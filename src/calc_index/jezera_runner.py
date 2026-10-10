"""
Napojeni hodnoceni stojatych vod na databazi.

Vypocetni logika je v modulech `jezera_fp`, `jezera_mf`, `jezera_ryby`
a `jezera_fyzchem`, ktere pracuji nad obycejnymi seznamy dictu a nemaji
zadnou vazbu na PyQt. Tento modul k nim doplnuje to, co potrebuje registr:
nacteni dat vzorku z databaze a zapis vysledku.

Rozhrani `hodnoceni(sample_id, db_connection, potencial=True)` je shodne
s moduly pro tekouci vody, takze registr mezi nimi nerozlisuje.

U stojatych vod se vzdy hodnoti POTENCIAL - vsechny vymezene utvary
kategorie jezero jsou v CR silne ovlivnene (HMWB) nebo umele (AWB), zadny
neni prirozeny.
"""

from __future__ import annotations

from PyQt6.QtSql import QSqlQuery

from .common import smaz_vysledky, to_float, zapis_vysledky
from .jezera_fp import METRIKY as METRIKY_FP
from .jezera_fp import vyhodnot as vyhodnot_fp
from .jezera_mf import METRIKY as METRIKY_MF
from .jezera_mf import vyhodnot as vyhodnot_mf
from .jezera_ryby import METRIKY as METRIKY_RYBY
from .jezera_ryby import vyhodnot as vyhodnot_ryby
from .jezera_typologie import urci_typ
from .jezera_utvary import je_rybnik

#: Kod chlorofylu-a v tabulce `taxalist_chem`.
KOD_CHLOROFYL = "IC0000"


def _abiotika(sample_id, db_connection):
    """Nacte abioticke parametry lokality a ID vodniho utvaru.

    Returns:
        (dict parametru, id_utvaru) nebo (None, None)
    """
    dotaz = QSqlQuery(db_connection)
    dotaz.prepare(
        """
        SELECT l.MNM, l.MAX_HLOUBKA, l.PRUM_HLOUBKA, l.TRT, l.GEOLOGIE,
               l.PLOCHA_KM2, l.VU
        FROM samples s
        JOIN loc l ON s.LOC_ID = l.KOD
        WHERE s.SAMPLE_ID = ?
        """
    )
    dotaz.addBindValue(sample_id)
    if not dotaz.exec() or not dotaz.next():
        return None, None
    return {
        "mnm": dotaz.value(0),
        "zmax": dotaz.value(1),
        "zprum": dotaz.value(2),
        "trt": dotaz.value(3),
        "geologie": dotaz.value(4),
        "plocha": dotaz.value(5),
    }, dotaz.value(6)


def _typ_vzorku(sample_id, db_connection):
    """Urci typ utvaru stojate vody pro dany vzorek."""
    parametry, utvar = _abiotika(sample_id, db_connection)
    if parametry is None:
        return None, "Nehodnoceno: chybí abiotické parametry lokality", None
    typ, duvod = urci_typ(**parametry)
    return typ, duvod, utvar


def _taxony(sample_id, db_connection, sloupce):
    """Nacte taxony vzorku vcetne sloupcu pro stojate vody.

    Args:
        sloupce: seznam nazvu sloupcu tabulky `data`, ktere se maji nacist

    Returns:
        seznam dictu; klice odpovidaji malym pismenum nazvu sloupcu
    """
    vybrane = ", ".join(f"d.{s}" for s in sloupce)
    dotaz = QSqlQuery(db_connection)
    dotaz.prepare(
        f"SELECT d.name, {vybrane} FROM data d WHERE d.sample = ?")
    dotaz.addBindValue(sample_id)
    if not dotaz.exec():
        return []

    radky = []
    while dotaz.next():
        radek = {"nazev": dotaz.value(0)}
        for i, sloupec in enumerate(sloupce, start=1):
            hodnota = dotaz.value(i)
            radek[sloupec.lower()] = None if hodnota == "" else hodnota
        radky.append(radek)
    return radky


def _zarazeni_fytoplanktonu(db_connection):
    """Dohleda rad a tridu taxonu fytoplanktonu v taxalistu.

    Volitelny doplnek: kdyz databaze tabulku `taxalist_FP_jezera` nema,
    vrati se prazdna mapa a zarazeni se dohleda podle rodu primo z Prilohy 2
    (modul `jezera_fp_optima`). Taxalist ma smysl jen tehdy, kdyz uzivatel
    urcuje taxony, ktere Priloha 2 nezna.
    """
    dotaz = QSqlQuery(db_connection)
    if not dotaz.exec(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='taxalist_FP_jezera'"):
        return {}
    if not dotaz.next():
        return {}

    mapa = {}
    dotaz = QSqlQuery(db_connection)
    if dotaz.exec("SELECT NAME, RAD, TRIDA FROM taxalist_FP_jezera"):
        while dotaz.next():
            mapa[str(dotaz.value(0)).strip().lower()] = (
                dotaz.value(1), dotaz.value(2))
    return mapa


def _chlorofyl(sample_id, db_connection):
    """Koncentrace chlorofylu-a ze vzorku [ug/l]."""
    dotaz = QSqlQuery(db_connection)
    dotaz.prepare("SELECT val FROM data WHERE sample = ? AND name = ?")
    dotaz.addBindValue(sample_id)
    dotaz.addBindValue(KOD_CHLOROFYL)
    if dotaz.exec() and dotaz.next():
        return to_float(dotaz.value(0))
    return None


def _zapis(db_connection, sample_id, prefix, vysledek, popisy):
    """Zapise metriky a souhrn do tabulky `results`."""
    kody = list(popisy) + [f"{prefix}_CELKEM"]
    smaz_vysledky(db_connection, sample_id, kody)

    radky = []
    for kod, hodnota in (vysledek.get("metriky") or {}).items():
        body = (vysledek.get("body") or {}).get(kod)
        radky.append({
            "metric": kod,
            "val": hodnota,
            "eqr": None,
            "class": None,
            "pozn": None if body is None else f"{body} bodů",
        })
    radky.append({
        "metric": f"{prefix}_CELKEM",
        "val": None,
        "eqr": vysledek.get("eqr"),
        "class": vysledek.get("trida"),
        "pozn": vysledek.get("poznamka"),
    })
    zapis_vysledky(db_connection, sample_id, radky)


def _souhrn(prefix, vysledek, typ):
    """Sestavi navratovou hodnotu ve tvaru, ktery ceka registr."""
    pozn = vysledek.get("poznamka")
    if typ is not None:
        pozn = f"typ {typ.kod}" + (f"; {pozn}" if pozn else "")
    return {
        f"{prefix}_CELKEM": vysledek.get("eqr"),
        f"{prefix}_CLASS": vysledek.get("trida"),
        f"{prefix}_POZN": pozn,
        f"{prefix}_TYP_HODNOCENI": "POTENCIAL",
    }


# ---------------------------------------------------------------------------
# Fytoplankton
# ---------------------------------------------------------------------------

def fp_jezero(sample_id, db_connection, potencial=True):
    """Fytoplankton stojatych vod - CZ-PHYPI."""
    typ, duvod, _utvar = _typ_vzorku(sample_id, db_connection)
    if typ is None:
        return {"FP_CELKEM": None, "FP_CLASS": None, "FP_POZN": duvod,
                "FP_TYP_HODNOCENI": "POTENCIAL"}

    zarazeni = _zarazeni_fytoplanktonu(db_connection)
    taxony = []
    for radek in _taxony(sample_id, db_connection, ["val", "BIOMASA"]):
        rad, trida = zarazeni.get(
            str(radek["nazev"]).strip().lower(), (None, None))
        taxony.append({
            "nazev": radek["nazev"],
            "biomasa": radek["biomasa"],
            "rad": rad,
            "trida": trida,
        })

    vysledek = vyhodnot_fp(typ, taxony, _chlorofyl(sample_id, db_connection))
    _zapis(db_connection, sample_id, "FP", vysledek, METRIKY_FP)
    return _souhrn("FP", vysledek, typ)


# ---------------------------------------------------------------------------
# Makrofyta
# ---------------------------------------------------------------------------

def mf_jezero(sample_id, db_connection, potencial=True):
    """Makrofyta stojatych vod - CZ-MPHYI."""
    typ, duvod, _utvar = _typ_vzorku(sample_id, db_connection)
    taxony = [
        {"nazev": r["nazev"], "pokryvnost": r["pokryvnost"]}
        for r in _taxony(sample_id, db_connection, ["POKRYVNOST"])
    ]
    vysledek = vyhodnot_mf(taxony, typ)
    _zapis(db_connection, sample_id, "MF", vysledek, METRIKY_MF)
    return _souhrn("MF", vysledek, typ)


# ---------------------------------------------------------------------------
# Ryby
# ---------------------------------------------------------------------------

def ryby_jezero(sample_id, db_connection, potencial=True):
    """Ryby stojatych vod - CZ-FBI."""
    typ, duvod, utvar = _typ_vzorku(sample_id, db_connection)
    if typ is None and not je_rybnik(utvar):
        return {"RYBY_CELKEM": None, "RYBY_CLASS": None, "RYBY_POZN": duvod,
                "RYBY_TYP_HODNOCENI": "POTENCIAL"}

    ulovky = [
        {"nazev": r["nazev"], "sit": r["sit"], "zona": r["zona"],
         "val": r["val"], "biomasa": r["biomasa"], "juv": r["juv"]}
        for r in _taxony(sample_id, db_connection,
                         ["val", "BIOMASA", "SIT", "ZONA", "juv"])
    ]
    vysledek = vyhodnot_ryby(typ, ulovky, rybnik=je_rybnik(utvar))
    _zapis(db_connection, sample_id, "RYBY", vysledek, METRIKY_RYBY)
    return _souhrn("RYBY", vysledek, typ)
