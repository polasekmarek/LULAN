"""
Jednorazove srovnani s mezemi, ktere u typu 2-1 pouziva ARROW.

Proc
----
U vsech 30 jarnich vzorku typu 2-1 sedi hodnota metriky RETI i Margalefovy
diverzity presne, ale jejich EQR se od ARROW lisi o konstantu. Zpetna
regrese EQR na hodnotu metriky dava meze, ktere ARROW pouzil, s R2 = 1,000:

    RETI      horni mez 0,86   (metodika Tab. 3 pro typ 2-1 uvadi 0,81)
    Margalef  horni mez 8,4    (metodika Tab. 3 pro typ 2-1 uvadi 7,7)

Obe hodnoty jsou presne ty, ktere Tab. 3 uvadi o radek niz - pro typ 3-1.

Co skript dela
--------------
Prepise meze POUZE V PAMETI a sestavi samostatny report. Databaze ani
vypocetni rutiny se nemeni - `mzb_perennial_broditelne.EQR_TABLE` se vraci
do puvodniho stavu jeste pred koncem behu.

Pouziti:
    python _tools/porovnani_meze_2_1.py
"""

import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))
sys.path.insert(0, os.path.join(KOREN, "_tools"))

#: Horni meze, ktere u typu 2-1 pouziva ARROW (= hodnoty typu 3-1).
MEZE_ARROW = {"MB03": 0.86, "MB05": 8.4}

VYSTUP = os.path.join(KOREN, "porovnani_metrik_MZB_meze_2-1.html")


def zamen_meze(tabulka):
    """Prepise horni meze typu 2-1 a vrati funkci, ktera zmenu vrati zpet."""
    puvodni = {}
    for klic, radek in tabulka.items():
        if klic[0] != "2-1":
            continue
        for metrika, mez in MEZE_ARROW.items():
            if metrika not in radek:
                continue
            puvodni[(klic, metrika)] = radek[metrika]
            dolni, _horni, invertovana, vaha = radek[metrika]
            radek[metrika] = (dolni, mez, invertovana, vaha)

    def vrat_zpet():
        for (klic, metrika), hodnota in puvodni.items():
            tabulka[klic][metrika] = hodnota

    return puvodni, vrat_zpet


def main():
    import pandas as pd

    from calc_index.mzb_perennial_broditelne import EQR_TABLE
    import porovnani_metrik as pm
    from porovnani_report import sestav_report

    zmeneno, vrat_zpet = zamen_meze(EQR_TABLE)
    print("Docasne zamenene meze (pouze v pameti):")
    for (klic, metrika), stara in sorted(zmeneno.items(), key=lambda x: str(x[0])):
        print(f"  typ {klic[0]}, sezona {klic[1]}, {metrika}: "
              f"horni mez {stara[1]} -> {MEZE_ARROW[metrika]}")

    try:
        ref = pd.read_csv(pm.REFERENCE, sep=";", encoding="utf-8-sig")
        ref = ref.rename(columns={ref.columns[0]: "SAMPLE_ID"})
        print(f"\nreferencni tabulka: {len(ref)} vzorku")

        print("pocitam LULANem...")
        vysledky = pm.spocitej(list(ref.SAMPLE_ID))
        print(f"spocitano: {len(vysledky)} vzorku")

        lulan = pd.DataFrame(
            [{"SAMPLE_ID": sid, **z} for sid, z in vysledky.items()]
        )
        lulan.to_csv(VYSTUP.replace(".html", ".csv"), sep=";", index=False)
        sestav_report(ref, lulan, vystup=VYSTUP, jen_hodnocene_sezony=True)
    finally:
        vrat_zpet()
        print("Meze v EQR_TABLE vraceny do puvodniho stavu.")


if __name__ == "__main__":
    main()
