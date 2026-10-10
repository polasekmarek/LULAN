"""
Prepocet vysledku mimo GUI - diagnostika i nahradni cesta.

Spusti tyz vypocet jako tlacitko "Spustit výpočet" v aplikaci, ale
v jednom vlakne a s vypisem do konzole. Slouzi ke dvema vecem:

  1. **diagnostika** - kdyz aplikace hlasi "Úspěšně vyhodnoceno: 0",
     tenhle skript ukaze, na cem to padlo (`--rozbor`)
  2. **nahradni cesta** - vysledky lze prepocitat i bez GUI

Pouziti:
    python _tools/prepocet.py --rozbor                 # jen rozbor, nezapisuje
    python _tools/prepocet.py --rozbor --vzorky RV_    # jen vybrane vzorky
    python _tools/prepocet.py --spustit                # prepocita a zapise
    python _tools/prepocet.py --spustit --db jina.db

POZOR: `--spustit` zapisuje do databaze. Kdyz databaze lezi na
synchronizovanem ulozisti (ownCloud, OneDrive, Dropbox), zavrete pred
spustenim aplikaci - jinak si dva zapisovatele mohou prekazet.
"""

import argparse
import collections
import io
import contextlib
import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")


def nacti_vzorky(db, filtr=None):
    """Vrati seznam (SAMPLE_ID, TYP) vzorku k prepoctu."""
    from PyQt6.QtSql import QSqlQuery

    dotaz = QSqlQuery(db)
    sql = ("SELECT SAMPLE_ID, TYP FROM samples "
           "WHERE SAMPLE_ID IS NOT NULL AND SAMPLE_ID != ''")
    if filtr:
        sql += f" AND SAMPLE_ID LIKE '{filtr}%'"
    sql += " ORDER BY SAMPLE_ID"
    dotaz.exec(sql)

    vzorky = []
    while dotaz.next():
        vzorky.append((dotaz.value(0), dotaz.value(1)))
    return vzorky


def otevri(cesta):
    from PyQt6.QtSql import QSqlDatabase

    db = QSqlDatabase.addDatabase("QSQLITE", "prepocet")
    db.setDatabaseName(cesta)
    if not db.open():
        raise SystemExit(f"Databázi {cesta} nelze otevřít: "
                         f"{db.lastError().text()}")
    return db


def rozbor(cesta, filtr=None):
    """Projde vzorky, spocita je a vypise, proc se nekterym nespocetlo.

    Nic nezapisuje - vypocetni moduly sice vysledky zapisuji samy, takze
    se tomu neda uplne vyhnout; proto se pracuje nad kopii v pameti.
    """
    import shutil
    import tempfile

    kopie = os.path.join(tempfile.mkdtemp(), "rozbor.db")
    shutil.copy(cesta, kopie)
    print(f"pracuji nad kopií {kopie} (původní databáze zůstane nedotčená)\n")

    db = otevri(kopie)
    from calc_index.registry import vycisti_hlaseni
    from calc_index.runner import SLOZKY, calc_indexes

    vycisti_hlaseni()
    vzorky = nacti_vzorky(db, filtr)
    print(f"vzorků k přepočtu: {len(vzorky)}\n")

    podle_typu = collections.defaultdict(
        lambda: {"celkem": 0, "spocteno": 0, "duvody": collections.Counter()})

    for sample_id, typ in vzorky:
        stat = podle_typu[typ or "?"]
        stat["celkem"] += 1
        with contextlib.redirect_stdout(io.StringIO()) as zachyceno:
            vysledek = calc_indexes(sample_id, db)

        if vysledek is None:
            stat["duvody"]["výpočet vrátil None"] += 1
            continue
        if any(vysledek.get(f"{s}_CELKEM") is not None for s in SLOZKY):
            stat["spocteno"] += 1
            continue

        pozn = next(
            (vysledek[f"{s}_POZN"] for s in SLOZKY
             if vysledek.get(f"{s}_POZN")), "bez uvedení důvodu")
        stat["duvody"][str(pozn)[:90]] += 1

    print(f"{'typ':6s} {'celkem':>7s} {'spočteno':>9s} {'nespočteno':>11s}")
    for typ, stat in sorted(podle_typu.items()):
        print(f"{typ:6s} {stat['celkem']:7d} {stat['spocteno']:9d} "
              f"{stat['celkem'] - stat['spocteno']:11d}")

    for typ, stat in sorted(podle_typu.items()):
        if not stat["duvody"]:
            continue
        print(f"\ndůvody u složky {typ}:")
        for duvod, kolik in stat["duvody"].most_common(10):
            print(f"  {kolik:5d}x  {duvod}")

    db.close()
    return podle_typu


def spustit(cesta, filtr=None):
    """Prepocita vysledky a zapise je do databaze."""
    db = otevri(cesta)
    from calc_index.common import vycisti_cache
    from calc_index.registry import vycisti_hlaseni
    from calc_index.runner import SLOZKY, aggregate_results_to_year, calc_indexes

    vycisti_cache()
    vycisti_hlaseni()
    vzorky = nacti_vzorky(db, filtr)
    print(f"přepočítávám {len(vzorky)} vzorků…")

    uspesnych = 0
    for i, (sample_id, _typ) in enumerate(vzorky, 1):
        if i % 200 == 0:
            print(f"   … {i}/{len(vzorky)}")
        with contextlib.redirect_stdout(io.StringIO()):
            vysledek = calc_indexes(sample_id, db)
        if vysledek and any(
                vysledek.get(f"{s}_CELKEM") is not None for s in SLOZKY):
            uspesnych += 1

    print(f"hotovo: úspěšně vyhodnoceno {uspesnych} z {len(vzorky)}")
    agregace = aggregate_results_to_year(db)
    print(f"agregace do ročních výsledků: {agregace['message']}")
    db.close()


def uklid(cesta):
    """Spusti VACUUM - prepise soubor a srovna vnitrni struktury.

    `PRAGMA integrity_check` obcas hlasi "Main freelist: size is X but
    should be Y". Data to neohrozuje, ale je to stopa po zapisu, ktery
    neskoncil cistě - u databaze na synchronizovanem ulozisti typicky po
    prerusenem zapisu. VACUUM soubor prepise a nesrovnalost odstrani.
    """
    import sqlite3

    conn = sqlite3.connect(cesta)
    print("před:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    conn.execute("VACUUM")
    print("po:  ", conn.execute("PRAGMA integrity_check").fetchone()[0])
    conn.close()


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--vzorky", metavar="PREFIX",
                   help="jen vzorky, jejichž SAMPLE_ID začíná tímto textem")
    p.add_argument("--rozbor", action="store_true",
                   help="jen rozbor, do databáze nezapisuje")
    p.add_argument("--spustit", action="store_true",
                   help="přepočítat a zapsat výsledky")
    p.add_argument("--vacuum", action="store_true",
                   help="uklidit databázi (opraví nesrovnalosti ve freelistu)")
    args = p.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"Databáze nenalezena: {args.db}")

    if args.vacuum:
        uklid(args.db)
    elif args.spustit:
        spustit(args.db, args.vzorky)
    else:
        rozbor(args.db, args.vzorky)


if __name__ == "__main__":
    main()
