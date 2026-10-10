"""
Import kalibracnich dat metodiky vysychavych toku (MZB) z Excelu.

Sesit `LULAN_kontrola_MZB_vysychave.xlsx` obsahuje podkladova data, na
kterych se metodika hodnoceni vysychavych toku kalibrovala. Vsechny
vzorky pochazeji z vysychavych lokalit.

Listy sesitu:

    lokality   kod, nazev, souradnice S-JTSK, a k tomu abioticke
               parametry (nadm. vyska, Strahler, sklon, vzdalenost od
               pramene, plocha povodi). Ty se ZAMERNE NEIMPORTUJI -
               slouzi jako referencni hodnoty pro kontrolu vypoctu
               (viz `_tools/kontrola_abiotiky.py`). Kdyby se ulozily,
               kontrola by porovnavala hodnoty samy se sebou.
    vzorky     kod vzorku, kod lokality, datum, slozka
    data       siroka matice taxon x vzorek, prevadi se na dlouhy format
    vysledky   referencni hodnoty peti metrik, EQR (multimetrika
               vysychavych toku) a MB_CELKEM (hodnoceni podle klasicke
               metodiky tekoucich vod). Pro vysychave toky plati EQR.

Hodnoceni ma smysl jen u jarnich vzorku - podzimni sber metodika
nepouziva a referencni EQR u nich neni vyplnene.

Souradnice jsou navzdory nazvu sloupcu (`S42_X`, `S42_Y`) v S-JTSK
(EPSG:5514) - overeno prepoctem proti jiz ulozenym lokalitam.

Vzorky se ukladaji s `INTERMITTENT = 'TRUE'`, coz je od upravy
`registry.nacti_utvar()` dostacujici k tomu, aby se pocitaly podle
metodiky vysychavych toku.

Pouziti:
    python _tools/import_vysychave.py --rozbor          # jen vypis, nezapisuje
    python _tools/import_vysychave.py --spustit
    python _tools/import_vysychave.py --spustit --db /tmp/kopie.db

POZOR: `--spustit` zapisuje do databaze. Zavrete pred spustenim
aplikaci, jinak si dva zapisovatele mohou prekazet.
"""

import argparse
import collections
import os
import re
import sqlite3
import sys
from datetime import datetime

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools"))

VYCHOZI_XLSX = os.path.join(
    KOREN, "kontrola_vysledku", "LULAN_kontrola_MZB_vysychave.xlsx")
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

#: Prefix, kterym se odlisi importovane lokality od jiz existujicich.
#: Kody z Excelu jsou dost svebytne (PMO_JPPBG024, PLO_7, BIO_GRA),
#: prefix zajisti, ze se nesrazi s nicim v databazi.
PREFIX = "VYS_"

#: Slozka, do ktere vzorky patri.
SLOZKA = "MZB"

#: EPSG kod souradnic v sesitu.
EPSG_ZDROJ = 5514


def _bez_pripony(kod):
    """Odstrani priponu, kterou R pridava k duplicitnim nazvum ('...41')."""
    return re.sub(r"\.\.\.\d+$", "", str(kod))


def sezona(kod):
    """JARO / PODZIM podle nazvu vzorku."""
    m = re.search(r"_(JARO|PODZIM|PODZ)$", _bez_pripony(kod))
    if not m:
        return None
    return "JARO" if m.group(1) == "JARO" else "PODZIM"


#: Poradi sloupcu na listu `lokality`.
L_KOD, L_NAZEV, L_X, L_Y = 0, 1, 2, 3

#: Poradi sloupcu na listu `vzorky`.
V_KOD, V_LOKALITA, V_DATUM, V_TYP = 0, 1, 2, 3


def nacti_sesit(cesta):
    """Nacte vsechny ctyri listy.

    Returns:
        dict s klici lokality, vzorky, data, vysledky
    """
    import openpyxl

    wb = openpyxl.load_workbook(cesta, data_only=True, read_only=True)

    def list_radku(nazev):
        it = wb[nazev].iter_rows(values_only=True)
        hlavicka = list(next(it))
        return hlavicka, [list(r) for r in it]

    _, lokality = list_radku("lokality")
    _, vzorky = list_radku("vzorky")
    hlavicka_dat, matice = list_radku("data")
    hlavicka_vys, vysledky = list_radku("vysledky")

    return {
        "lokality": [r for r in lokality if r[0]],
        "vzorky": [r for r in vzorky if r[0]],
        "vzorky_v_matici": [str(x) for x in hlavicka_dat[1:] if x],
        "matice": [r for r in matice if r[0]],
        "vysledky_hlavicka": hlavicka_vys,
        "vysledky": [r for r in vysledky if r[0]],
    }


def prevod_souradnic(lokality):
    """Doplni WGS84 k souradnicim S-JTSK.

    Returns:
        dict {kod: (lat, lon)}; prazdny, kdyz pyproj neni k dispozici
    """
    try:
        import pyproj
    except ImportError:
        print("(pyproj není nainstalován, WGS84 se nedoplní)")
        return {}

    t = pyproj.Transformer.from_crs(
        f"EPSG:{EPSG_ZDROJ}", "EPSG:4326", always_xy=True)
    vysledek = {}
    for r in lokality:
        x, y = r[L_X], r[L_Y]
        if x is None or y is None:
            continue
        lon, lat = t.transform(float(x), float(y))
        vysledek[r[L_KOD]] = (round(lat, 8), round(lon, 8))
    return vysledek


def dlouhy_format(matice, vzorky_v_matici, prevod_nazvu=False):
    """Prevede sirokou matici taxon x vzorek na dlouhy format.

    Nuly se nezapisuji - v siroke matici znamenaji nepritomnost, ne
    zmereny nulovy pocet. Vsechny ostatni taxony se zapisuji, i kdyz
    je taxalist nezna; do vypoctu metrik sice nevstoupi, ale v databazi
    zustanou, takze po doplneni taxalistu staci prepocet.

    Args:
        prevod_nazvu: prevest nazvy na konvenci taxalistu podle
            `nazvy_vysychave.PREVOD`

    Returns:
        list trojic (taxon, vzorek, abundance)
    """
    preved = (lambda x: x)
    if prevod_nazvu:
        from nazvy_vysychave import preved  # noqa: F811

    radky = []
    for r in matice:
        taxon = preved(str(r[0]).strip())
        for i, vzorek in enumerate(vzorky_v_matici, start=1):
            if i >= len(r):
                break
            v = r[i]
            if isinstance(v, (int, float)) and v:
                radky.append((taxon, vzorek, float(v)))
    return radky


def rozbor(sesit, db_cesta, prevod_nazvu=False):
    """Vypise, co by se importovalo, a na co je potreba dat pozor."""
    lokality, vzorky = sesit["lokality"], sesit["vzorky"]
    dlouhe = dlouhy_format(
        sesit["matice"], sesit["vzorky_v_matici"], prevod_nazvu)

    print(f"lokality:  {len(lokality)}")
    print(f"vzorky:    {len(vzorky)}  "
          f"({dict(collections.Counter(sezona(r[V_KOD]) for r in vzorky))})")
    print(f"data:      {len(sesit['matice'])} taxonů × "
          f"{len(sesit['vzorky_v_matici'])} vzorků "
          f"→ {len(dlouhe)} řádků v dlouhém formátu")

    v_matici = set(sesit["vzorky_v_matici"])
    v_seznamu = {str(r[V_KOD]) for r in vzorky}
    if v_matici != v_seznamu:
        print(f"  !! matice a seznam vzorků se liší: "
              f"jen v matici {len(v_matici - v_seznamu)}, "
              f"jen v seznamu {len(v_seznamu - v_matici)}")

    kody = {r[L_KOD] for r in lokality}
    chybi = {r[V_LOKALITA] for r in vzorky} - kody
    if chybi:
        print(f"  !! vzorky odkazují na neznámé lokality: {sorted(chybi)[:5]}")

    # kolize s jiz ulozenymi zaznamy
    conn = sqlite3.connect(db_cesta)
    for tabulka, sloupec, hodnoty in (
            ("loc", "KOD", [PREFIX + r[L_KOD] for r in lokality]),
            ("samples", "SAMPLE_ID", [PREFIX + str(r[V_KOD]) for r in vzorky])):
        existujici = {r[0] for r in conn.execute(
            f"SELECT {sloupec} FROM {tabulka}")}
        kolize = [h for h in hodnoty if h in existujici]
        print(f"  {tabulka}: {len(kolize)} kódů už v databázi je"
              + (f" (např. {kolize[:3]})" if kolize else ""))

    # dohledatelnost taxonu
    taxalist = {r[0] for r in conn.execute("SELECT NAME FROM taxalist_MZB")}
    conn.close()
    celkem = sum(a for _, _, a in dlouhe)
    nezname = collections.Counter()
    for taxon, _, a in dlouhe:
        if taxon not in taxalist:
            nezname[taxon] += a
    print(f"\n  taxonů mimo taxalist_MZB: {len(nezname)} "
          f"({sum(nezname.values()) / celkem * 100:.2f} % abundance)")
    for t, a in nezname.most_common(10):
        print(f"     {a:9.0f}  {t}")
    return dlouhe


def zapis(sesit, db_cesta, prevod_nazvu=False):
    """Zapise lokality, vzorky a data do databaze."""
    lokality, vzorky = sesit["lokality"], sesit["vzorky"]
    wgs = prevod_souradnic(lokality)
    dlouhe = dlouhy_format(
        sesit["matice"], sesit["vzorky_v_matici"], prevod_nazvu)
    ted = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    conn = sqlite3.connect(db_cesta)
    try:
        with conn:
            # Abioticke parametry se zamerne nezapisuji - zustavaji NULL,
            # aby je slo dopocitat a porovnat s hodnotami ze sesitu.
            for r in lokality:
                kod = PREFIX + str(r[L_KOD])
                lat, lon = wgs.get(r[L_KOD], (None, None))
                conn.execute(
                    """
                    INSERT INTO loc (KOD, TOK, PROFIL, SJTSK_X, SJTSK_Y,
                                     WGS84_LAT, WGS84_LON, KATEGORIE, DTCH)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'R', ?)
                    ON CONFLICT(KOD) DO UPDATE SET
                        TOK = excluded.TOK, PROFIL = excluded.PROFIL,
                        SJTSK_X = excluded.SJTSK_X, SJTSK_Y = excluded.SJTSK_Y,
                        WGS84_LAT = excluded.WGS84_LAT,
                        WGS84_LON = excluded.WGS84_LON, DTCH = excluded.DTCH
                    """,
                    (kod, r[L_NAZEV], r[L_NAZEV], r[L_X], r[L_Y],
                     lat, lon, ted))

            for r in vzorky:
                datum = r[V_DATUM]
                if isinstance(datum, datetime):
                    datum = datum.strftime("%d.%m.%Y")
                conn.execute(
                    """
                    INSERT INTO samples (SAMPLE_ID, TYP, INTERMITTENT,
                                         DATE, LOC_ID, DTCH)
                    VALUES (?, ?, 'TRUE', ?, ?, ?)
                    ON CONFLICT(SAMPLE_ID) DO UPDATE SET
                        TYP = excluded.TYP,
                        INTERMITTENT = excluded.INTERMITTENT,
                        DATE = excluded.DATE, LOC_ID = excluded.LOC_ID,
                        DTCH = excluded.DTCH
                    """,
                    (PREFIX + str(r[V_KOD]), r[V_TYP] or SLOZKA, datum,
                     PREFIX + str(r[V_LOKALITA]), ted))

            vzorky_kody = [PREFIX + str(r[V_KOD]) for r in vzorky]
            conn.executemany(
                "DELETE FROM data WHERE sample = ?",
                [(k,) for k in vzorky_kody])
            conn.executemany(
                "INSERT INTO data (name, sample, val, DTCH) VALUES (?,?,?,?)",
                [(t, PREFIX + str(v), a, ted) for t, v, a in dlouhe])
    finally:
        conn.close()

    print(f"zapsáno: {len(lokality)} lokalit, {len(vzorky)} vzorků, "
          f"{len(dlouhe)} řádků dat")


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", default=VYCHOZI_XLSX)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--rozbor", action="store_true",
                   help="jen vypsat, co by se importovalo")
    p.add_argument("--spustit", action="store_true",
                   help="zapsat do databáze")
    p.add_argument("--nazvy", action="store_true",
                   help="převést názvy taxonů na konvenci taxalistu "
                        "(viz _tools/nazvy_vysychave.py)")
    args = p.parse_args()

    for cesta in (args.xlsx, args.db):
        if not os.path.exists(cesta):
            raise SystemExit(f"Soubor nenalezen: {cesta}")

    sesit = nacti_sesit(args.xlsx)
    if args.nazvy:
        print("názvy taxonů se převádějí na konvenci taxalistu\n")
    rozbor(sesit, args.db, args.nazvy)
    if args.spustit:
        print()
        zapis(sesit, args.db, args.nazvy)
    else:
        print("\nNic se nezapsalo. Zápis do databáze: přepínač --spustit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
