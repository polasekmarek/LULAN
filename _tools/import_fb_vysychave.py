"""
Import kontrolnich dat fytobentosu vysychavych toku z Excelu.

Sesit `LULAN_kontrola_FB_vysychave.xlsx` ma pet listu, ale pouzitelny je
jen `orig`. Listy `data` a `vysledky` jsou proti sobe posunute - ve
`vysledky` je nazev vzorku vyplneny pouze u 120 jarnich vzorku a zbylych
108 radku ma prazdne jmeno, takze se s matici parovat nedaji. List
`orig` ma naproti tomu metadata, metriky i taxony na jednom radku.

Sloupce listu `orig`:

    Kod_Lokality_EKOSVYST   kod lokality
    loc_poradi              kod vzorku (pripona `...N` odlisuje duplicity)
    datum                   datum odberu
    Profil                  slovni popis lokality
    SAL, O2, sap            predpocitane metriky
    SLA_sens                citlivost podle Sladeckove
    dale                    siroka matice taxonu

Lokality jsou tytez, ktere uz naimportoval `import_vysychave.py` pro
makrozoobentos - z 85 lokalit je 84 shodnych. Souradnice sesit neuvadi,
takze se zaklada jen ta jedna chybejici, a to bez nich.

Vzorky se ukladaji s `INTERMITTENT = 'TRUE'` a `TYP = 'FB'`.

Pouziti:
    python _tools/import_fb_vysychave.py --rozbor
    python _tools/import_fb_vysychave.py --spustit
    python _tools/import_fb_vysychave.py --spustit --db /tmp/kopie.db

POZOR: `--spustit` zapisuje do databaze. Zavrete pred spustenim aplikaci.
"""

import argparse
import collections
import os
import sys
from datetime import datetime

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools"))

VYCHOZI_XLSX = os.path.join(
    KOREN, "kontrola_vysledku", "LULAN_kontrola_FB_vysychave.xlsx")
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

#: Stejny prefix jako u makrozoobentosu - lokality jsou tytez.
PREFIX = "VYS_"

#: Pocet sloupcu metadat na listu `orig` pred zacatkem matice taxonu.
META = 8

#: Poradi sloupcu metadat.
O_LOKALITA, O_VZOREK, O_DATUM, O_PROFIL, O_SAL, O_O2, O_SAP, O_SLA = range(8)

#: Mesice, ktere metodika povazuje za jarni. Referencni EQR je v sesitu
#: vyplnene prave a jen u techto vzorku.
JARNI_MESICE = (3, 4, 5)


def nacti_sesit(cesta):
    """Nacte list `orig`.

    Returns:
        dict s klici `taxony` (nazvy sloupcu matice) a `radky`
    """
    import openpyxl

    wb = openpyxl.load_workbook(cesta, data_only=True, read_only=True)
    it = wb["orig"].iter_rows(values_only=True)
    hlavicka = list(next(it))
    return {
        "taxony": [str(x).strip() for x in hlavicka[META:]],
        "radky": [list(r) for r in it if r[O_VZOREK]],
    }


def je_jarni(radek):
    """Jarni vzorek se pozna podle mesice odberu, ne podle nazvu."""
    datum = radek[O_DATUM]
    return isinstance(datum, datetime) and datum.month in JARNI_MESICE


def dlouhy_format(sesit):
    """Prevede sirokou matici na trojice (taxon, vzorek, abundance)."""
    taxony = sesit["taxony"]
    radky = []
    for r in sesit["radky"]:
        vzorek = str(r[O_VZOREK])
        for i, taxon in enumerate(taxony):
            hodnota = r[META + i] if META + i < len(r) else None
            if isinstance(hodnota, (int, float)) and hodnota:
                radky.append((taxon, vzorek, float(hodnota)))
    return radky


def rozbor(sesit, db_cesta):
    """Vypise, co by se importovalo."""
    import sqlite3

    radky = sesit["radky"]
    dlouhe = dlouhy_format(sesit)
    lokality = sorted({str(r[O_LOKALITA]) for r in radky})

    print(f"lokality:  {len(lokality)}")
    print(f"vzorky:    {len(radky)}  "
          f"(jarních {sum(1 for r in radky if je_jarni(r))})")
    print(f"data:      {len(sesit['taxony'])} taxonů "
          f"→ {len(dlouhe)} řádků v dlouhém formátu")

    conn = sqlite3.connect(db_cesta)
    existujici = {r[0] for r in conn.execute("SELECT KOD FROM loc")}
    nove = [k for k in lokality if PREFIX + k not in existujici]
    print(f"  lokalit už v databázi: {len(lokality) - len(nove)}, "
          f"nových: {len(nove)}" + (f" {nove}" if nove else ""))

    vzorky = {r[0] for r in conn.execute("SELECT SAMPLE_ID FROM samples")}
    kolize = [r for r in radky if PREFIX + str(r[O_VZOREK]) in vzorky]
    print(f"  vzorků už v databázi: {len(kolize)}")

    taxalist = {r[0] for r in conn.execute("SELECT NAME FROM taxalist_FB")}
    conn.close()
    celkem = sum(a for _, _, a in dlouhe)
    nezname = collections.Counter()
    for taxon, _, a in dlouhe:
        if taxon not in taxalist:
            nezname[taxon] += a
    print(f"\n  taxonů mimo taxalist_FB: {len(nezname)} "
          f"({sum(nezname.values()) / celkem * 100:.2f} % abundance)")
    for t, a in nezname.most_common(8):
        print(f"     {a:8.0f}  {t}")
    return dlouhe


def zapis(sesit, db_cesta):
    """Zapise lokality, vzorky a data do databaze."""
    import sqlite3

    radky = sesit["radky"]
    dlouhe = dlouhy_format(sesit)
    lokality = sorted({str(r[O_LOKALITA]) for r in radky})
    profily = {str(r[O_LOKALITA]): r[O_PROFIL] for r in radky}
    ted = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    conn = sqlite3.connect(db_cesta)
    try:
        with conn:
            # Lokality, ktere uz zalozil import makrozoobentosu, se
            # nechavaji byt - maji souradnice, ktere tenhle sesit neuvadi.
            for kod in lokality:
                conn.execute(
                    """
                    INSERT INTO loc (KOD, TOK, PROFIL, KATEGORIE, DTCH)
                    VALUES (?, ?, ?, 'R', ?)
                    ON CONFLICT(KOD) DO NOTHING
                    """,
                    (PREFIX + kod, profily.get(kod), profily.get(kod), ted))

            for r in radky:
                datum = r[O_DATUM]
                if isinstance(datum, datetime):
                    datum = datum.strftime("%d.%m.%Y")
                conn.execute(
                    """
                    INSERT INTO samples (SAMPLE_ID, TYP, INTERMITTENT,
                                         DATE, LOC_ID, DTCH)
                    VALUES (?, 'FB', 'TRUE', ?, ?, ?)
                    ON CONFLICT(SAMPLE_ID) DO UPDATE SET
                        TYP = excluded.TYP,
                        INTERMITTENT = excluded.INTERMITTENT,
                        DATE = excluded.DATE, LOC_ID = excluded.LOC_ID,
                        DTCH = excluded.DTCH
                    """,
                    (PREFIX + str(r[O_VZOREK]), datum,
                     PREFIX + str(r[O_LOKALITA]), ted))

            kody = [PREFIX + str(r[O_VZOREK]) for r in radky]
            conn.executemany("DELETE FROM data WHERE sample = ?",
                             [(k,) for k in kody])
            conn.executemany(
                "INSERT INTO data (name, sample, val, DTCH) VALUES (?,?,?,?)",
                [(t, PREFIX + v, a, ted) for t, v, a in dlouhe])
    finally:
        conn.close()

    print(f"zapsáno: {len(lokality)} lokalit, {len(radky)} vzorků, "
          f"{len(dlouhe)} řádků dat")


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", default=VYCHOZI_XLSX)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--rozbor", action="store_true")
    p.add_argument("--spustit", action="store_true",
                   help="zapsat do databáze")
    args = p.parse_args()

    for cesta in (args.xlsx, args.db):
        if not os.path.exists(cesta):
            raise SystemExit(f"Soubor nenalezen: {cesta}")

    sesit = nacti_sesit(args.xlsx)
    rozbor(sesit, args.db)
    if args.spustit:
        print()
        zapis(sesit, args.db)
    else:
        print("\nNic se nezapsalo. Zápis do databáze: přepínač --spustit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
