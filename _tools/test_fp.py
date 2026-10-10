"""Kontrola vypoctu fytoplanktonu na umele sestavene sezone.

V databazi zatim nejsou zadne FP vzorky, proto se sestavi testovaci sada
se znamym slozenim a vysledek se porovna s rucnim vypoctem podle metodiky.

Testuje se zejmena poradi vypoctu: metodika predepisuje zprumerovat HODNOTY
METRIK pres vegetacni sezonu a teprve z prumeru pocitat EQR. Protoze se EQR
orezava do <0, 1>, dava opacne poradi (prumer EQR z jednotlivych vzorku)
jiny vysledek - a test to ukazuje na konkretnich cislech.
"""
import os
import shutil
import sqlite3
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

TEST_DB = "/tmp/fp_test.db"
STRAHLER = 8

#: Vzorky sezony: (ID, datum, slozeni {taxon: pocet}, chlorofyl)
#: Slozeni je zvolene tak, aby se podily mezi vzorky vyrazne lisily.
SEZONA = [
    ("TESTFP_1_FP", "10.04.2020", {
        "Cyclotella distinguenda": 800,   # Bacillariophyceae
        "Microcystis aeruginosa": 20,     # Cyanophyceae
        "Scenedesmus acutus": 100,        # Chlorophyceae
        "Ceratium cornutum": 40,          # obrnenka - jina skupina
        "Neexistujici taxon xyz": 40,     # mimo seznam - patri do jmenovatele
    }, 8.0),
    ("TESTFP_2_FP", "15.07.2020", {
        "Cyclotella distinguenda": 400,
        "Microcystis aeruginosa": 200,
        "Scenedesmus acutus": 300,
        "Ceratium cornutum": 100,
    }, 45.0),
    ("TESTFP_3_FP", "20.09.2020", {
        "Cyclotella distinguenda": 300,
        "Microcystis aeruginosa": 380,
        "Scenedesmus acutus": 250,
        "Ceratium cornutum": 70,
    }, 70.0),
    # vzorek mimo vegetacni sezonu - do prumeru nesmi vstoupit
    ("TESTFP_4_FP", "05.12.2020", {
        "Cyclotella distinguenda": 900,
        "Microcystis aeruginosa": 10,
        "Scenedesmus acutus": 50,
        "Ceratium cornutum": 40,
    }, 3.0),
]

#: Meze podle Tab. 2 metodiky pro Strahler 8: (dolni, horni)
MEZE = {
    "FP01": (0.33, 0.85),
    "FP02": (0.3, 0.011),
    "FP03": (0.38, 0.12),
    "FP04": (98.0, 12.0),
}

SKUPINA_TAXONU = {
    "Cyclotella distinguenda": "FP01",
    "Microcystis aeruginosa": "FP02",
    "Scenedesmus acutus": "FP03",
}


def eqr(metrika, hodnota):
    lo, hi = MEZE[metrika]
    return min(1.0, max(0.0, (hodnota - lo) / (hi - lo)))


def priprav_databazi():
    shutil.copy(os.path.join(KOREN, "dtb", "LULAN_dtb_001.db"), TEST_DB)
    c = sqlite3.connect(TEST_DB)
    c.execute(
        "INSERT OR REPLACE INTO utvary (ID_UTVARU, NAZ_UTVARU, DILCI_POVODI,"
        " KATEGORIE, HMWB, VYSYCHAVY, BROD) VALUES"
        " ('TEST_FP','Testovaci utvar FP','TST','R','P','P','B')"
    )
    c.execute(
        "INSERT OR REPLACE INTO loc (KOD, VU, TOK, PROFIL, WGS84_LAT,"
        " WGS84_LON, STRAHLER, MNM) VALUES ('TESTFP','TEST_FP','Testovaci tok',"
        " 'profil', 50.0, 14.0, ?, 180)", (STRAHLER,)
    )
    c.execute("DELETE FROM samples WHERE SAMPLE_ID LIKE 'TESTFP%'")
    c.execute("DELETE FROM data WHERE sample LIKE 'TESTFP%'")

    for sid, datum, slozeni, chlorofyl in SEZONA:
        c.execute(
            "INSERT INTO samples (SAMPLE_ID, TYP, DATE, LOC_ID)"
            " VALUES (?,'FP',?,'TESTFP')", (sid, datum)
        )
        for jmeno, pocet in slozeni.items():
            c.execute("INSERT INTO data (sample, name, val) VALUES (?,?,?)",
                      (sid, jmeno, pocet))
        c.execute("INSERT INTO data (sample, name, val) VALUES (?,'IC0000',?)",
                  (sid, chlorofyl))
    c.commit()
    c.close()


def rucni_vypocet():
    """Spocita ocekavane hodnoty podle metodiky (prumer metrik, pak EQR)."""
    sezonni = [z for z in SEZONA if 3 <= int(z[1][3:5]) <= 10]

    po_vzorcich = []
    for _sid, _datum, slozeni, _chl in sezonni:
        celkem = sum(slozeni.values())
        podily = {m: 0.0 for m in ("FP01", "FP02", "FP03")}
        for jmeno, pocet in slozeni.items():
            metrika = SKUPINA_TAXONU.get(jmeno)
            if metrika:
                podily[metrika] += pocet / celkem
        po_vzorcich.append({m: round(v, 4) for m, v in podily.items()})

    prumery = {
        m: round(sum(p[m] for p in po_vzorcich) / len(po_vzorcich), 4)
        for m in ("FP01", "FP02", "FP03")
    }
    prumery["FP04"] = round(
        sum(z[3] for z in sezonni) / len(sezonni), 3
    )

    spravne_eqr = {m: eqr(m, prumery[m]) for m in MEZE}
    spravne_mmi = round(sum(spravne_eqr.values()) / 4, 3)

    # opacne poradi: EQR z kazdeho vzorku, pak prumer
    eqr_po_vzorcich = []
    for (_sid, _datum, _sl, chl), podily in zip(sezonni, po_vzorcich):
        e = [eqr(m, podily[m]) for m in ("FP01", "FP02", "FP03")]
        e.append(eqr("FP04", chl))
        eqr_po_vzorcich.append(sum(e) / 4)
    spatne_mmi = round(sum(eqr_po_vzorcich) / len(eqr_po_vzorcich), 3)

    return prumery, spravne_eqr, spravne_mmi, spatne_mmi


def main():
    priprav_databazi()

    from PyQt6.QtSql import QSqlDatabase          # noqa: E402
    from calc_index.common import vycisti_cache   # noqa: E402
    from calc_index.fp_reka import NAZVY          # noqa: E402
    import calc_indexes as ci                     # noqa: E402

    vycisti_cache()
    db = QSqlDatabase(TEST_DB)
    vysledky = {sid: ci.calc_indexes(sid, db) for sid, *_ in SEZONA}
    db.conn.commit()
    db.close()

    prumery, spravne_eqr, spravne_mmi, spatne_mmi = rucni_vypocet()
    vysledek = vysledky["TESTFP_2_FP"]

    print("\nSezona 2020, lokalita TESTFP, Strahler 8")
    print("Tri vzorky ve vegetacni sezone + jeden prosincovy (nema se pocitat)\n")

    print(f"{'metrika':10s} {'nazev':22s} {'prumer ocek.':>13s} "
          f"{'prumer spoc.':>13s} {'EQR ocek.':>10s} {'EQR spoc.':>10s}")
    print("-" * 84)
    chyby = 0
    for m in ("FP01", "FP02", "FP03", "FP04"):
        sp = vysledek.get(m)
        eq = vysledek.get(f"{m}_EQR")
        ok = (sp is not None and abs(sp - prumery[m]) < 1e-3
              and eq is not None and abs(eq - spravne_eqr[m]) < 1e-3)
        chyby += not ok
        print(f"{m:10s} {NAZVY[m]:22s} {prumery[m]:13.4f} {sp:13.4f} "
              f"{spravne_eqr[m]:10.4f} {eq:10.4f} {'' if ok else '  <-- NESEDI'}")

    mmi = vysledek.get("FP_CELKEM")
    ok = mmi is not None and abs(mmi - spravne_mmi) < 1e-3
    chyby += not ok
    print(f"\n{'MMI':10s} {'multimetrika':22s} {spravne_mmi:13.3f} {mmi:13.3f}"
          f" {'' if ok else '  <-- NESEDI'}")
    print(f"{'trida':10s} {'':22s} {'':13s} {str(vysledek.get('FP_CLASS')):>13s}")

    print(f"\nPoradi vypoctu ma vliv:")
    print(f"   spravne (prumer metrik -> EQR):  {spravne_mmi}")
    print(f"   chybne  (EQR -> prumer):         {spatne_mmi}")
    print(f"   rozdil:                          {abs(spravne_mmi - spatne_mmi):.3f}")

    print("\nVsechny vzorky sezony maji dostat shodny vysledek:")
    for sid, datum, *_ in SEZONA:
        v = vysledky[sid]
        print(f"   {sid:14s} {datum}  MMI={str(v.get('FP_CELKEM')):>6s}  "
              f"trida={str(v.get('FP_CLASS')):>5s}")

    sezonni_mmi = {vysledky[z[0]].get("FP_CELKEM") for z in SEZONA[:3]}
    if len(sezonni_mmi) != 1:
        print("   <-- NESEDI: vzorky sezony maji ruzny vysledek")
        chyby += 1
    if vysledky["TESTFP_4_FP"].get("FP_CELKEM") is not None:
        print("   <-- NESEDI: prosincovy vzorek se nemel vyhodnotit")
        chyby += 1

    print(f"\npoznamka: {vysledek.get('FP_POZN')}")
    print(f"\nchyb: {chyby}")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
