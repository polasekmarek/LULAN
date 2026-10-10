"""
Fytobentos (FB) - staletekouci (perennial) toky.

Metodika stavi na saprobnim indexu z tabulky `taxalist_fb` (MSZS vazene
MSZG). Referencni hodnota EQR se odvozuje od nadmorske vysky, Strahlerova
radu a rocniho prumeru kyselinove neutralizacni kapacity (KNK, chemicky
parametr CB0050) na dane lokalite.

Vypocet:
    saprobni index  = sum(val * MSZS * MSZG) / sum(val * MSZG)
    referencni mez  = 1.1 - 0.0004 * MNM + 0.025 * STRAHLER          (KNK >= 0.75)
                      + 0.4 * (0.75 - KNK)                            (KNK <  0.75)
    EQR             = (2.9 - saprobni index) / (2.9 - referencni mez)

Krome vlastniho indexu se pocitaji dve doprovodne veliciny, ktere metodika
zavadi jako miru duveryhodnosti stanoveni (odst. 6.5 a 6.6):

    soucet vah Sw   = sum(MSZG) pres skorujici taxony
    stredni chyba   = sqrt( sum((MSZS - I)^2 * val * MSZG)
                            / ((n - 1) * sum(val * MSZG)) )        [ 8 ]
    spolehlivost R  = Sw / 50 + 0.20 / stredni chyba

Pozor na rozdil mezi Sw a jmenovatelem indexu: jmenovatel je vazeny
abundanci (`sum(val * MSZG)`), soucet vah nikoli (`sum(MSZG)`). ARROW
exportuje Sw ve sloupci SOUCET_VAH.
"""

from __future__ import annotations

import math
from datetime import datetime

from PyQt6.QtSql import QSqlQuery

from .common import (
    klasifikuj,
    nacti_data_vzorku,
    nacti_taxalist,
    smaz_vysledky,
    to_float,
    vyres_synonyma,
    zapis_vysledky,
)

#: Vychozi hodnota KNK, pokud pro lokalitu nejsou chemicka data.
KNK_DEFAULT = 0.8

#: Kod chemickeho parametru KNK v tabulce `data`.
KNK_PARAM = "CB0050"

#: Horni referencni hodnota saprobniho indexu (nejhorsi stav).
SAPROBITA_MAX = 2.9

#: Mez souctu vah, pod kterou metodika (odst. 6.8.1) pripousti, ze
#: zastoupeni fototrofu uz na spolehlive hodnoceni nestaci.
MEZ_SOUCTU_VAH = 30

#: Meze spolehlivosti R podle odst. 6.6.
SPOLEHLIVOST = ((2.0, "spolehlivé"), (1.0, "málo spolehlivé"))

#: Hranice trid - FB perennial ma vlastni, prisnejsi delitka.
HRANICE_STAV = [(0.8, "VD"), (0.63, "D"), (0.4, "S"), (0.2, "P"), (float("-inf"), "Z")]
HRANICE_POTENCIAL = [
    (0.75, "VD"), (0.55, "D"), (0.35, "S"), (0.15, "P"), (float("-inf"), "Z")
]


def _nacti_kontext(sample_id, db_connection):
    """Nacte datum, lokalitu a jeji abioticke parametry."""
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT s.DATE, s.LOC_ID, l.STRAHLER, l.MNM
        FROM samples s
        LEFT JOIN loc l ON s.LOC_ID = l.KOD
        WHERE s.SAMPLE_ID = ?
        """
    )
    query.addBindValue(sample_id)
    if not query.exec() or not query.next():
        return None
    return {
        "date": query.value(0),
        "loc_id": query.value(1),
        "strahler": to_float(query.value(2), 0.0),
        "mnm": to_float(query.value(3), 0.0),
    }


def _nacti_knk(db_connection, loc_id, rok):
    """Rocni prumer KNK na lokalite; None pokud nejsou data."""
    if rok is None:
        return None
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT avg(d.val)
        FROM data d
        JOIN samples s ON d.sample = s.SAMPLE_ID
        WHERE s.LOC_ID = ? AND s.DATE LIKE ? AND d.name = ?
        """
    )
    query.addBindValue(loc_id)
    query.addBindValue(f"%.{rok}")
    query.addBindValue(KNK_PARAM)
    if query.exec() and query.next():
        return to_float(query.value(0))
    return None


def _spolehlivost(skorujici, index, jmenovatel, soucet_vah):
    """Stredni chyba indexu a spolehlivost stanoveni.

    Args:
        skorujici: seznam trojic (MSZS, abundance, MSZG)
        index: nezaokrouhleny saprobni index
        jmenovatel: sum(abundance * MSZG)
        soucet_vah: sum(MSZG)

    Returns:
        (stredni_chyba, spolehlivost); obe None, kdyz je taxon jen jeden
        (rozptyl se deli n-1) nebo kdyz vsechny taxony maji tyz index.
    """
    n = len(skorujici)
    if n < 2 or jmenovatel <= 0:
        return None, None

    rozptyl = sum(
        (s - index) ** 2 * h * w for s, h, w in skorujici
    ) / ((n - 1) * jmenovatel)
    chyba = math.sqrt(rozptyl)
    if chyba <= 0:
        return 0.0, None
    return round(chyba, 4), round(soucet_vah / 50 + 0.20 / chyba, 4)


def _slovy(spolehlivost):
    """Prevede cislo R na slovni hodnoceni podle odst. 6.6."""
    if spolehlivost is None:
        return "neurčeno"
    for mez, popis in SPOLEHLIVOST:
        if spolehlivost >= mez:
            return popis
    return "nespolehlivé"


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte FB hodnoceni pro staletekouci tok."""
    try:
        ctx = _nacti_kontext(sample_id, db_connection)
        if ctx is None:
            return {"FB_POZN": "Vzorek nebo lokalita nenalezena"}

        try:
            rok = datetime.strptime(ctx["date"], "%d.%m.%Y").year
        except (TypeError, ValueError):
            rok = None

        taxa_data = nacti_data_vzorku(db_connection, sample_id)
        if not taxa_data:
            return {"FB_POZN": "Ve vzorku nejsou zadna taxonomicka data"}

        taxalist = nacti_taxalist(db_connection, "taxalist_fb", ["MSZS", "MSZG"])
        data = vyres_synonyma(taxa_data, taxalist["by_name"])
        by_id = taxalist["by_id"]

        # Skorujici taxony: musi mit v taxalistu obe hodnoty, saprobni
        # index S i indikacni vahu w. Uklada se trojice (S, h, w), protoze
        # se pres ni pak jeste jednou prochazi pri vypoctu stredni chyby.
        skorujici = []
        for taxon_id, abundance in data.items():
            info = by_id.get(taxon_id)
            if info is None or info["MSZS"] is None or info["MSZG"] is None:
                continue
            skorujici.append(
                (info["MSZS"], to_float(abundance, 0.0), info["MSZG"])
            )

        citatel = sum(s * h * w for s, h, w in skorujici)
        jmenovatel = sum(h * w for _, h, w in skorujici)

        if jmenovatel <= 0:
            return {"FB_POZN": "Zadne taxony s hodnotami MSZS / MSZG"}

        # Presna hodnota se drzi stranou: do EQR se dosazuje ona, nikoli
        # zaokrouhlena. Zaokrouhleni az na vstupu do EQR posouvalo vysledek
        # o 0,001 u 52 z 409 kontrolnich vzorku.
        index_presne = citatel / jmenovatel
        saprobni_index = round(index_presne, 3)
        soucet_vah = sum(w for _, _, w in skorujici)
        stredni_chyba, spolehlivost = _spolehlivost(
            skorujici, index_presne, jmenovatel, soucet_vah
        )

        knk = _nacti_knk(db_connection, ctx["loc_id"], rok)
        knk_pouzita = KNK_DEFAULT if knk is None else knk

        referencni_mez = 1.1 - 0.0004 * ctx["mnm"] + 0.025 * ctx["strahler"]
        if knk_pouzita < 0.75:
            referencni_mez += 0.4 * (0.75 - knk_pouzita)

        rozsah = SAPROBITA_MAX - referencni_mez
        if rozsah <= 0:
            return {"FB_POZN": "Neplatna referencni mez pro vypocet EQR"}

        eqr = round((SAPROBITA_MAX - index_presne) / rozsah, 3)
        trida = klasifikuj(
            eqr, hranice=HRANICE_POTENCIAL if potencial else HRANICE_STAV
        )

        pozn = (
            f"Saprobni index: {saprobni_index}, referencni mez: "
            f"{round(referencni_mez, 3)}, KNK: {round(knk_pouzita, 3)}"
            f"{' (vychozi)' if knk is None else ''}, soucet vah: "
            f"{soucet_vah:g}, spolehlivost: {_slovy(spolehlivost)}"
        )
        if soucet_vah < MEZ_SOUCTU_VAH:
            pozn += (
                f" — soucet vah je pod {MEZ_SOUCTU_VAH}; podle odst. 6.8.1 "
                "metodiky je treba overit, zda ve vzorku neprevazuji "
                "heterotrofni organismy"
            )

        smaz_vysledky(
            db_connection, sample_id,
            ["FB_01", "FB_03", "FB_04", "FB_SW", "FB_CELKEM"],
        )
        zapis_vysledky(
            db_connection,
            sample_id,
            [
                {"metric": "FB_01", "val": saprobni_index, "eqr": eqr,
                 "class": None, "pozn": pozn},
                {"metric": "FB_SW", "val": soucet_vah, "eqr": None,
                 "class": None, "pozn": "Soucet indikacnich vah (sum MSZG)"},
                {"metric": "FB_03", "val": stredni_chyba, "eqr": None,
                 "class": None,
                 "pozn": "Stredni chyba indexu podle vzorce [8] metodiky"},
                {"metric": "FB_04", "val": spolehlivost, "eqr": None,
                 "class": None,
                 "pozn": f"Spolehlivost stanoveni R ({_slovy(spolehlivost)})"},
                {"metric": "FB_CELKEM", "val": eqr, "eqr": eqr,
                 "class": trida, "pozn": pozn},
            ],
        )

        return {
            "FB_01": saprobni_index,
            "FB_01_EQR": eqr,
            "FB_03": stredni_chyba,
            "FB_04": spolehlivost,
            "FB_SW": soucet_vah,
            "FB_CELKEM": eqr,
            "FB_CLASS": trida,
            "FB_POZN": pozn,
            "FB_TYP_HODNOCENI": "POTENCIAL" if potencial else "STAV",
        }

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"FB_POZN": f"Kriticka chyba: {e}"}
