"""
Porovnani trait hodnot taxonomickeho seznamu se zalohou.

Proc to existuje
----------------
V tabulce `taxalist_mzb` se nekdy pri importu zmenily saprobni hodnoty
u nekolika taxonu - napr. u rodu Micropsectra se saprobni index posunul
z 0,8 na 2,2. Rod je pritom bezny a pocetny (299 vzorku, pres 40 tisic
jedincu), takze jedina prehozena hodnota nadhodnotila saprobni index
u tri ctvrtin vsech vzorku, v krajnim pripade o vice nez celou tridu.

Chyba se v kodu neprojevi nijak - vzorec je spravny, jen dostane spatna
vstupni data. Proto tato kontrola.

Pouziti
-------
    python _tools/kontrola_traitu.py dtb/LULAN_dtb_001.db
    python _tools/kontrola_traitu.py dtb/LULAN_dtb_001.db --opravit
    python _tools/kontrola_traitu.py dtb/LULAN_dtb_001.db --report rozdily.csv
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

#: Dvojice (tabulka, zaloha), ktere se maji porovnavat.
DVOJICE = [
    ("taxalist_mzb", "taxalist_mzb_zaloha"),
    ("taxalist_fb", "taxalist_fb_zaloha"),
    ("taxalist_mf", "taxalist_mf_zaloha"),
    ("taxalist_ryby", "taxalist_ryby_zaloha"),
]

#: Sloupce, jejichz zmena ma vliv na vypocet metrik.
#: Sledujeme jen ty, ktere metriky skutecne pouzivaji - u ostatnich by
#: hlaseni jen zbytecne slo.
SLEDOVANE_SLOUPCE = [
    "SZS", "SZG",                       # saprobni index a jeho vaha
    "HLI",                              # lital
    "ZER", "ZMR", "ZHR", "ZEP",         # ricni zonace
    "FGR", "FMI", "FXY", "FSH",         # funkcni skupiny
    "FGA", "FAF", "FPF", "FPR", "FPA", "FOT",
    "SZA", "SZP",                       # saprobita pro vysychave toky
    "SPEAR_ORG",                        # SPEAR organic
    "MSZS", "MSZG", "SAL", "O2",        # fytobentos
    "MTV", "STEN_POLY",                 # makrofyta
]


def sloupce(conn, tabulka):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabulka})")]


def porovnej(conn, tabulka, zaloha):
    """Najde taxony s odlisnou trait hodnotou.

    Returns:
        list dictu {taxon, sloupec, nyni, zaloha, vzorku, jedincu}
    """
    dostupne = set(sloupce(conn, tabulka)) & set(sloupce(conn, zaloha))
    sledovane = [s for s in SLEDOVANE_SLOUPCE if s in dostupne]
    if not sledovane:
        return []

    rozdily = []
    for sl in sledovane:
        sql = f"""
            SELECT a.NAME, a.[{sl}], b.[{sl}],
                   (SELECT COUNT(DISTINCT sample) FROM data WHERE name = a.NAME),
                   (SELECT IFNULL(SUM(val), 0) FROM data WHERE name = a.NAME)
            FROM {tabulka} a
            JOIN {zaloha} b ON a.NAME = b.NAME
            WHERE IFNULL(TRIM(CAST(a.[{sl}] AS TEXT)), '#')
               <> IFNULL(TRIM(CAST(b.[{sl}] AS TEXT)), '#')
        """
        for nazev, nyni, zal, vzorku, jedincu in conn.execute(sql):
            rozdily.append({
                "tabulka": tabulka,
                "taxon": nazev,
                "sloupec": sl,
                "nyni": nyni,
                "zaloha": zal,
                "vzorku": vzorku or 0,
                "jedincu": jedincu or 0,
            })
    return rozdily


def vypis(rozdily, jen_pouzivane=False):
    """Vypise rozdily serazene podle dopadu."""
    if jen_pouzivane:
        rozdily = [r for r in rozdily if r["vzorku"] > 0]
    if not rozdily:
        print("  Zadne rozdily.")
        return

    rozdily = sorted(rozdily, key=lambda r: -r["jedincu"])
    print(f"  {'taxon':36s} {'sloupec':9s} {'nyni':>8s} {'zaloha':>8s} "
          f"{'vzorku':>7s} {'jedincu':>9s}")
    print(f"  {'-'*36} {'-'*9} {'-'*8} {'-'*8} {'-'*7} {'-'*9}")
    for r in rozdily:
        print(f"  {r['taxon'][:36]:36s} {r['sloupec']:9s} "
              f"{str(r['nyni']):>8s} {str(r['zaloha']):>8s} "
              f"{r['vzorku']:7d} {r['jedincu']:9.0f}")


def zapis_report(cesta, rozdily):
    import csv

    with open(cesta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["TABULKA", "TAXON", "SLOUPEC", "HODNOTA_NYNI",
                    "HODNOTA_ZALOHA", "VZORKU", "JEDINCU"])
        for r in sorted(rozdily, key=lambda x: -x["jedincu"]):
            w.writerow([r["tabulka"], r["taxon"], r["sloupec"],
                        r["nyni"], r["zaloha"], r["vzorku"], r["jedincu"]])


def oprav(conn, rozdily):
    """Prepise trait hodnoty hodnotami ze zalohy."""
    for r in rozdily:
        conn.execute(
            f"UPDATE {r['tabulka']} SET [{r['sloupec']}] = ? WHERE NAME = ?",
            (r["zaloha"], r["taxon"]),
        )
    conn.commit()
    return len(rozdily)


def spust(db_path, opravit=False, report=None, jen_pouzivane=False,
          jen_tabulky=None):
    conn = sqlite3.connect(db_path)
    try:
        # Nazvy tabulek jsou v databazi psane ruzne (taxalist_MZB vs
        # taxalist_mzb_zaloha), SQLite je ale porovnava bez ohledu na
        # velikost pismen - proto porovnavame take bez rozliseni.
        existujici = {
            r[0].lower() for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        vybrane = {t.lower() for t in jen_tabulky} if jen_tabulky else None

        vsechny = []
        for tabulka, zaloha in DVOJICE:
            if vybrane is not None and tabulka.lower() not in vybrane:
                continue
            if tabulka.lower() not in existujici or zaloha.lower() not in existujici:
                print(f"\n=== {tabulka}: zaloha {zaloha} neni k dispozici ===")
                continue
            print(f"\n=== {tabulka} vs {zaloha} ===")
            rozdily = porovnej(conn, tabulka, zaloha)
            vsechny += rozdily
            vypis(rozdily, jen_pouzivane)

        if report and vsechny:
            zapis_report(report, vsechny)
            print(f"\nPrehled zapsan do {report}")

        if opravit and vsechny:
            # Upozornit na hodnoty, ktere se prepisem ZTRATI - v zaloze
            # chybi, takze se nastavi na prazdno.
            ztraty = [
                r for r in vsechny
                if r["zaloha"] in (None, "") and r["nyni"] not in (None, "")
                and r["vzorku"] > 0
            ]
            if ztraty:
                print("\n  POZOR - tyto hodnoty se prepisem ztrati "
                      "(v zaloze nejsou vyplnene):")
                for r in ztraty:
                    print(f"    {r['taxon'][:36]:36s} {r['sloupec']:9s} "
                          f"{str(r['nyni']):>8s} -> prazdno   "
                          f"({r['vzorku']} vzorku, {r['jedincu']:.0f} jedincu)")

            pocet = oprav(conn, vsechny)
            print(f"\nOpraveno {pocet} hodnot podle zalohy.")

        pouzivane = [r for r in vsechny if r["vzorku"] > 0]
        print(f"\nCelkem rozdilu: {len(vsechny)}, "
              f"z toho u taxonu pouzitych ve vzorcich: {len(pouzivane)}")
        return 0
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("db", help="cesta k databazi")
    p.add_argument("--opravit", action="store_true",
                   help="prepsat hodnoty hodnotami ze zalohy")
    p.add_argument("--report", help="ulozit prehled rozdilu do CSV")
    p.add_argument("--jen-pouzivane", action="store_true",
                   help="vypsat jen taxony, ktere se vyskytuji ve vzorcich")
    p.add_argument("--tabulka", action="append",
                   help="omezit na konkretni taxalist (lze opakovat)")
    p.add_argument("--primo", action="store_true",
                   help="zapisovat primo misto pres docasnou kopii")
    args = p.parse_args()

    if not args.opravit:
        sys.exit(spust(args.db, False, args.report, args.jen_pouzivane,
                       args.tabulka))

    zaloha = f"{args.db}.pred_opravou_traitu_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(args.db, zaloha)
    print(f"Zaloha: {zaloha}")

    # SQLite si na sitovych a synchronizovanych discich neporadi se zamky
    if args.primo:
        pracovni = args.db
    else:
        popisovac, pracovni = tempfile.mkstemp(suffix=".db", prefix="lulan_trait_")
        os.close(popisovac)
        shutil.copy2(args.db, pracovni)

    try:
        navrat = spust(pracovni, True, args.report, args.jen_pouzivane,
                       args.tabulka)
        if not args.primo and navrat == 0:
            shutil.copy2(pracovni, args.db)
            print(f"Hotovy soubor zkopirovan zpet do {args.db}")
    finally:
        if not args.primo and os.path.exists(pracovni):
            os.remove(pracovni)

    sys.exit(navrat)


if __name__ == "__main__":
    main()
