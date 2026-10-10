"""
Mereni rychlosti vypoctu - nova verze proti puvodnimu monolitu.

Skript si sam pripravi pracovni kopii databaze vcetne abiotickych parametru,
takze nezavisi na zadnem docasnem souboru z drivejsiho behu.

Pouziti:
    python _tools/vykon.py [pocet_vzorku]
"""

import importlib
import os
import shutil
import sqlite3
import sys
import time

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))

from PyQt6.QtSql import QSqlDatabase  # noqa: E402

ZDROJ_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
PUVODNI_MODULY = os.path.join(KOREN, "_archiv", "src_orig")
NOVE_MODULY = os.path.join(KOREN, "src")


def priprav_db(cil):
    """Vytvori pracovni kopii databaze s doplnenymi souradnicemi."""
    shutil.copy(ZDROJ_DB, cil)
    sys.path.insert(0, NOVE_MODULY)
    import abiotic_params as ap
    ap.doplnit_parametry(cil, ["souradnice", "umori"], jen_chybejici=True)
    return cil


def spust(modul_dir, db_path, vzorky):
    """Zmeri cas vypoctu zadanych vzorku danou verzi modulu."""
    for m in list(sys.modules):
        if m.startswith("calc_index") or m in ("B_index2", "calc_indexes"):
            del sys.modules[m]
    sys.path = [p for p in sys.path if "src" not in p and "_archiv" not in p]
    sys.path.insert(0, modul_dir)

    import calc_indexes as ci
    importlib.reload(ci)

    db = QSqlDatabase(db_path)
    zacatek = time.perf_counter()
    chyb = 0
    for sample_id in vzorky:
        try:
            ci.calc_indexes(sample_id, db)
        except Exception:  # noqa: BLE001 - merime rychlost, ne spravnost
            chyb += 1
    trvani = time.perf_counter() - zacatek
    db.conn.commit()
    db.close()
    return trvani, chyb


def main():
    pocet = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    pracovni = "/tmp/vykon_zdroj.db"
    if not os.path.exists(pracovni):
        priprav_db(pracovni)

    conn = sqlite3.connect(pracovni)
    vzorky = [
        r[0] for r in conn.execute(
            """
            SELECT s.SAMPLE_ID FROM samples s
            JOIN loc l ON s.LOC_ID = l.KOD
            JOIN utvary u ON l.VU = u.ID_UTVARU
            JOIN (SELECT DISTINCT sample FROM data) d ON d.sample = s.SAMPLE_ID
            WHERE s.TYP = 'MZB' LIMIT ?
            """, (pocet,)
        )
    ]
    conn.close()

    if not vzorky:
        print("V databazi nejsou zadne pouzitelne vzorky MZB.")
        return 1

    shutil.copy(pracovni, "/tmp/vykon_nova.db")
    trvani_nova, chyb_nova = spust(NOVE_MODULY, "/tmp/vykon_nova.db", vzorky)

    print(f"\n{len(vzorky)} vzorku MZB:")
    print(f"  nova verze:    {trvani_nova:7.2f} s  "
          f"({trvani_nova / len(vzorky) * 1000:6.0f} ms/vzorek), chyb: {chyb_nova}")

    if os.path.isdir(PUVODNI_MODULY):
        shutil.copy(pracovni, "/tmp/vykon_puvodni.db")
        trvani_stara, chyb_stara = spust(
            PUVODNI_MODULY, "/tmp/vykon_puvodni.db", vzorky
        )
        print(f"  puvodni verze: {trvani_stara:7.2f} s  "
              f"({trvani_stara / len(vzorky) * 1000:6.0f} ms/vzorek), "
              f"chyb: {chyb_stara}")
        print(f"  zrychleni:     {trvani_stara / trvani_nova:.1f}x")
    else:
        print(f"  (puvodni verze v {PUVODNI_MODULY} neni k dispozici, "
              f"srovnani se preskakuje)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
