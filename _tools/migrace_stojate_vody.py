"""
Rozsireni schematu o stojate vody (kategorie jezero).

Metodika pro hodnoceni ekologickeho potencialu kategorie jezero (Borovec
a kol. 2014) potrebuje jine abioticke parametry nez tekouci vody: misto
Strahlerova radu, plochy povodi a sklonu jde o prumernou a maximalni
hloubku, plochu hladiny a dobu zdrzeni vody.

Skript pridava:

  loc     KATEGORIE      R = tekouci (reka), J = stojata (jezero)
          MAX_HLOUBKA    maximalni hloubka [m]
          PRUM_HLOUBKA   prumerna hloubka [m]
          PLOCHA_KM2     plocha hladiny [km2]
          TRT            doba zdrzeni vody [rok]
          GEOLOGIE       1 = krystalinikum a vulkanity, 2 = piskovce/jilovce/kvarter

  data    BIOMASA        objemova biomasa taxonu [mm3/l] (fytoplankton)
          SIT            typ tenatni site: BT, PT (ryby)
          ZONA           H = hrazova cast, P = pritokova cast (ryby)
          POKRYVNOST     pokryvnost taxonu [%] (makrofyta)

Existujicim zaznamum se KATEGORIE nastavi na 'R' - vsech 86 lokalit
v databazi jsou profily na tekoucich vodach.

Vsechny nove sloupce jsou volitelne, takze vypocty nad tekoucimi vodami
zustavaji nedotcene.

Pouziti:
    python _tools/migrace_stojate_vody.py [cesta_k_databazi]
    python _tools/migrace_stojate_vody.py --kontrola
"""

import os
import sqlite3
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

#: (tabulka, sloupec, definice, komentar)
NOVE_SLOUPCE = [
    ("loc", "KATEGORIE", "TEXT", "R = tekoucí, J = stojatá voda"),
    ("loc", "MAX_HLOUBKA", "REAL", "maximální hloubka [m]"),
    ("loc", "PRUM_HLOUBKA", "REAL", "průměrná hloubka [m]"),
    ("loc", "PLOCHA_KM2", "REAL", "plocha hladiny [km²]"),
    ("loc", "TRT", "REAL", "doba zdržení vody [rok]"),
    ("loc", "GEOLOGIE", "INTEGER", "1 = krystalinikum, 2 = sedimenty"),
    ("data", "BIOMASA", "REAL", "objemová biomasa taxonu [mm³/l]"),
    ("data", "SIT", "TEXT", "typ tenatní sítě: BT, PT"),
    ("data", "ZONA", "TEXT", "H = hrázová část, P = přítoková část"),
    ("data", "POKRYVNOST", "REAL", "pokryvnost taxonu [%]"),
]


def sloupce(conn, tabulka):
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{tabulka}")')}


def migruj(db_path, jen_kontrola=False):
    """Prida chybejici sloupce. Vraci seznam provedenych zmen."""
    conn = sqlite3.connect(db_path)
    zmeny = []
    try:
        for tabulka, sloupec, typ, popis in NOVE_SLOUPCE:
            if sloupec in sloupce(conn, tabulka):
                continue
            zmeny.append(f"{tabulka}.{sloupec} ({typ}) — {popis}")
            if not jen_kontrola:
                conn.execute(
                    f'ALTER TABLE "{tabulka}" ADD COLUMN "{sloupec}" {typ}')

        if not jen_kontrola:
            # Vsechny stavajici lokality jsou profily na tekoucich vodach.
            pocet = conn.execute(
                "UPDATE loc SET KATEGORIE = 'R' WHERE KATEGORIE IS NULL"
            ).rowcount
            if pocet:
                zmeny.append(f"loc.KATEGORIE = 'R' nastaveno u {pocet} lokalit")
            conn.commit()
    finally:
        conn.close()
    return zmeny


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    db = argv[0] if argv else VYCHOZI_DB
    kontrola = "--kontrola" in sys.argv

    if not os.path.exists(db):
        print(f"Databáze nenalezena: {db}")
        return 1

    zmeny = migruj(db, jen_kontrola=kontrola)
    if not zmeny:
        print("Schéma je aktuální, není co měnit.")
        return 0

    print("Chybí:" if kontrola else "Provedeno:")
    for z in zmeny:
        print(f"  {z}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
