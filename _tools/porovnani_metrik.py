"""
Porovnani metrik MZB spocitanych LULANem s oficialnimi hodnotami.

Nacte referencni tabulku, spocita tytez vzorky vlastnim vypoctem a pro
kazdou metriku i jeji EQR porovna hodnoty - korelace, prumerna odchylka,
bodovy graf.

Pouziti:
    python _tools/porovnani_metrik.py                       # vypocet + report
    python _tools/porovnani_metrik.py --jen-vypocet         # jen ulozit hodnoty
"""

import argparse
import os
import shutil
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

REFERENCE = os.path.join(
    "/sessions/beautiful-zen-pasteur/mnt/uploads",
    "MZB_hodnoceni_metriky_EQR_pro_testovani.csv",
)
PRACOVNI_DB = "/tmp/porovnani.db"
VYSTUP = os.path.join(KOREN, "_tools", "vypocet_lulan.csv")

METRIKY = [f"MB{i:02d}" for i in range(1, 19)]


def priprav_db():
    """Vytvori pracovni kopii databaze s doplnenymi abiotickymi parametry."""
    if os.path.exists(PRACOVNI_DB):
        return PRACOVNI_DB
    shutil.copy(os.path.join(KOREN, "dtb", "LULAN_dtb_001.db"), PRACOVNI_DB)
    import abiotic_params as ap
    ap.doplnit_parametry(PRACOVNI_DB, ["souradnice", "umori"], jen_chybejici=True)
    return PRACOVNI_DB


def spocitej(vzorky):
    """Spocita metriky a EQR pro zadane vzorky.

    Returns:
        dict {sample_id: {metrika: hodnota, metrikaQ: eqr, 'MB_CELKEM': ...}}
    """
    from PyQt6.QtSql import QSqlDatabase
    from calc_index.common import preved_na_eqr, vazeny_prumer, vycisti_cache
    from calc_index.mzb_metrics import priprav_data, spocitej_metriky
    from calc_index.mzb_perennial_broditelne import (
        EQR_TABLE, urci_adjustace, urci_typ_lokality,
    )
    from calc_index.common import urci_sezonu

    vycisti_cache()
    db = QSqlDatabase(priprav_db())
    from PyQt6.QtSql import QSqlQuery

    vysledky = {}
    for i, sid in enumerate(vzorky, 1):
        if i % 100 == 0:
            print(f"   ... {i}/{len(vzorky)}")

        q = QSqlQuery(db)
        q.prepare(
            "SELECT s.DATE, s.LOC_ID, l.MNM, l.STRAHLER FROM samples s "
            "LEFT JOIN loc l ON s.LOC_ID = l.KOD WHERE s.SAMPLE_ID = ?"
        )
        q.addBindValue(sid)
        if not q.exec() or not q.next():
            continue
        datum, loc_id, mnm, strahler = (q.value(j) for j in range(4))

        sezona = urci_sezonu(datum)
        typ = urci_typ_lokality(mnm, strahler)
        if sezona is None:
            continue

        metr_adj, pred_adj = urci_adjustace(sezona, typ)
        priprava = priprav_data(db, sid, metr_adj, pred_adj)
        if priprava is None:
            continue

        metriky = spocitej_metriky(priprava, db, loc_id, sezona)
        zaznam = dict(metriky)

        # EQR podle typu a sezony, pokud je pro kombinaci tabulka
        klic = (typ, sezona, strahler)
        if klic not in EQR_TABLE:
            klic = (typ, sezona, None)
        radek = EQR_TABLE.get(klic)
        if radek:
            from calc_index.mzb_perennial_broditelne import _uprav_meze_dle_arrow
            radek = _uprav_meze_dle_arrow(radek, typ, sezona)
            eqr = preved_na_eqr(metriky, radek)
            for m, v in eqr.items():
                zaznam[m.replace("_EQR", "") + "Q"] = v
            mmi, _ = vazeny_prumer(eqr, radek)
            zaznam["MB_CELKEM"] = mmi

        zaznam["_typ"] = typ
        zaznam["_sezona"] = sezona
        zaznam["_strahler"] = strahler
        zaznam["_mnm"] = mnm
        vysledky[sid] = zaznam

    db.conn.commit()
    db.close()
    return vysledky


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jen-vypocet", action="store_true")
    p.add_argument(
        "--meze-arrow", action="store_true",
        help="u typu 2-1 jaro pouzit horni meze RETI 0,86 a Margalef 8,4, "
             "se kterymi pocita IS ARROW (metodika uvadi 0,81 a 7,7)",
    )
    p.add_argument(
        "--vsechny-sezony", action="store_true",
        help="do reportu zahrnout i letni vzorky (ty se podle metodiky "
             "nehodnoti a v databazi maji nekompletni taxonomii)",
    )
    args = p.parse_args()

    if args.meze_arrow:
        import calc_index.mzb_perennial_broditelne as mpb
        mpb.MEZE_DLE_ARROW = True
        print("meze typu 2-1 jaro: pouzity hodnoty z IS ARROW")

    import pandas as pd

    ref = pd.read_csv(REFERENCE, sep=";", encoding="utf-8-sig")
    ref = ref.rename(columns={ref.columns[0]: "SAMPLE_ID"})
    print(f"referencni tabulka: {len(ref)} vzorku")

    print("pocitam LULANem...")
    vysledky = spocitej(list(ref.SAMPLE_ID))
    print(f"spocitano: {len(vysledky)} vzorku")

    radky = []
    for sid, z in vysledky.items():
        radek = {"SAMPLE_ID": sid}
        radek.update(z)
        radky.append(radek)
    lulan = pd.DataFrame(radky)
    lulan.to_csv(VYSTUP, sep=";", index=False)
    print(f"ulozeno do {VYSTUP}")

    if args.jen_vypocet:
        return

    from porovnani_report import sestav_report  # noqa: E402
    vystup = (
        os.path.join(KOREN, "porovnani_metrik_MZB_meze-ARROW.html")
        if args.meze_arrow else None
    )
    sestav_report(
        ref, lulan, vystup=vystup,
        jen_hodnocene_sezony=not args.vsechny_sezony,
    )


if __name__ == "__main__":
    main()
