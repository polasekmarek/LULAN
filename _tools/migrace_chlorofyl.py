"""
Doplneni kodu chlorofylu-a do ciselniku chemickych parametru.

Hodnoceni fytoplanktonu potrebuje koncentraci chlorofylu-a jako metriku
celkove biomasy. V ciselnicich `chem_params` a `taxalist_chem` kod dosud
chybel, takze hodnoty nebylo kam ukladat ani je nebylo videt v detailu
vzorku.

Pouziti:
    python _tools/migrace_chlorofyl.py dtb/LULAN_dtb_001.db            # nahled
    python _tools/migrace_chlorofyl.py dtb/LULAN_dtb_001.db --zapsat
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

#: Kody, ktere se maji v ciselnicich vyskytovat.
#: (kod, popis, jednotka)
KODY = [
    ("IC0000", "chlorofyl-a (extrakce ethanolem)", "UG_L"),
]


def doplnit(db_path, zapsat=False):
    conn = sqlite3.connect(db_path)
    try:
        zmeny = []

        for kod, popis, jednotka in KODY:
            # chem_params: kod, popis
            je = conn.execute(
                "SELECT COUNT(*) FROM chem_params WHERE kod = ?", (kod,)
            ).fetchone()[0]
            if je:
                print(f"  chem_params:   {kod} uz existuje")
            else:
                zmeny.append(("chem_params", kod, popis))
                print(f"  chem_params:   {kod} bude pridan - {popis}")

            # taxalist_chem: KOD, descript, jednotka
            je = conn.execute(
                "SELECT COUNT(*) FROM taxalist_chem WHERE KOD = ?", (kod,)
            ).fetchone()[0]
            if je:
                print(f"  taxalist_chem: {kod} uz existuje")
            else:
                zmeny.append(("taxalist_chem", kod, popis, jednotka))
                print(
                    f"  taxalist_chem: {kod} bude pridan - {popis} [{jednotka}]"
                )

        if not zmeny:
            print("\n  Neni co doplnovat.")
            return 0

        if not zapsat:
            print("\n  (nahled - pro zapis pouzijte --zapsat)")
            return 0

        for zmena in zmeny:
            if zmena[0] == "chem_params":
                conn.execute(
                    "INSERT INTO chem_params (kod, popis) VALUES (?, ?)",
                    zmena[1:],
                )
            else:
                conn.execute(
                    "INSERT INTO taxalist_chem (KOD, descript, jednotka) "
                    "VALUES (?, ?, ?)",
                    zmena[1:],
                )
        conn.commit()
        print(f"\n  Zapsano {len(zmeny)} zaznamu.")
        return 0

    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="cesta k databazi")
    p.add_argument("--zapsat", action="store_true")
    p.add_argument("--primo", action="store_true",
                   help="zapisovat primo misto pres docasnou kopii")
    args = p.parse_args()

    if not args.zapsat:
        sys.exit(doplnit(args.db, False))

    zaloha = f"{args.db}.pred_chlorofylem_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(args.db, zaloha)
    print(f"Zaloha: {zaloha}")

    # SQLite si na sitovych a synchronizovanych discich neporadi se zamky -
    # pracujeme na docasne kopii a hotovy soubor kopirujeme zpet.
    if args.primo:
        pracovni = args.db
    else:
        popisovac, pracovni = tempfile.mkstemp(suffix=".db", prefix="lulan_chl_")
        os.close(popisovac)
        shutil.copy2(args.db, pracovni)

    try:
        navrat = doplnit(pracovni, True)
        if not args.primo and navrat == 0:
            shutil.copy2(pracovni, args.db)
            print(f"Hotovy soubor zkopirovan zpet do {args.db}")
    finally:
        if not args.primo and os.path.exists(pracovni):
            os.remove(pracovni)

    sys.exit(navrat)


if __name__ == "__main__":
    main()
