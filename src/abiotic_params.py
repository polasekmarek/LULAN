"""
Doplnovani abiotickych parametru lokalit (tabulka `loc`).

Modul dopocitava z dostupnych zdroju parametry, ktere metodiky potrebuji
pro zarazeni lokality do typu a pro predikcni model B-index:

    souradnice   S42_X, S42_Y, SJTSK_X, SJTSK_Y, UTM_X, UTM_Y
                 prepocteny z WGS84 pomoci pyproj
    MNM          nadmorska vyska z digitalniho modelu reliefu CUZK (DMR 5G)
    STRAHLER     Strahleruv rad
    UMORI        1 Labe, 2 Odra, 3 Dunaj
    KM_OD_PRAM   vzdalenost od pramene [km] podel osy toku
    PLOCHA_POV   plocha povodi nad lokalitou [km2]
    SLOPE        podelny sklon toku [promile] z DMR podel osy toku

Ctyri parametry - STRAHLER, UMORI, KM_OD_PRAM a PLOCHA_POV - se ctou
z odvozene ricni site `dtb/ricni_sit.db` (modul `ricni_sit`), kterou
sestavuje `_tools/gen_ricni_sit.py`. Drivejsi verze je pocitala primo nad
shapefily pres geopandas; bylo to pomale (minuty na davku) a plochu povodi
to bez externi vrstvy neumelo vubec. Dotaz do site trva ~20 ms na bod
a nepotrebuje zadnou GIS knihovnu.

POZOR na S42: predikcni model B-index ocekava souradnice v Gauss-Krugerove
zobrazeni pasma 3 (EPSG:28403, tj. X kolem 3 300 000 - 3 700 000,
Y kolem 5 400 000 - 5 700 000). Prave tyto sloupce byly v databazi prazdne,
takze B-index (metrika MB07) nesel spocitat pro zadny vzorek.

Zavislosti:
    pyproj      povinne (prepocet souradnic)
    requests    pro nadmorskou vysku z online sluzby CUZK (MNM, SLOPE)

Pouziti z prikazove radky:
    python abiotic_params.py --db dtb/LULAN_dtb_001.db --vse
    python abiotic_params.py --db dtb/LULAN_dtb_001.db --parametry souradnice mnm
    python abiotic_params.py --db dtb/LULAN_dtb_001.db --import-csv plochy.csv
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time

# --- volitelne zavislosti -------------------------------------------------
try:
    import pyproj
except ImportError:  # pragma: no cover
    pyproj = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

# ---------------------------------------------------------------------------
# Konfigurace
# ---------------------------------------------------------------------------

#: Adresar s GIS vrstvami relativne k tomuto souboru. Vrstvy same uz tento
#: modul necte - jsou vstupem pro `_tools/gen_ricni_sit.py`, ktery z nich
#: sestavuje `dtb/ricni_sit.db`.
GIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GIS")

#: Sluzby CUZK pro dotaz na nadmorskou vysku, v poradi podle presnosti.
#: DMR 5G ma uplnou stredni chybu vysky 0,18 m v terenu, DMR 4G 0,3 m;
#: 4G je zaloha pro pripad, ze 5G neni pro dane misto k dispozici.
DMR_URLS = (
    "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer/identify",
    "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr4g/ImageServer/identify",
)
DMR_URL = DMR_URLS[0]

#: Prodleva mezi dotazy na sluzbu CUZK [s], aby nedoslo k zahlceni serveru.
DMR_PRODLEVA = 0.2

#: Souradnicove systemy.
CRS_WGS84 = "EPSG:4326"
CRS_S42 = "EPSG:28403"     # Pulkovo 1942 / Gauss-Kruger pasmo 3 - vstup B-indexu
CRS_SJTSK = "EPSG:5514"    # S-JTSK / Krovak East North
CRS_UTM = "EPSG:32633"     # WGS 84 / UTM zona 33N

#: Maximalni vzdalenost bodu od osy toku, do ktere se prirazeni povazuje
#: za duveryhodne [m].
MAX_VZDALENOST_OD_TOKU = 500

#: Delka useku toku, na kterem se meri podelny sklon [m].
USEK_SKLONU = 400

#: Pocet bodu, ve kterych se podel useku odecita vyska pro vypocet sklonu.
#: Vic nez dva body proto, ze jednotlivy odecet z DMR muze padnout na
#: brehovou hranu nebo most; regrese pres radu bodu je proti tomu odolna.
VZORKU_SKLONU = 9

#: Vsechny podporovane parametry v poradi, v jakem se maji dopocitavat
#: (souradnice musi byt prvni - ostatni je pouzivaji).
PARAMETRY = ["souradnice", "mnm", "umori", "strahler", "km_od_pram",
             "plocha_pov", "slope"]


#: Zdroje dat, ze kterych se jednotlive parametry odvozuji.
#: (nazev, spravce, licence, url, ktere parametry z nej pochazeji)
ZDROJE_DAT = (
    (
        "DIBAVOD – Digitální báze vodohospodářských dat",
        "Výzkumný ústav vodohospodářský T. G. Masaryka, v. v. i.",
        "© VÚV TGM, v. v. i.",
        "https://www.dibavod.cz",
        "říční síť, názvy a identifikátory toků, Strahlerův řád, "
        "vzdálenost od pramene, vrstva hlavních toků v mapovém náhledu",
    ),
    (
        "Rozvodnice základních ploch povodí 4. řádu",
        "Český hydrometeorologický ústav",
        "CC BY 4.0",
        "https://data.gov.cz",
        "plocha povodí, číslo hydrologického pořadí, úmoří",
    ),
    (
        "ZABAGED® – Základní báze geografických dat ČR",
        "Český úřad zeměměřický a katastrální",
        "CC BY 4.0 – „ČÚZK, 2026“",
        "https://geoportal.cuzk.gov.cz",
        "podklad, ze kterého jsou DIBAVOD i rozvodnice odvozeny",
    ),
    (
        "DMR 5G / DMR 4G – digitální model reliéfu ČR",
        "Český úřad zeměměřický a katastrální",
        "CC BY 4.0 – „ČÚZK, 2026“",
        "https://geoportal.cuzk.gov.cz",
        "nadmořská výška, podélný sklon toku",
    ),
)

#: Citace, kterou pro sva data predepisuje VUV TGM.
CITACE_DIBAVOD = (
    "FOJTÍK, T., JAŠÍKOVÁ, L., KURFIŘTOVÁ, J., MAKOVCOVÁ, M., "
    "MAŤAŠOVSKÁ, V., MAYER, P., NOVÁKOVÁ, H., ZAVŘELOVÁ, J. a ZBOŘIL, A. "
    "GIS a kartografie ve VÚV TGM. Vodohospodářské technicko-ekonomické "
    "informace, 2022, roč. 64, č. 1, str. 47–52. ISSN 0322-8916."
)

#: Upozorneni, ktere musi uzivatel videt pred spustenim dopoctu.
UPOZORNENI = (
    "Dopočet abiotických parametrů je <b>pomocná funkce</b>. Hodnoty jsou "
    "odvozené automaticky z veřejných geografických vrstev a "
    "<b>nejsou zaručeně správné</b>.<br><br>"
    "<b>Dopočtené hodnoty vždy zkontrolujte.</b> Pro oficiální hodnocení "
    "je namístě nechat parametry odvodit GIS specialistou a zadat je "
    "ručně. Autoři aplikace za správnost odvozených hodnot neručí."
)


def popis_zdroju_html():
    """Vrati HTML s prehledem zdroju, licenci a upozornenim."""
    radky = [
        "<p>Parametry se odvozují z těchto podkladů:</p>",
        "<table cellpadding='4' cellspacing='0' width='100%'>",
        "<tr><th align='left'>Vrstva</th><th align='left'>Správce</th>"
        "<th align='left'>Licence</th></tr>",
    ]
    for nazev, spravce, licence, url, k_cemu in ZDROJE_DAT:
        radky.append(
            f"<tr><td valign='top'><b>{nazev}</b><br>"
            f"<span style='color:#555'>{k_cemu}</span><br>"
            f"<a href='{url}'>{url}</a></td>"
            f"<td valign='top'>{spravce}</td>"
            f"<td valign='top'>{licence}</td></tr>"
        )
    radky.append("</table>")
    radky.append(f"<p><b>Citace DIBAVOD:</b><br>{CITACE_DIBAVOD}</p>")
    radky.append("<hr>")
    radky.append(f"<p>{UPOZORNENI}</p>")
    return "\n".join(radky)


class ChybejiciZavislost(RuntimeError):
    """Vyvolana, kdyz pro dany parametr chybi potrebna knihovna nebo vrstva."""


# ---------------------------------------------------------------------------
# Pomocne funkce
# ---------------------------------------------------------------------------

def nacti_lokality(conn, jen_chybejici_sloupce=None):
    """Nacte lokality s platnymi WGS84 souradnicemi.

    Args:
        jen_chybejici_sloupce: seznam sloupcu; vrati jen lokality, kde je
            alespon jeden z nich prazdny. None = vsechny lokality.

    Returns:
        list dictu {KOD, TOK, WGS84_LAT, WGS84_LON, ...}
    """
    podminka = "WGS84_LAT IS NOT NULL AND WGS84_LON IS NOT NULL"
    if jen_chybejici_sloupce:
        chybi = " OR ".join(f"{s} IS NULL" for s in jen_chybejici_sloupce)
        podminka += f" AND ({chybi})"

    conn.row_factory = sqlite3.Row
    radky = conn.execute(f"SELECT * FROM loc WHERE {podminka}").fetchall()
    return [dict(r) for r in radky]


def _uloz(conn, kod, hodnoty):
    """Zapise vypoctene hodnoty do tabulky loc pro danou lokalitu."""
    if not hodnoty:
        return
    sety = ", ".join(f"{k} = ?" for k in hodnoty)
    conn.execute(
        f"UPDATE loc SET {sety} WHERE KOD = ?", (*hodnoty.values(), kod)
    )


# ---------------------------------------------------------------------------
# 1. Souradnice
# ---------------------------------------------------------------------------

def prepocti_souradnice(lokality):
    """Prepocte WGS84 souradnice do S-42, S-JTSK a UTM 33N.

    Returns:
        dict {KOD: {S42_X, S42_Y, SJTSK_X, SJTSK_Y, UTM_X, UTM_Y}}
    """
    if pyproj is None:
        raise ChybejiciZavislost("Pro prepocet souradnic je potreba knihovna pyproj")

    prevody = {
        ("S42_X", "S42_Y"): pyproj.Transformer.from_crs(
            CRS_WGS84, CRS_S42, always_xy=True
        ),
        ("SJTSK_X", "SJTSK_Y"): pyproj.Transformer.from_crs(
            CRS_WGS84, CRS_SJTSK, always_xy=True
        ),
        ("UTM_X", "UTM_Y"): pyproj.Transformer.from_crs(
            CRS_WGS84, CRS_UTM, always_xy=True
        ),
    }

    vysledky = {}
    for loc in lokality:
        lon, lat = loc["WGS84_LON"], loc["WGS84_LAT"]
        hodnoty = {}
        for (sx, sy), prevod in prevody.items():
            x, y = prevod.transform(lon, lat)
            hodnoty[sx] = round(x, 2)
            hodnoty[sy] = round(y, 2)
        vysledky[loc["KOD"]] = hodnoty
    return vysledky


# ---------------------------------------------------------------------------
# 2. Nadmorska vyska (DMR 4G)
# ---------------------------------------------------------------------------

def _vyska_z_dmr(x_sjtsk, y_sjtsk, timeout=10):
    """Dotaz na sluzbu CUZK DMR 4G. Vraci vysku v metrech nebo None."""
    if requests is None:
        raise ChybejiciZavislost("Pro dotaz na DMR 4G je potreba knihovna requests")

    parametry = {
        "f": "json",
        "geometry": f"{x_sjtsk},{y_sjtsk}",
        "geometryType": "esriGeometryPoint",
        "sr": 5514,
        "imageDisplay": "1,1,96",
        "returnGeometry": "false",
    }
    posledni = None
    for url in DMR_URLS:
        try:
            r = requests.get(url, params=parametry, timeout=timeout)
            r.raise_for_status()
            hodnota = r.json().get("value")
            if hodnota not in (None, "", "NoData"):
                return float(hodnota)
        except Exception as e:  # noqa: BLE001
            posledni = e
    if posledni is not None:
        print(f"  [MNM] chyba dotazu pro ({x_sjtsk:.0f}, {y_sjtsk:.0f}): {posledni}")
    return None


def doplnit_mnm(lokality, souradnice=None, progress=None):
    """Ziska nadmorskou vysku pro kazdou lokalitu z DMR 4G.

    Args:
        souradnice: vysledek prepocti_souradnice(); pokud None, pouziji se
            hodnoty SJTSK_X/SJTSK_Y primo z databaze

    Returns:
        dict {KOD: {'MNM': int}}
    """
    vysledky = {}
    for i, loc in enumerate(lokality, 1):
        kod = loc["KOD"]
        s = (souradnice or {}).get(kod, {})
        x = s.get("SJTSK_X", loc.get("SJTSK_X"))
        y = s.get("SJTSK_Y", loc.get("SJTSK_Y"))
        if x is None or y is None:
            continue

        vyska = _vyska_z_dmr(x, y)
        if vyska is not None:
            vysledky[kod] = {"MNM": int(round(vyska))}
        if progress:
            progress(i, len(lokality), f"MNM {kod}")
        time.sleep(DMR_PRODLEVA)
    return vysledky


# ---------------------------------------------------------------------------
# 3. Parametry z odvozene ricni site
#    (STRAHLER, UMORI, KM_OD_PRAM, PLOCHA_POV)
# ---------------------------------------------------------------------------

def _popis_lokalit(lokality, progress=None, popis=""):
    """Prichyti lokality k ricni siti a vrati popis kazdeho bodu.

    Sit se otevira jednou pro celou davku - kazdy dotaz je jen hledani
    v R-tree indexu.

    Returns:
        dict {KOD: popis_bodu}
    """
    try:
        from ricni_sit import RicniSit
    except ImportError as e:  # pragma: no cover
        raise ChybejiciZavislost(f"Modul ricni_sit nelze nacist: {e}") from e

    try:
        sit = RicniSit()
    except FileNotFoundError as e:
        raise ChybejiciZavislost(str(e)) from e

    vysledky = {}
    try:
        for i, loc in enumerate(lokality, 1):
            lat, lon = loc.get("WGS84_LAT"), loc.get("WGS84_LON")
            if lat in (None, "") or lon in (None, ""):
                continue
            try:
                udaje = sit.popis_bodu(float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            if udaje.get("usek_id") is None:
                print(f"  [{popis}] {loc['KOD']}: {udaje.get('poznamka')}")
                continue
            if udaje["odsazeni"] > MAX_VZDALENOST_OD_TOKU:
                print(
                    f"  [{popis}] {loc['KOD']}: nejbližší tok je "
                    f"{udaje['odsazeni']:.0f} m daleko - přeskočeno"
                )
                continue
            vysledky[loc["KOD"]] = udaje
            if progress:
                progress(i, len(lokality), f"{popis} {loc['KOD']}")
    finally:
        sit.zavri()
    return vysledky


def _ze_site(lokality, klic_site, sloupec, prevod=float, progress=None):
    """Obecny prevod jedne veliciny z ricni site na hodnoty do tabulky."""
    vysledky = {}
    for kod, udaje in _popis_lokalit(lokality, progress, sloupec).items():
        hodnota = udaje.get(klic_site)
        if hodnota is None:
            continue
        try:
            vysledky[kod] = {sloupec: prevod(hodnota)}
        except (TypeError, ValueError):
            continue
    return vysledky


def doplnit_umori(lokality, progress=None):
    """Umori podle cisla hydrologickeho poradi rozvodnice.

    Returns:
        dict {KOD: {'UMORI': int}}  (1 = Labe, 2 = Odra, 3 = Dunaj)
    """
    return _ze_site(lokality, "umori", "UMORI", int, progress)


def doplnit_strahler(lokality, progress=None):
    """Strahleruv rad nejblizsiho useku toku.

    Cte se z atributu vrstvy, nepocita se ze site - rad zavisi na hustote
    site, takze prepocet z jineho podkladu dava jina cisla (viz
    GIS_PROTOTYP.md, kap. 2).

    Returns:
        dict {KOD: {'STRAHLER': int}}
    """
    return _ze_site(lokality, "strahler", "STRAHLER", int, progress)


def doplnit_km_od_pram(lokality, progress=None):
    """Vzdalenost od pramene [km] merena podel osy toku.

    Returns:
        dict {KOD: {'KM_OD_PRAM': float}}
    """
    return _ze_site(lokality, "km_od_pramene", "KM_OD_PRAM", float, progress)


def doplnit_plocha_pov(lokality, progress=None):
    """Plocha povodi nad lokalitou [km2].

    Returns:
        dict {KOD: {'PLOCHA_POV': float}}
    """
    return _ze_site(lokality, "plocha_povodi", "PLOCHA_POV", float, progress)


# ---------------------------------------------------------------------------
# 4. Podelny sklon toku
# ---------------------------------------------------------------------------

def _theil_sen(body):
    """Robustni odhad smernice: median smernic vsech dvojic bodu.

    Odolny vuci ojedinelym vypadkum v odectu vysky (most, brehova hrana),
    ktere by metodu nejmensich ctvercu vychylily.
    """
    smernice = []
    for i in range(len(body)):
        for j in range(i + 1, len(body)):
            dx = body[j][0] - body[i][0]
            if abs(dx) > 1e-9:
                smernice.append((body[j][1] - body[i][1]) / dx)
    if not smernice:
        return None
    smernice.sort()
    stred = len(smernice) // 2
    if len(smernice) % 2:
        return smernice[stred]
    return (smernice[stred - 1] + smernice[stred]) / 2


def doplnit_slope(lokality, progress=None):
    """Podelny sklon toku [promile] z vysek podel osy toku.

    Postup:
        1. lokalita se prichyti k ricni siti
        2. podel osy toku se odmeri USEK_SKLONU metru (polovina nad,
           polovina pod lokalitou) a rozdeli na VZORKU_SKLONU bodu
        3. pro kazdy bod se dotazem na DMR ziska nadmorska vyska
        4. sklon = smernice Theil-Senovy primky, prepoctena na promile

    Vyzaduje pristup k online sluzbe CUZK.

    Returns:
        dict {KOD: {'SLOPE': float}}
    """
    try:
        from ricni_sit import RicniSit
    except ImportError as e:  # pragma: no cover
        raise ChybejiciZavislost(f"Modul ricni_sit nelze nacist: {e}") from e
    if requests is None:
        raise ChybejiciZavislost("Pro dotaz na DMR je potreba knihovna requests")

    try:
        sit = RicniSit()
    except FileNotFoundError as e:
        raise ChybejiciZavislost(str(e)) from e

    vysledky = {}
    try:
        for i, loc in enumerate(lokality, 1):
            lat, lon = loc.get("WGS84_LAT"), loc.get("WGS84_LON")
            if lat in (None, "") or lon in (None, ""):
                continue
            try:
                osa = sit.osa_okolo(float(lat), float(lon), USEK_SKLONU,
                                    VZORKU_SKLONU)
            except (TypeError, ValueError):
                continue
            if len(osa) < 3:
                continue

            mereni = []
            for vzdalenost, x, y in osa:
                vyska = _vyska_z_dmr(x, y)
                if vyska is not None:
                    mereni.append((vzdalenost, vyska))
                time.sleep(DMR_PRODLEVA)

            if len(mereni) < 3:
                print(f"  [SLOPE] {loc['KOD']}: málo platných odečtů výšky")
                continue
            smernice = _theil_sen(mereni)
            if smernice is None:
                continue
            # smernice je m/m a klesa po proudu - sklon se udava kladne
            vysledky[loc["KOD"]] = {"SLOPE": round(abs(smernice) * 1000, 3)}
            if progress:
                progress(i, len(lokality), f"SLOPE {loc['KOD']}")
    finally:
        sit.zavri()
    return vysledky


def nacti_z_csv(conn, cesta, oddelovac=";"):
    """Nacte abioticke parametry z CSV a zapise je do tabulky loc.

    CSV musi mit hlavicku; prvni sloupec je KOD lokality, dalsi sloupce
    se jmenuji stejne jako sloupce v tabulce loc (napr. PLOCHA_POV, SLOPE).
    Prazdne bunky se ignoruji, existujici hodnoty se prepisou.

    Returns:
        pocet aktualizovanych lokalit
    """
    import csv

    povolene = {
        r[1] for r in conn.execute("PRAGMA table_info(loc)")
    } - {"ID", "KOD"}

    aktualizovano = 0
    with open(cesta, newline="", encoding="utf-8-sig") as f:
        for radek in csv.DictReader(f, delimiter=oddelovac):
            kod = (radek.get("KOD") or "").strip()
            if not kod:
                continue
            hodnoty = {}
            for sloupec, hodnota in radek.items():
                if sloupec in povolene and hodnota not in (None, ""):
                    try:
                        hodnoty[sloupec] = float(hodnota.replace(",", "."))
                    except ValueError:
                        hodnoty[sloupec] = hodnota
            if hodnoty:
                _uloz(conn, kod, hodnoty)
                aktualizovano += 1
    conn.commit()
    return aktualizovano


# ---------------------------------------------------------------------------
# Hlavni davkova funkce
# ---------------------------------------------------------------------------

#: Sloupce, ktere jednotlive parametry plni.
SLOUPCE_PARAMETRU = {
    "souradnice": ["S42_X", "S42_Y", "SJTSK_X", "SJTSK_Y", "UTM_X", "UTM_Y"],
    "mnm": ["MNM"],
    "umori": ["UMORI"],
    "strahler": ["STRAHLER"],
    "km_od_pram": ["KM_OD_PRAM"],
    "slope": ["SLOPE"],
    "plocha_pov": ["PLOCHA_POV"],
}


def doplnit_parametry(db_path, parametry=None, jen_chybejici=True, progress=None):
    """Dopocita vybrane abioticke parametry pro vsechny lokality.

    Args:
        db_path: cesta k SQLite databazi
        parametry: seznam nazvu parametru (viz PARAMETRY); None = vsechny
        jen_chybejici: True = zpracovat jen lokality s prazdnou hodnotou
        progress: volitelna funkce progress(aktualni, celkem, popis)

    Returns:
        dict {parametr: {'doplneno': int, 'lokalit': int, 'chyba': str|None}}
    """
    parametry = parametry or PARAMETRY
    # zachovat definovane poradi - souradnice musi predchazet ostatnim
    parametry = [p for p in PARAMETRY if p in parametry]

    conn = sqlite3.connect(db_path)
    prehled = {}
    souradnice_cache = None

    try:
        for parametr in parametry:
            sloupce = SLOUPCE_PARAMETRU[parametr]
            lokality = nacti_lokality(conn, sloupce if jen_chybejici else None)
            prehled[parametr] = {
                "lokalit": len(lokality), "doplneno": 0, "chyba": None
            }

            if not lokality:
                continue

            try:
                if parametr == "souradnice":
                    vysledky = prepocti_souradnice(lokality)
                    souradnice_cache = vysledky
                elif parametr == "mnm":
                    vysledky = doplnit_mnm(lokality, souradnice_cache, progress)
                elif parametr == "umori":
                    vysledky = doplnit_umori(lokality, progress)
                elif parametr == "strahler":
                    vysledky = doplnit_strahler(lokality, progress)
                elif parametr == "km_od_pram":
                    vysledky = doplnit_km_od_pram(lokality, progress)
                elif parametr == "plocha_pov":
                    vysledky = doplnit_plocha_pov(lokality, progress)
                elif parametr == "slope":
                    vysledky = doplnit_slope(lokality, progress)
                else:
                    continue

            except ChybejiciZavislost as e:
                prehled[parametr]["chyba"] = str(e)
                print(f"[{parametr}] preskoceno: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                prehled[parametr]["chyba"] = f"{type(e).__name__}: {e}"
                print(f"[{parametr}] chyba: {e}")
                continue

            for kod, hodnoty in vysledky.items():
                _uloz(conn, kod, hodnoty)
            conn.commit()
            prehled[parametr]["doplneno"] = len(vysledky)
            print(
                f"[{parametr}] doplneno {len(vysledky)} z {len(lokality)} lokalit"
            )
    finally:
        conn.close()

    return prehled


def prehled_naplnenosti(db_path):
    """Vrati prehled, kolik lokalit ma jednotlive parametry vyplnene.

    Returns:
        dict {sloupec: (vyplneno, celkem)}
    """
    conn = sqlite3.connect(db_path)
    try:
        celkem = conn.execute("SELECT COUNT(*) FROM loc").fetchone()[0]
        prehled = {}
        for sloupce in SLOUPCE_PARAMETRU.values():
            for sloupec in sloupce:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM loc WHERE {sloupec} IS NOT NULL"
                ).fetchone()[0]
                prehled[sloupec] = (n, celkem)
        return prehled
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Doplneni abiotickych parametru lokalit v databazi LULAN"
    )
    p.add_argument("--db", default="dtb/LULAN_dtb_001.db", help="cesta k databazi")
    p.add_argument(
        "--parametry", nargs="+", choices=PARAMETRY,
        help="ktere parametry doplnit (vychozi: vsechny)"
    )
    p.add_argument("--vse", action="store_true", help="doplnit vsechny parametry")
    p.add_argument(
        "--prepsat", action="store_true",
        help="prepsat i jiz vyplnene hodnoty (jinak jen chybejici)"
    )
    p.add_argument("--import-csv", help="nacist parametry z CSV souboru")
    p.add_argument("--prehled", action="store_true", help="jen vypsat naplnenost")
    args = p.parse_args()

    if args.prehled:
        print(f"{'sloupec':12s} {'vyplneno':>10s}")
        for sloupec, (n, celkem) in prehled_naplnenosti(args.db).items():
            print(f"{sloupec:12s} {n:6d}/{celkem:<4d}")
        return

    if args.import_csv:
        conn = sqlite3.connect(args.db)
        try:
            n = nacti_z_csv(conn, args.import_csv)
            print(f"Aktualizovano {n} lokalit z {args.import_csv}")
        finally:
            conn.close()
        return

    parametry = PARAMETRY if args.vse else args.parametry
    if not parametry:
        p.error("zadejte --parametry, --vse, --import-csv nebo --prehled")

    prehled = doplnit_parametry(
        args.db, parametry, jen_chybejici=not args.prepsat
    )
    print("\nSouhrn:")
    for parametr, info in prehled.items():
        stav = info["chyba"] or f"{info['doplneno']}/{info['lokalit']}"
        print(f"  {parametr:12s} {stav}")


if __name__ == "__main__":
    main()
