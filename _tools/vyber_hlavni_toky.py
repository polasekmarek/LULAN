"""
Vybere z hrubeho cleneni vodnich toku hlavni toky CR.

Vstupem je vrstva `A03_Vodni_tok_HU` (hrube cleneni useku vodnich toku,
DIBAVOD / VUV TGM), vystupem novy shapefile jen s nejvetsimi toky.
Slouzi jako podklad pod mapku polohy lokality (`src/mapa_lokalit.py`),
kde samotny obrys statu bez rek nedava dost oporu pro odhad, kde bod lezi.

Prevod souradnic
----------------
Zdroj je v S-JTSK Krovak East North (EPSG:5514), vystup se prevadi do
Pulkovo 1942 / Gauss-Kruger pasmo 3 (EPSG:28403) - v tom je vrstva
hranic `hrcr_S42.shp` i sloupce `loc.S42_X` a `loc.S42_Y`. Mapka pak
kresli obrys, reky i bod ve stejnem systemu bez dalsiho prepoctu.

Zapis shapefilu
---------------
Zamerne bez knihovny pyshp - polyliniovy shapefile ma stejnou strukturu
zaznamu jako polygonovy, ktery uz umi cist `mapa_lokalit`, takze staci
par desitek radku se `struct`. Aplikace tim nezisakva dalsi zavislost.

Pouziti:
    python _tools/vyber_hlavni_toky.py --vstup /cesta/A03_Vodni_tok_HU.shp
    python _tools/vyber_hlavni_toky.py --vstup ... --vystup jina_cesta.shp
"""

import argparse
import os
import struct
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VYCHOZI_VYSTUP = os.path.join(KOREN, "src", "GIS", "hlavni_toky_S42.shp")

#: Typ geometrie "PolyLine" v hlavicce shapefilu.
TYP_POLYLINE = 3

#: Souradnicove systemy: zdroj a cil.
CRS_ZDROJ = "EPSG:5514"     # S-JTSK Krovak East North
CRS_CIL = "EPSG:28403"      # Pulkovo 1942 / GK pasmo 3

#: Obsah `.prj` pro vystup - shodny s vrstvou hranic `hrcr_S42.prj`.
PRJ_CIL = (
    'PROJCS["Pulkovo_1942_GK_Zone_3",GEOGCS["GCS_Pulkovo_1942",'
    'DATUM["D_Pulkovo_1942",SPHEROID["Krasovsky_1940",6378245.0,298.3]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Gauss_Kruger"],PARAMETER["False_Easting",3500000.0],'
    'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",15.0],'
    'PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",0.0],'
    'UNIT["Meter",1.0]]'
)

#: Nazvy toku, ktere se do vystupu prevezmou. Porovnava se presne, aby
#: se nepribraly pritoky s podobnym jmenem - "Morava" ano, "Moravanka"
#: ne, "Otava" ano, "Rotava" ne.
#:
#: Divoka a Ticha Orlice jsou v seznamu proto, ze samotna Orlice je
#: pod tim jmenem jen 33 km od jejich soutoku po usti do Labe; bez
#: zdrojnic by na mape vypadala jako krcek. Ostatni pritoky s vlastnim
#: jmenem (Vsetinska a Roznovska Becva, Tepla a Studena Vltava,
#: Moravska Sazava, Moravska Dyje) se nevybiraji - jako samostatne
#: toky by mapku zahltily.
HLAVNI_TOKY = (
    "Vltava", "Labe", "Morava", "Odra", "Dyje", "Berounka", "Jihlava",
    "Bečva", "Sázava", "Ohře", "Střela", "Mže", "Radbuza", "Úhlava",
    "Úslava", "Jizera", "Orlice", "Divoká Orlice", "Tichá Orlice",
    "Svratka", "Lužnice", "Otava",
)

#: Sloupec s nazvem toku v atributove tabulce.
SLOUPEC_NAZVU = "NAZ_TOK"


def cti_dbf(cesta, kodovani="cp1250"):
    """Nacte atributovou tabulku shapefilu.

    Returns:
        list dictu, jeden na zaznam, v poradi geometrii
    """
    with open(cesta, "rb") as f:
        hlavicka = f.read(32)
        pocet, delka_hlavicky, delka_zaznamu = struct.unpack(
            "<I H H", hlavicka[4:12])

        pole = []
        while True:
            popis = f.read(32)
            if popis[0:1] in (b"\r", b""):
                break
            pole.append((
                popis[:11].split(b"\x00")[0].decode(kodovani),
                popis[11:12].decode(kodovani),
                popis[16],
            ))

        f.seek(delka_hlavicky)
        zaznamy = []
        for _ in range(pocet):
            radek = f.read(delka_zaznamu)
            if len(radek) < delka_zaznamu:
                break
            posun = 1  # prvni bajt je priznak smazani
            zaznam = {}
            for nazev, _typ, delka in pole:
                zaznam[nazev] = radek[posun:posun + delka].decode(
                    kodovani).strip()
                posun += delka
            zaznamy.append(zaznam)
    return zaznamy


def cti_linie(cesta):
    """Nacte polylinie ze shapefilu.

    Returns:
        list zaznamu; kazdy je list casti, kazda cast list bodu (x, y)
    """
    with open(cesta, "rb") as f:
        hlavicka = f.read(100)
        if struct.unpack(">i", hlavicka[0:4])[0] != 9994:
            raise ValueError("Soubor není ESRI shapefile.")
        (typ,) = struct.unpack("<i", hlavicka[32:36])
        if typ != TYP_POLYLINE:
            raise ValueError(
                f"Očekáván polyliniový shapefile (typ {TYP_POLYLINE}), "
                f"nalezen typ {typ}.")

        zaznamy = []
        while True:
            zahlavi = f.read(8)
            if len(zahlavi) < 8:
                break
            _cislo, delka = struct.unpack(">ii", zahlavi)
            obsah = f.read(delka * 2)
            if len(obsah) < delka * 2:
                break
            if struct.unpack("<i", obsah[0:4])[0] != TYP_POLYLINE:
                zaznamy.append([])   # prazdna geometrie
                continue

            pocet_casti, pocet_bodu = struct.unpack("<ii", obsah[36:44])
            zacatky = struct.unpack(
                f"<{pocet_casti}i", obsah[44:44 + 4 * pocet_casti])
            posun = 44 + 4 * pocet_casti
            body = struct.unpack(
                f"<{2 * pocet_bodu}d", obsah[posun:posun + 16 * pocet_bodu])

            casti = []
            for i, zacatek in enumerate(zacatky):
                konec = zacatky[i + 1] if i + 1 < pocet_casti else pocet_bodu
                casti.append([
                    (body[2 * j], body[2 * j + 1])
                    for j in range(zacatek, konec)
                ])
            zaznamy.append(casti)
    return zaznamy


def preved(zaznamy):
    """Prevede souradnice ze zdrojoveho systemu do ciloveho."""
    import pyproj

    prevod = pyproj.Transformer.from_crs(CRS_ZDROJ, CRS_CIL, always_xy=True)
    vysledek = []
    for casti in zaznamy:
        nove = []
        for cast in casti:
            if not cast:
                continue
            xs, ys = prevod.transform(
                [b[0] for b in cast], [b[1] for b in cast])
            nove.append(list(zip(xs, ys)))
        vysledek.append(nove)
    return vysledek


def _zaznam_shp(cislo, casti):
    """Sestavi jeden zaznam SHP vcetne osmibajtoveho zahlavi."""
    body = [b for cast in casti for b in cast]
    xs = [b[0] for b in body]
    ys = [b[1] for b in body]

    zacatky, poradi = [], 0
    for cast in casti:
        zacatky.append(poradi)
        poradi += len(cast)

    obsah = struct.pack("<i", TYP_POLYLINE)
    obsah += struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
    obsah += struct.pack("<ii", len(casti), len(body))
    obsah += struct.pack(f"<{len(zacatky)}i", *zacatky)
    for x, y in body:
        obsah += struct.pack("<2d", x, y)

    zahlavi = struct.pack(">ii", cislo, len(obsah) // 2)
    return zahlavi + obsah, len(obsah) // 2


def _hlavicka_shp(delka_slov, rozsah):
    """Sestavi stobajtovou hlavicku SHP nebo SHX."""
    h = struct.pack(">i", 9994) + b"\x00" * 20
    h += struct.pack(">i", delka_slov)
    h += struct.pack("<ii", 1000, TYP_POLYLINE)
    h += struct.pack("<4d", *rozsah)
    h += struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)   # Z a M se nepouzivaji
    return h


def zapis_shapefile(cesta, geometrie, nazvy, kodovani="cp1250"):
    """Zapise SHP, SHX, DBF a PRJ.

    Args:
        geometrie: list zaznamu (list casti, kazda list bodu)
        nazvy: list nazvu toku, stejne dlouhy jako `geometrie`
    """
    zaklad = os.path.splitext(cesta)[0]
    body = [b for casti in geometrie for cast in casti for b in cast]
    rozsah = (min(b[0] for b in body), min(b[1] for b in body),
              max(b[0] for b in body), max(b[1] for b in body))

    zaznamy, rejstrik, posun = [], [], 50   # 100 B hlavicky = 50 slov
    for i, casti in enumerate(geometrie, start=1):
        data, delka = _zaznam_shp(i, casti)
        zaznamy.append(data)
        rejstrik.append(struct.pack(">ii", posun, delka))
        posun += delka + 4                  # 8 B zahlavi = 4 slova

    with open(zaklad + ".shp", "wb") as f:
        f.write(_hlavicka_shp(posun, rozsah))
        for data in zaznamy:
            f.write(data)

    with open(zaklad + ".shx", "wb") as f:
        f.write(_hlavicka_shp(50 + 4 * len(rejstrik), rozsah))
        for polozka in rejstrik:
            f.write(polozka)

    # DBF s jedinym sloupcem - nazev toku
    sirka = 50
    hlavicka = struct.pack(
        "<BBBBIHH", 0x03, 126, 1, 1, len(nazvy), 32 + 32 + 1, 1 + sirka)
    hlavicka += b"\x00" * 20
    pole = (SLOUPEC_NAZVU.encode("ascii").ljust(11, b"\x00") + b"C"
            + b"\x00" * 4 + bytes([sirka]) + b"\x00" * 15)
    with open(zaklad + ".dbf", "wb") as f:
        f.write(hlavicka + pole + b"\r")
        for nazev in nazvy:
            f.write(b" " + nazev.encode(kodovani, "replace").ljust(sirka)[:sirka])
        f.write(b"\x1a")

    with open(zaklad + ".prj", "w", encoding="ascii") as f:
        f.write(PRJ_CIL)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vstup", required=True,
                   help="cesta k A03_Vodni_tok_HU.shp")
    p.add_argument("--vystup", default=VYCHOZI_VYSTUP)
    args = p.parse_args()

    dbf = os.path.splitext(args.vstup)[0] + ".dbf"
    for cesta in (args.vstup, dbf):
        if not os.path.exists(cesta):
            raise SystemExit(f"Soubor nenalezen: {cesta}")

    atributy = cti_dbf(dbf)
    geometrie = cti_linie(args.vstup)
    if len(atributy) != len(geometrie):
        raise SystemExit(
            f"DBF má {len(atributy)} záznamů, SHP {len(geometrie)} — "
            "vrstva je nekonzistentní.")

    hledane = set(HLAVNI_TOKY)
    vybrane, nazvy = [], []
    for atr, casti in zip(atributy, geometrie):
        nazev = atr.get(SLOUPEC_NAZVU, "")
        if nazev in hledane and casti:
            vybrane.append(casti)
            nazvy.append(nazev)

    if not vybrane:
        raise SystemExit("Nevybral se žádný úsek — zkontrolujte názvy toků.")

    import collections
    pocty = collections.Counter(nazvy)
    chybi = [t for t in HLAVNI_TOKY if t not in pocty]
    print(f"vybráno {len(vybrane)} úseků z {len(geometrie)}")
    for tok in HLAVNI_TOKY:
        print(f"   {tok:10s} {pocty.get(tok, 0):4d} úseků")
    if chybi:
        print(f"\n  !! ve vrstvě nenalezeno: {', '.join(chybi)}")

    prevedene = preved(vybrane)
    zapis_shapefile(args.vystup, prevedene, nazvy)
    print(f"\nuloženo do {args.vystup}")
    for pripona in (".shp", ".shx", ".dbf", ".prj"):
        soubor = os.path.splitext(args.vystup)[0] + pripona
        print(f"   {os.path.basename(soubor):24s} "
              f"{os.path.getsize(soubor) / 1024:8.0f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
