"""
Ryby - toky, ekologicky potencial silne ovlivnenych a umelych utvaru.

Metodika:
    Janac M. a kol. (2024): Metodika hodnoceni ekologickeho potencialu silne
    ovlivnenych a umelych vodnich utvaru - kategorie reka podle biologicke
    slozky ryby.
    metodiky/OOV_Metodika hodnoceni ekologickeho potencialu_reka_ryby_20241204.pdf

Princip
-------
Vypocet stoji na tomtez indexu CZI jako hodnoceni stavu. Lisi se tim, ze
horni meze, vahy a nekdy i sada pouzitych metrik se neberou podle typu toku,
ale podle KATEGORIE silne ovlivneneho utvaru (I-X). Kategorie je v metodice
zadana vyctem konkretnich vodnich utvaru - viz ryby_hmwb_utvary.

Tridy potencialu jsou ctyri (Tab. 12): dobry a lepsi / stredni / poskozeny /
zniceny, hranice 0,6 / 0,4 / 0,2 s ostrou nerovnosti.
"""

from __future__ import annotations

from .ryby_hmwb_utvary import NEHODNOCENE_KATEGORIE, kategorie_utvaru
from .ryby_reka import EQR_TABLE, hodnoceni as hodnoceni_czi
from .ryby_typologie import urci_typ

try:
    from PyQt6.QtSql import QSqlQuery
except ImportError:  # pragma: no cover
    QSqlQuery = None


#: Kategorie I a VI - CZI = (TA_EQR + AR_EQR) / 2.
#:
#: "Metriky TD, ND1 a ND2 tedy nemohou byt pouzity pro stanoveni ekologickeho
#:  potencialu techto toku ani v omezene mire." Misto nich nastupuje nova,
#:  pata metrika TA = celkova abundance vsech juvenilnich ryb.
#:  Hodnota AR se transformuje jako ln(AR + 1). (kap. 3.1 a 3.6)
TABULKA_I = {
    "RY_TA": (50, 1.0, None),
    "RY_AR": (20, 1.0, "ln1"),
}

#: Kategorie II - CZI = (TD_EQR + AR_EQR) / 2, tok zustava typu F,
#: mez TD klesa z 8 na 6 a mez AR z 200 na 100. (kap. 3.2)
TABULKA_II = {
    "RY_TD": (6,   1.0, None),
    "RY_AR": (100, 1.0, None),
}

#: Kategorie III - standardni vzorec pro typ G, mez TD klesa z 12 na 6
#: a mez AR ze 150 na 50; ND1 a ND2 zustavaji beze zmeny. (kap. 3.3)
TABULKA_III = {
    "RY_TD":  (6,  EQR_TABLE["G"]["RY_TD"][1], EQR_TABLE["G"]["RY_TD"][2]),
    "RY_AR":  (50, EQR_TABLE["G"]["RY_AR"][1], EQR_TABLE["G"]["RY_AR"][2]),
    "RY_ND1": EQR_TABLE["G"]["RY_ND1"],
    "RY_ND2": EQR_TABLE["G"]["RY_ND2"],
}

#: Kategorie V - nove meze a vahy podle Tab. 8. Transformace zustavaji
#: stejne jako u hodnoceni stavu.
TABULKA_V = {
    "A": {
        "RY_TD":  (1,    1.6, "ln5"),
        "RY_AR":  (30,   1.6, None),
        "RY_ND1": (6,    0.4, "ln10"),
        "RY_ND2": (0.75, 0.4, "ln100"),
    },
    "B": {
        "RY_TD":  (3,    1.6, None),
        "RY_AR":  (50,   1.6, None),
        "RY_ND1": (6,    0.4, "ln10"),
        "RY_ND2": (0.75, 0.4, "ln100"),
    },
    "C": {
        "RY_TD":  (3,    1.6, None),
        "RY_AR":  (50,   1.6, None),
        "RY_ND1": (6,    0.4, "ln10"),
        "RY_ND2": (0.75, 0.4, "ln100"),
    },
    "D": {
        "RY_TD":  (3,     1.8, None),
        "RY_AR":  (20,    1.2, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.6, "ln100"),
    },
    "E": {
        "RY_TD":  (4,     2.2, None),
        "RY_AR":  (100,   1.0, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.4, "ln100"),
    },
    "F": {
        "RY_TD":  (5,     2.2, None),
        "RY_AR":  (100,   1.0, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.4, "ln100"),
    },
}

#: Popis toho, co se v jednotlive kategorii meni - jde do poznamky vysledku.
POPIS_KATEGORIE = {
    "I": "male toky v rybnicnich oblastech (TA + AR)",
    "II": "velke toky v rybnicnich oblastech (TD + AR)",
    "III": "kanalizovane a regulovane useky velkych rek",
    "IV": "sekundarni pstruhove pasmo - hodnoceno jako typ A",
    "V": "tok pod vodni nadrzi (upravene meze dle Tab. 8)",
    "VI": "tok s nizkym ekologickym potencialem (TA + AR)",
    "VII": "utvar s dobrym ekologickym stavem - nezmenene CZI",
    "VIII": "lze docilit dobreho ekologickeho stavu - nezmenene CZI",
}


def _utvar_vzorku(sample_id, db_connection):
    """Vrati (kod vodniho utvaru, priznak HMWB) pro vzorek."""
    query = QSqlQuery(db_connection)
    query.prepare(
        "SELECT l.VU, u.HMWB FROM samples s "
        "LEFT JOIN loc l ON l.KOD = s.LOC_ID "
        "LEFT JOIN utvary u ON u.ID_UTVARU = l.VU "
        "WHERE s.SAMPLE_ID = ?"
    )
    query.addBindValue(sample_id)
    if query.exec() and query.next():
        return query.value(0), query.value(1)
    return None, None


def _nacti_typ_z_dat(sample_id, db_connection):
    """Odvodi typ toku z abiotickych parametru lokality."""
    query = QSqlQuery(db_connection)
    query.prepare(
        "SELECT l.UMORI, l.MNM, l.STRAHLER FROM samples s "
        "LEFT JOIN loc l ON l.KOD = s.LOC_ID WHERE s.SAMPLE_ID = ?"
    )
    query.addBindValue(sample_id)
    if not query.exec() or not query.next():
        return None, "Vzorek nebo lokalita nenalezena"
    return urci_typ(query.value(0), query.value(1), query.value(2))


def vyber_nastaveni(kategorie, typ_toku):
    """Vrati (tabulka, vynuceny_typ) pro danou kategorii HMWB.

    Tabulka None znamena "pouzij standardni tabulku podle typu toku".
    """
    if kategorie in ("I", "VI"):
        return TABULKA_I, None
    if kategorie == "II":
        return TABULKA_II, "F"
    if kategorie == "III":
        # vcetne profilu Vltava - Hluboka, ktery jinak spada do typu F
        return TABULKA_III, "G"
    if kategorie == "IV":
        # sekundarni pstruhova pasma se hodnoti jako toky typu A
        return None, "A"
    if kategorie == "V":
        return TABULKA_V.get(typ_toku), typ_toku
    # kategorie VII a VIII - nezmenena verze CZI
    return None, None


def hodnoceni(sample_id, db_connection, **kwargs):
    """Vypocte ekologicky potencial vzorku ryb.

    Kategorii silne ovlivneneho utvaru bere z tabulky v ryby_hmwb_utvary;
    pokud utvar v seznamu neni, hodnoti se nezmenenym CZI jako by slo
    o ekologicky stav, jen s hranicemi trid pro potencial.
    """
    utvar, hmwb = _utvar_vzorku(sample_id, db_connection)
    kategorie, typ_metodiky = kategorie_utvaru(utvar)

    # U umelych utvaru se biologicke slozky zpravidla nehodnoti (metodika
    # 2013, kap. 6). Vyjimkou je Vranansko-Horinsky plavebni kanal, ktery
    # metodika ryb vyslovne radi do kategorie III.
    if hmwb == "U" and kategorie is None:
        return {
            "RYBY_POZN": (
                f"Nehodnoceno: umely vodni utvar {utvar} neni v seznamu "
                f"kategorii metodiky potencialu"
            )
        }

    if kategorie in NEHODNOCENE_KATEGORIE:
        return {
            "RYBY_POZN": (
                f"Nehodnoceno: utvar {utvar} je kategorie {kategorie} - "
                f"{NEHODNOCENE_KATEGORIE[kategorie]}"
            )
        }

    # Typ toku podle metodiky ma prednost - podle nej byly nastaveny meze.
    typ_z_dat, duvod = _nacti_typ_z_dat(sample_id, db_connection)
    typ = typ_metodiky or typ_z_dat
    if typ is None:
        # duvod uz predponu "Nehodnoceno:" obsahuje - viz urci_typ()
        return {"RYBY_POZN": duvod}

    if kategorie is None:
        popis = (
            f"Ekologicky potencial. Utvar {utvar} neni v seznamu kategorii "
            f"I-X, pouzito nezmenene CZI"
        )
        return hodnoceni_czi(
            sample_id, db_connection, potencial=True,
            typ_toku=typ, popis=popis,
        )

    tabulka, vynuceny_typ = vyber_nastaveni(kategorie, typ)
    if kategorie == "V" and tabulka is None:
        return {
            "RYBY_POZN": (
                f"Nehodnoceno: pro kategorii V a typ toku {typ} neni "
                f"v Tab. 8 zadny radek"
            )
        }

    pouzity_typ = vynuceny_typ or typ
    nesoulad = (
        f", typ dle dat {typ_z_dat} prepsan na {pouzity_typ}"
        if typ_z_dat and typ_z_dat != pouzity_typ else ""
    )
    popis = (
        f"Ekologicky potencial. Utvar {utvar}, kategorie {kategorie} "
        f"({POPIS_KATEGORIE.get(kategorie, '?')}){nesoulad}"
    )

    return hodnoceni_czi(
        sample_id, db_connection, potencial=True,
        tabulka=tabulka, typ_toku=pouzity_typ, popis=popis,
    )
