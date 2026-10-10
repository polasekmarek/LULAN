"""
Export dat a vysledku do CSV.

Protejsek modulu `import_csv`. Zapisuje ve stejnem tvaru, v jakem import
cte, takze data z LULANu jde po uprave v tabulkovem procesoru nacist
zpatky.

Format vystupu
--------------
Oddelovac je stredník a kodovani `utf-8-sig`. BOM na zacatku souboru
potrebuje Excel, aby cesky text zobrazil spravne; bez nej ukaze
"LokalitaÄ›". Desetinny oddelovac zustava tecka - `import_csv` cte cisla
pres `float()` a s carkou by si neporadil. V Excelu je proto nutne pri
otevirani potvrdit, ze desetinny oddelovac je tecka, jinak se sloupce
s cisly nactou jako text.

Dva druhy exportu
-----------------
**Z modelu** (`exportuj_model`) - vypise presne to, co uzivatel vidi
v tabulce, vcetne nastavenych filtru. To je u tlacitka "Exportovat"
prirozene ocekavani: co je videt, to se ulozi.

**Z dotazu** (`exportuj_dotaz`) - predpripravene sestavy, ktere se do
zadne tabulky v GUI nevejdou, hlavne vysledky prevedene do siroke
podoby (jeden radek na vzorek, sloupec na metriku).
"""

from __future__ import annotations

import csv
import os

from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlQuery

from ciselnik_metrik import ZASTARALE

#: Oddelovac a kodovani vystupu - viz poznamka v hlavicce modulu.
ODDELOVAC = ";"
KODOVANI = "utf-8-sig"

#: Zastarale metriky pro klauzuli NOT IN. Kody pochazeji z kodu, ne od
#: uzivatele, takze je bezpecne je vlozit primo do dotazu - a musi to
#: tak byt, protoze dotazy jsou hotove retezce bez parametru.
_ZASTARALE_SQL = ", ".join(f"'{k}'" for k in sorted(ZASTARALE)) or "''"


class PopisExportu:
    """Jedna polozka nabidky exportu."""

    def __init__(self, nazev, popis, sql, soubor):
        self.nazev = nazev
        self.popis = popis
        self.sql = sql
        self.soubor = soubor


#: Vysledky po metrikach - dlouhy format, jeden radek na metriku.
_SQL_VYSLEDKY_DLOUHE = """
    SELECT r.SAMPLE_ID   AS vzorek,
           s.TYP         AS slozka,
           s.DATE        AS datum,
           s.LOC_ID      AS lokalita,
           l.TOK         AS tok,
           l.PROFIL      AS profil,
           l.VU          AS utvar,
           r.METRIC      AS metrika,
           r.VAL         AS hodnota,
           r.VAL_EQR     AS eqr,
           r.CLASS       AS trida,
           r.POZN        AS poznamka
    FROM results r
    LEFT JOIN samples s ON r.SAMPLE_ID = s.SAMPLE_ID
    LEFT JOIN loc l ON s.LOC_ID = l.KOD
    WHERE r.METRIC NOT IN (__ZASTARALE__)
    ORDER BY r.SAMPLE_ID, r.METRIC
""".replace("__ZASTARALE__", _ZASTARALE_SQL)

#: Souhrn po vzorcich - jen celkove hodnoceni kazde slozky.
_SQL_VYSLEDKY_SOUHRN = """
    SELECT r.SAMPLE_ID   AS vzorek,
           s.TYP         AS slozka,
           s.DATE        AS datum,
           s.LOC_ID      AS lokalita,
           l.TOK         AS tok,
           l.PROFIL      AS profil,
           l.VU          AS utvar,
           r.VAL         AS hodnota,
           r.VAL_EQR     AS eqr,
           r.CLASS       AS trida,
           r.POZN        AS poznamka
    FROM results r
    LEFT JOIN samples s ON r.SAMPLE_ID = s.SAMPLE_ID
    LEFT JOIN loc l ON s.LOC_ID = l.KOD
    WHERE r.METRIC LIKE '%\\_CELKEM' ESCAPE '\\'
    ORDER BY r.SAMPLE_ID
"""

#: Rocni vysledky vodnich utvaru.
_SQL_ROCNI = """
    SELECT UTVAR_POV AS utvar, ROK AS rok,
           MZB_EQR, MZB_CLASS, FB_EQR, FB_CLASS, FP_EQR, FP_CLASS,
           MF_EQR, MF_CLASS, RYBY_EQR, RYBY_CLASS, FYZCHEM_CLASS
    FROM results_year
    ORDER BY UTVAR_POV, ROK
"""

#: Taxonomicka data vzorku v dlouhem formatu - stejny tvar, jaky cte
#: `import_csv`, takze export a import na sebe navazuji.
_SQL_DATA_VZORKU = """
    SELECT d.sample AS SAMPLE_ID,
           d.name   AS NAME,
           d.val    AS VAL,
           d.BIOMASA, d.POKRYVNOST, d.SIT, d.ZONA,
           s.TYP    AS TYP,
           s.DATE   AS DATE,
           s.LOC_ID AS LOC_ID
    FROM data d
    LEFT JOIN samples s ON d.sample = s.SAMPLE_ID
    ORDER BY d.sample, d.name
"""

#: Nabidka exportu vysledku (zalozka Vysledky).
EXPORTY_VYSLEDKU = {
    "souhrn": PopisExportu(
        "Souhrn po vzorcích",
        "Celkové hodnocení každé složky – jeden řádek na vzorek a složku.",
        _SQL_VYSLEDKY_SOUHRN, "LULAN_vysledky_souhrn.csv"),
    "metriky": PopisExportu(
        "Všechny metriky",
        "Dlouhý formát – jeden řádek na metriku, včetně poznámek.",
        _SQL_VYSLEDKY_DLOUHE, "LULAN_vysledky_metriky.csv"),
    "rocni": PopisExportu(
        "Roční výsledky útvarů",
        "Agregace na vodní útvar a rok, tak jak se předává do reportingu.",
        _SQL_ROCNI, "LULAN_vysledky_rocni.csv"),
}

#: Nabidka exportu vzorku (zalozka Vzorky).
EXPORTY_VZORKU = {
    "seznam": PopisExportu(
        "Seznam vzorků (dle filtru)",
        "To, co je právě vidět v tabulce – včetně nastavených filtrů.",
        None, "LULAN_vzorky.csv"),
    "data": PopisExportu(
        "Vzorky včetně taxonů",
        "Dlouhý formát taxon po taxonu; dá se rovnou naimportovat zpět.",
        _SQL_DATA_VZORKU, "LULAN_vzorky_data.csv"),
}


def _zapis(cesta, hlavicky, radky):
    """Zapise CSV a vrati pocet zapsanych radku."""
    slozka = os.path.dirname(os.path.abspath(cesta))
    if slozka and not os.path.isdir(slozka):
        os.makedirs(slozka, exist_ok=True)

    with open(cesta, "w", encoding=KODOVANI, newline="") as f:
        zapis = csv.writer(f, delimiter=ODDELOVAC, lineterminator="\n")
        zapis.writerow(hlavicky)
        pocet = 0
        for radek in radky:
            zapis.writerow(["" if h is None else h for h in radek])
            pocet += 1
    return pocet


def exportuj_dotaz(db_connection, sql, cesta):
    """Provede SQL dotaz a vysledek zapise do CSV.

    Returns:
        pocet zapsanych radku

    Raises:
        RuntimeError: kdyz dotaz selze
    """
    dotaz = QSqlQuery(db_connection)
    if not dotaz.exec(sql):
        raise RuntimeError(dotaz.lastError().text() or "dotaz selhal")

    zaznam = dotaz.record()
    hlavicky = [zaznam.fieldName(i) for i in range(zaznam.count())]

    def radky():
        while dotaz.next():
            yield [dotaz.value(i) for i in range(len(hlavicky))]

    return _zapis(cesta, hlavicky, radky())


def exportuj_model(model, cesta, sloupce=None, hlavicky=None):
    """Zapise obsah modelu do CSV.

    `QSqlQueryModel` nacita radky po davkach - dokud se nezavola
    `fetchMore()`, model o vetsine radku nevi a export by byl useknuty
    na prvnich 256. Proto se nejdriv donacte vse.

    Args:
        model: QSqlQueryModel, QSqlTableModel nebo proxy nad nimi
        sloupce: indexy sloupcu k exportu; None = vsechny
        hlavicky: vlastni nazvy sloupcu; None = z modelu

    Returns:
        pocet zapsanych radku
    """
    while model.canFetchMore():
        model.fetchMore()

    if sloupce is None:
        sloupce = list(range(model.columnCount()))
    if hlavicky is None:
        hlavicky = [
            str(model.headerData(i, Qt.Orientation.Horizontal)
                or f"sloupec_{i}")
            for i in sloupce
        ]

    def radky():
        for r in range(model.rowCount()):
            yield [model.data(model.index(r, c)) for c in sloupce]

    return _zapis(cesta, hlavicky, radky())
