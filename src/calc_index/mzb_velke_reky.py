"""
MZB - velke nebroditelne reky (VR), ekologicky stav i potencial.

Metodika:
    Nemejcova D. a kol. (2019): Metodika hodnoceni biologicke slozky
    benticti bezobratli pro velke nebroditelne reky. VUV TGM.
    metodiky/OOV-metodika_MZB_VR_aktualizace-20191014.pdf

Uplatnuje se pouze na 24 vyjmenovanych vodnich utvaru typu 12_3
(viz velke_reky_utvary.py), nikoli na vsechny toky 7.-9. radu.

Sada metrik je uplne jina nez u broditelnych toku - B-index (MB07) se
zde NEPOUZIVA VUBEC, jeho roli prebira index REKOnstruovanych taxocenoz
MEPT. Vsechny metriky maji vahu 1 (metodika, kap. 4).

    VR01  REKO MEPT   podil zjistenych taxonu ze seznamu ocekavanych
    VR02  DivMarg     Margaleuv index diverzity
    VR03  ZEPota      ricni zonace epipotamal [%]
    VR04  EPT Abu     podil log-abundanci taxonu EPT [%]
    VR05  SI          saprobni index
    VR06  SPEARorg    index citlivosti spolecenstva SPEAR organic

Hodnoti se pouze LETNI vzorky (odber v cervenci, obdobi nizkych prutoku).
"""

from __future__ import annotations

from .common import (
    aplikuj_adjustace,
    je_platna,
    klasifikuj,
    nacti_adjustaci,
    nacti_data_vzorku,
    nacti_taxalist,
    patri_do_skupiny,
    preved_na_eqr,
    safe_log,
    smaz_vysledky,
    to_float,
    vazeny_prumer,
    vyres_synonyma,
    zapis_vysledky,
)
from .velke_reky_utvary import SLOUPEC_REKO, povodi, utvar_vzorku

#: Trait sloupce potrebne pro metriky velkych rek.
TRAIT_SLOUPCE = [
    "SZS", "SZG",           # saprobni index
    "ZEP",                  # ricni zonace: epipotamal
    "SPEAR_ORG",            # SPEAR organic
    "TAXONY_MEPT_VLT",      # ocekavane taxony MEPT - povodi Labe
    "TAXONY_MEPT_MO",       # ocekavane taxony MEPT - povodi Moravy
]

METRIKY = ["VR01", "VR02", "VR03", "VR04", "VR05", "VR06"]

#: Citelne nazvy metrik pro poznamky ve vysledcich.
NAZVY = {
    "VR01": "REKO MEPT",
    "VR02": "Margalef",
    "VR03": "epipotamal",
    "VR04": "EPT Abu",
    "VR05": "saprobni index",
    "VR06": "SPEAR organic",
}

#: Prevodni tabulka {metrika: (dolni_mez, horni_mez, invertovat, vaha)}.
#: Zdroj: metodika VR, Tab. 4 (letni vzorky). Vsechny vahy jsou 1.
EQR_TABLE = {
    "VR01": (0.0, 0.5, False, 1.0),
    "VR02": (0.4, 11.0, False, 1.0),
    "VR03": (8.6, 34.5, False, 1.0),
    "VR04": (0.0, 39.7, False, 1.0),
    "VR05": (1.7, 3.5, True, 1.0),
    "VR06": (-1.23, -0.07, False, 1.0),
}

#: Hranice trid ekologickeho stavu podle Tab. 5 metodiky VR.
#: Metodika pouziva ostrou nerovnost: VD je 0,8 < MMI, D je 0,6 < MMI <= 0,8 atd.
HRANICE_VR = [
    (0.8, "VD"), (0.6, "D"), (0.4, "S"), (0.2, "P"), (float("-inf"), "Z"),
]

#: Mesice, ve kterych se odebiraji letni vzorky pro hodnoceni velkych rek.
#:
#: Metodika predpisuje cerven-srpen (obdobi nizkych prutoku, teziste
#: v cervenci). Zari je v datech nejednoznacne - patri jak k letni, tak
#: k podzimni kampani - proto o nem rozhoduje az znacka v ID vzorku.
LETNI_MESICE = (6, 7, 8)

#: Doporuceny minimalni pocet jedincu ve vzorku (metodika, kap. 8).
MIN_JEDINCU = 100

EPT = ("Ephemeroptera", "Plecoptera", "Trichoptera")


def _je_letni(datum_str, sample_id):
    """Overi, ze jde o letni vzorek.

    Prednost ma znacka kampane v ID vzorku (_J_ jaro, _L_ leto, _P_ podzim),
    protoze je jednoznacna. Zari se v datech vyskytuje u letni i podzimni
    kampane, takze podle mesice samotneho rozhodnout nelze. Pokud znacka
    chybi, rozhodne mesic odberu.

    Returns:
        (je_letni, duvod) - duvod je text do poznamky
    """
    from datetime import datetime

    ident = sample_id or ""
    for znacka, letni in (("_L_", True), ("_J_", False), ("_P_", False)):
        if znacka in ident:
            return letni, f"kampaň {znacka.strip('_')}"

    try:
        mesic = datetime.strptime(datum_str, "%d.%m.%Y").month
    except (TypeError, ValueError):
        return False, "nerozpoznatelné datum odběru"
    return mesic in LETNI_MESICE, f"měsíc odběru {mesic}"


def _reko_mept(data, by_id, sloupec):
    """Index REKOnstruovanych taxocenoz MEPT.

    REKO = pocet zjistenych taxonu ze seznamu ocekavanych / pocet ocekavanych

    Args:
        sloupec: TAXONY_MEPT_VLT (povodi Labe) nebo TAXONY_MEPT_MO (Morava)
    """
    ocekavane = {
        tid for tid, info in by_id.items()
        if info.get(sloupec)
    }
    if not ocekavane:
        return None, 0, 0

    zjistene = ocekavane & set(data)
    return round(len(zjistene) / len(ocekavane), 4), len(zjistene), len(ocekavane)


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte MZB hodnoceni velke nebroditelne reky.

    Args:
        potencial: True u silne ovlivnenych utvaru - meni pouze hranice
            trid, sada metrik i meze zustavaji shodne (metodika potencialu
            2013, Tab. 5 uvadi pro velke reky tytez metriky)
    """
    try:
        id_utvaru = utvar_vzorku(sample_id, db_connection)
        umori = povodi(id_utvaru)
        if umori is None:
            return {
                "MZB_POZN": (
                    f"Utvar {id_utvaru} neni ve vymezeni velkych nebroditelnych rek"
                )
            }

        from PyQt6.QtSql import QSqlQuery

        query = QSqlQuery(db_connection)
        query.prepare("SELECT DATE FROM samples WHERE SAMPLE_ID = ?")
        query.addBindValue(sample_id)
        datum = query.value(0) if (query.exec() and query.next()) else None

        letni, duvod = _je_letni(datum, sample_id)
        if not letni:
            return {
                "MZB_CELKEM": None,
                "MZB_CLASS": None,
                "MZB_POZN": (
                    f"Nehodnoceno: velké řeky se hodnotí pouze z letních "
                    f"vzorků, vzorek je z {datum} ({duvod})"
                ),
            }

        taxa_data = nacti_data_vzorku(db_connection, sample_id)
        if not taxa_data:
            return {"MZB_POZN": "Ve vzorku nejsou zadna taxonomicka data"}

        taxalist = nacti_taxalist(db_connection, "taxalist_mzb", TRAIT_SLOUPCE)
        by_id = taxalist["by_id"]
        puvodni_id = {}
        resolved = vyres_synonyma(taxa_data, taxalist["by_name"], puvodni_id)
        if not resolved:
            return {"MZB_POZN": "Po vyreseni synonym nezbyly zadne taxony"}

        # letni vzorky pouzivaji jarni adjustacni sadu (leden-srpen)
        data = aplikuj_adjustace(
            resolved,
            nacti_adjustaci(db_connection, "METR_J"),
            taxalist["children"],
            puvodni_id,
        )

        metriky = {}
        cache = {}

        # --- VR01: REKO MEPT ---
        sloupec = SLOUPEC_REKO[umori]
        metriky["VR01"], zjisteno, ocekavano = _reko_mept(data, by_id, sloupec)

        # --- VR02: Margalefuv index diverzity ---
        celkova_abundance = sum(data.values())
        metriky["VR02"] = (
            round((len(data) - 1) / safe_log(celkova_abundance), 3)
            if celkova_abundance > 1 else None
        )

        # --- VR03: ricni zonace epipotamal [%] ---
        citatel = jmenovatel = 0.0
        for tid, abundance in data.items():
            info = by_id.get(tid)
            if info is None or info.get("ZEP") is None:
                continue
            log_ab = safe_log(abundance)
            if log_ab <= 0:
                continue
            citatel += log_ab * info["ZEP"] / 10
            jmenovatel += log_ab
        metriky["VR03"] = (
            round(citatel / jmenovatel * 100, 3) if jmenovatel > 0 else None
        )

        # --- VR04: EPT Abu [%] ---
        ept_log = celkem_log = 0.0
        for tid, abundance in data.items():
            log_ab = safe_log(abundance)
            if log_ab <= 0:
                continue
            celkem_log += log_ab
            if patri_do_skupiny(tid, EPT, by_id, cache):
                ept_log += log_ab
        metriky["VR04"] = (
            round(ept_log / celkem_log * 100, 2) if celkem_log > 0 else None
        )

        # --- VR05: saprobni index ---
        citatel = jmenovatel = 0.0
        for tid, abundance in data.items():
            info = by_id.get(tid)
            if info is None or info["SZS"] is None or info["SZG"] is None:
                continue
            ab = to_float(abundance, 0.0)
            citatel += ab * info["SZS"] * info["SZG"]
            jmenovatel += ab * info["SZG"]
        metriky["VR05"] = round(citatel / jmenovatel, 3) if jmenovatel > 0 else None

        # --- VR06: SPEAR organic ---
        citatel = jmenovatel = 0.0
        for tid, abundance in data.items():
            info = by_id.get(tid)
            if info is None or info.get("SPEAR_ORG") is None:
                continue
            log_ab = safe_log(abundance)
            if log_ab <= 0:
                continue
            citatel += log_ab * info["SPEAR_ORG"]
            jmenovatel += log_ab
        metriky["VR06"] = round(citatel / jmenovatel, 3) if jmenovatel > 0 else None

        # --- prevod na EQR a multimetrika ---
        eqr_hodnoty = preved_na_eqr(metriky, EQR_TABLE)
        multimetrika, pouzite = vazeny_prumer(eqr_hodnoty, EQR_TABLE)
        trida = klasifikuj(multimetrika, hranice=HRANICE_VR, ostre=True)

        pozn = (
            f"Velka nebroditelna reka ({umori}), "
            f"{'potencial' if potencial else 'stav'}. "
            f"REKO: {zjisteno}/{ocekavano} taxonu, "
            f"metrik pouzito: {len(pouzite)}/{len(METRIKY)}"
        )
        if celkova_abundance < MIN_JEDINCU:
            pozn += (
                f". POZOR: vzorek ma jen {int(celkova_abundance)} jedincu "
                f"(metodika doporucuje alespon {MIN_JEDINCU}), "
                f"vysledek nemusi byt spolehlivy"
            )

        smaz_vysledky(db_connection, sample_id, METRIKY + ["MZB_CELKEM"])
        radky = [
            {
                "metric": m,
                "val": metriky[m],
                "eqr": eqr_hodnoty.get(f"{m}_EQR"),
                "class": None,
                "pozn": f"{NAZVY[m]} (velke reky, {umori})",
            }
            for m in METRIKY
            if je_platna(metriky.get(m))
        ]
        radky.append(
            {
                "metric": "MZB_CELKEM",
                "val": multimetrika,
                "eqr": multimetrika,
                "class": trida,
                "pozn": pozn,
            }
        )
        zapis_vysledky(db_connection, sample_id, radky)

        vysledek = dict(metriky)
        vysledek.update(eqr_hodnoty)
        vysledek["MZB_CELKEM"] = multimetrika
        vysledek["MZB_CLASS"] = trida
        vysledek["MZB_POZN"] = pozn
        vysledek["MZB_TYP_HODNOCENI"] = "POTENCIAL" if potencial else "STAV"
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"MZB_POZN": f"Kriticka chyba: {e}"}
