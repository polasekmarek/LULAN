"""
Kontrola vypoctu hodnoceni podle ryb.

Overuje tri veci:

  1. prevod metrik na EQR proti prikladum, ktere metodika sama pocita
     (Janac a kol. 2019, kap. 3, str. 12)
  2. zarazeni profilu do typu toku proti klici v Tab. 2
  3. vyber prevodni tabulky podle kategorie silne ovlivneneho utvaru
     (Janac a kol. 2024, Tab. 8 a kap. 3.1-3.8)

a nakonec spocita vsechny vzorky ryb v databazi a vypise prehled.

Pouziti:
    python _tools/test_ryby.py [cesta_k_databazi]
"""

import os
import shutil
import sys
import sqlite3
import tempfile
from collections import Counter

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

_stav = {"ok": 0, "chyba": 0}


def zkontroluj(popis, spocteno, ocekavano, tolerance=0.005):
    shoda = (
        spocteno == ocekavano
        if isinstance(ocekavano, str) or ocekavano is None
        else abs(spocteno - ocekavano) <= tolerance
    )
    _stav["ok" if shoda else "chyba"] += 1
    znacka = "ok  " if shoda else "CHYBA"
    hodnota = spocteno if isinstance(spocteno, str) else f"{spocteno:.4f}"
    print(f"  {znacka} {popis:56s} {str(hodnota):>10s}  ocekavano {ocekavano}")


# ---------------------------------------------------------------------------

def test_eqr():
    """Priklady vypoctu EQR ze str. 12 metodiky."""
    from calc_index.ryby_metriky import eqr

    print("\n1. Priklady vypoctu EQR z metodiky (kap. 3, str. 12)")
    zkontroluj("TD  typ A, 1 typicky taxon: ln(6)/ln(11)",
               eqr(1, 2, False, "ln5"), 0.7472)
    zkontroluj("TD  typ E, 3 typicke taxony: 3/6",
               eqr(3, 6, False, None), 0.50)
    zkontroluj("AR  typ A, pstruh 30 ks/100 m: 30/50",
               eqr(30, 50, False, None), 0.60)
    zkontroluj("AR  typ C, reofilove 50 ks/100 m: 50/100",
               eqr(50, 100, False, None), 0.50)
    zkontroluj("ND1 typ B, 2 EL taxony: 1-ln(21)/ln(41)",
               eqr(2, 4, True, "ln10"), 0.18)
    zkontroluj("ND1 typ F, 1 invazni taxon: 1-1/1",
               eqr(1, 1, True, None), 0.0)
    zkontroluj("ND2 typ B, 20 % EL: 1-ln(21)/ln(51)",
               eqr(0.20, 0.5, True, "ln100"), 0.226)
    zkontroluj("ND2 typ E, 5 % invaznich: 1-ln(6)/ln(34,33)",
               eqr(0.05, 1 / 3, True, "ln100"), 0.493)
    zkontroluj("orezani: hodnota nad horni mezi da EQR presne 1",
               eqr(300, 200, False, None), 1.0)


def test_vahy():
    """Soucet vah musi byt v kazdem typu presne 4 - metodika deli ctyrmi."""
    from calc_index.ryby_reka import EQR_TABLE
    from calc_index.ryby_potencial import TABULKA_V

    print("\n2. Soucet vah metrik (metodika deli konstantou 4)")
    for typ, radek in EQR_TABLE.items():
        zkontroluj(f"stav, typ {typ}", sum(v[1] for v in radek.values()), 4.0,
                   tolerance=1e-9)
    for typ, radek in TABULKA_V.items():
        zkontroluj(f"potencial kat. V, typ {typ}",
                   sum(v[1] for v in radek.values()), 4.0, tolerance=1e-9)


def test_typologie():
    """Zarazeni do typu toku proti klici v Tab. 2."""
    from calc_index.ryby_typologie import urci_typ

    print("\n3. Typologie toku (Tab. 2)")
    # (umori v kodovani LULANu, nadm. vyska, Strahler, ocekavany typ)
    pripady = [
        (2, 900, 4, "A"),    # Baltske, h >= 500
        (2, 450, 5, "B"),    # Baltske, 400-500
        (2, 300, 5, "B"),    # Baltske, 250-400
        (2, 100, 5, "E"),    # Baltske, < 250
        (2, 100, 4, "B"),
        (2, 100, 7, "F"),
        (3, 100, 4, "D"),    # Cerne, < 250, 4. rad
        (3, 300, 6, "E"),    # Cerne, 250-400, 6. rad
        (3, 100, 6, "F"),
        (3, 200, 8, "G"),
        (1, 300, 5, "C"),    # Severni, 250-400, 5. rad
        (1, 450, 6, "C"),    # Severni, 400-500, 6. rad
        (1, 300, 6, "F"),    # Severni, 250-400, 6. rad
        (1, 100, 9, "G"),
        (1, 900, 9, "A"),    # nad 500 m je vzdy A
    ]
    for umori, mnm, strahler, ocekavano in pripady:
        typ, _ = urci_typ(umori, mnm, strahler)
        zkontroluj(f"umori={umori}, {mnm} m n.m., {strahler}. rad",
                   str(typ), ocekavano)

    typ, duvod = urci_typ(1, 300, 3)
    zkontroluj("3. rad se nehodnoti", str(typ), "None")
    typ, duvod = urci_typ(1, None, 5)
    zkontroluj("chybejici nadmorska vyska", str(typ), "None")


def test_kategorie_hmwb():
    """Vyber prevodni tabulky podle kategorie HMWB."""
    from calc_index.ryby_hmwb_utvary import UTVARY_KATEGORIE, pocty_podle_kategorii
    from calc_index.ryby_potencial import (
        TABULKA_I, TABULKA_II, TABULKA_III, TABULKA_V, vyber_nastaveni,
    )

    print("\n4. Kategorie silne ovlivnenych utvaru (Tab. 3-11)")
    ocekavane_pocty = {
        "I": 17, "II": 1, "III": 12, "IV": 9, "V": 14,
        "VI": 4, "VII": 18, "VIII": 21, "IX": 3, "X": 3,
    }
    pocty = pocty_podle_kategorii()
    for kat, ocekavano in ocekavane_pocty.items():
        zkontroluj(f"pocet utvaru kategorie {kat}", float(pocty[kat]),
                   float(ocekavano), tolerance=1e-9)

    zkontroluj("kat. I pouziva TA + AR",
               ",".join(sorted(vyber_nastaveni("I", "C")[0])), "RY_AR,RY_TA")
    zkontroluj("kat. II pouziva TD + AR a typ F",
               vyber_nastaveni("II", "F")[1], "F")
    zkontroluj("kat. III prerazuje do typu G",
               vyber_nastaveni("III", "F")[1], "G")
    zkontroluj("kat. IV prerazuje do typu A",
               vyber_nastaveni("IV", "E")[1], "A")
    zkontroluj("kat. V, typ B: horni mez AR podle Tab. 8",
               vyber_nastaveni("V", "B")[0]["RY_AR"][0], 50.0)
    zkontroluj("kat. V, typ A: horni mez TD podle Tab. 8",
               vyber_nastaveni("V", "A")[0]["RY_TD"][0], 1.0)
    zkontroluj("kat. VII nemeni nic (standardni tabulka)",
               str(vyber_nastaveni("VII", "E")[0]), "None")
    zkontroluj("kat. III: mez TD snizena z 12 na 6",
               TABULKA_III["RY_TD"][0], 6.0)
    zkontroluj("kat. I: mez AR 20 ks/100 m",
               TABULKA_I["RY_AR"][0], 20.0)
    zkontroluj("kat. II: mez TD snizena z 8 na 6",
               TABULKA_II["RY_TD"][0], 6.0)


def test_ekvivalentni_skupiny(db):
    """Hrouzci a formy pstruha se pocitaji jako jeden taxon (Tab. 4)."""
    from calc_index.common import nacti_taxalist
    from calc_index.ryby_metriky import TRAIT_SLOUPCE, _skupina

    print("\n5. Slucovani taxonu, ktere Tab. 4 vede jako jednu polozku")
    taxalist = nacti_taxalist(db, "taxalist_ryby", TRAIT_SLOUPCE)
    by_name, by_id = taxalist["by_name"], taxalist["by_id"]

    def klic(*jmena):
        data = {by_name[j]["ID"]: 10.0 for j in jmena if j in by_name}
        return _skupina(data, by_id, "G")

    zkontroluj("Gobio gobio + Romanogobio albipinnatus = 1 taxon",
               float(len(klic("Gobio gobio", "Romanogobio albipinnatus"))),
               1.0, tolerance=1e-9)
    zkontroluj("Gobio gobio + Squalius cephalus = 2 taxony",
               float(len(klic("Gobio gobio", "Squalius cephalus"))),
               2.0, tolerance=1e-9)

    def klic_c(*jmena):
        data = {by_name[j]["ID"]: 10.0 for j in jmena if j in by_name}
        return _skupina(data, by_id, "C")

    zkontroluj("Lampetra planeri + L. fluviatilis = 1 taxon",
               float(len(klic_c("Lampetra planeri", "Lampetra fluviatilis"))),
               1.0, tolerance=1e-9)
    zkontroluj("Salmo trutta + S. trutta m. fario = 1 taxon",
               float(len(klic_c("Salmo trutta", "Salmo trutta m. fario"))),
               1.0, tolerance=1e-9)


def spust_na_datech(db, db_path):
    """Spocita vsechny vzorky ryb a vypise prehled."""
    from calc_index.registry import vlastnosti_utvaru, vyber_funkci_pro_vzorek

    print("\n6. Vypocet na realnych datech")
    conn = sqlite3.connect(db_path)
    vzorky = [
        r[0] for r in conn.execute(
            "SELECT SAMPLE_ID FROM samples WHERE TYP = 'RYBY' ORDER BY SAMPLE_ID"
        )
    ]
    tridy, typy, nehodnoceno = Counter(), Counter(), Counter()
    for sample_id in vzorky:
        utvar = vlastnosti_utvaru(sample_id, db)
        funkce, potencial = vyber_funkci_pro_vzorek("RYBY", utvar, sample_id, db)
        if funkce is None:
            nehodnoceno["neni v registru"] += 1
            continue
        vysledek = (
            funkce(sample_id, db, potencial=potencial)
            if potencial else funkce(sample_id, db)
        )
        if vysledek.get("RYBY_CELKEM") is None:
            nehodnoceno[vysledek.get("RYBY_POZN", "?")[:60]] += 1
            continue
        tridy[vysledek.get("RYBY_CLASS")] += 1
        typy[vysledek.get("RYBY_TYP")] += 1

    print(f"  vzorku ryb v databazi: {len(vzorky)}")
    print(f"  spocitano:             {sum(tridy.values())}")
    print(f"  tridy:                 {dict(sorted(tridy.items()))}")
    print(f"  typy toku:             {dict(sorted(typy.items()))}")
    if nehodnoceno:
        print("  nehodnoceno:")
        for duvod, pocet in nehodnoceno.most_common():
            print(f"    {pocet:3d}x {duvod}")
    return sum(tridy.values())


def main():
    zdroj = sys.argv[1] if len(sys.argv) > 1 else VYCHOZI_DB
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="lulan_ryby_")
    os.close(fd)
    shutil.copy2(zdroj, db_path)

    from PyQt6.QtSql import QSqlDatabase

    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(db_path)
    db.open()

    try:
        test_eqr()
        test_vahy()
        test_typologie()
        test_kategorie_hmwb()
        test_ekvivalentni_skupiny(db)
        spust_na_datech(db, db_path)
    finally:
        db.close()
        os.remove(db_path)

    print(f"\nKontrol proslo: {_stav['ok']}, selhalo: {_stav['chyba']}")
    return 1 if _stav["chyba"] else 0


if __name__ == "__main__":
    sys.exit(main())
