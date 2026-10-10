"""
Fytobentos (FB) - vysychave (intermittent) toky.

Bez rozliseni typologie - jeden postup pro vsechny vysychave toky.

Metriky:
    FI01  Saprobni index (MSZS vazene MSZG)
    FI02  Salinita (SAL), vazeno abundanci
    FI03  Naroky na kyslik (O2), vazeno abundanci

Multimetrika = odmocnina z prosteho prumeru EQR jednotlivych metrik.
"""

from __future__ import annotations

from .common import (
    je_platna,
    klasifikuj,
    nacti_data_vzorku,
    nacti_taxalist,
    preved_na_eqr,
    prosty_prumer,
    smaz_vysledky,
    to_float,
    vyres_synonyma,
    zapis_vysledky,
)

TRAIT_SLOUPCE = ["MSZS", "MSZG", "SAL", "O2"]
METRIKY = ["FI01", "FI02", "FI03"]


def _vazeny_prumer(data, by_id, trait):
    """Prumer trait hodnoty vazeny abundanci.

    Delitelem je soucet abundanci taxonu, ktere danou hodnotu **maji**,
    ne celkova abundance vzorku. To je podstatny rozdil: kdyby se delilo
    celkovou abundanci, kazdy taxon bez vyplnene hodnoty by vysledek
    stahoval k nule, i kdyz o nem nic nevime. Metrika by pak merila
    hlavne uplnost taxalistu, ne stav lokality.

    Overeno proti kontrolnim datum metodiky: hodnoty v nich jsou zlomky
    se spolecnym jmenovatelem, ktery odpovida souctu abundanci taxonu
    s vyplnenou hodnotou, nikoli souctu vsech.
    """
    citatel = jmenovatel = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or info.get(trait) is None:
            continue
        ab = to_float(abundance, 0.0)
        citatel += info[trait] * ab
        jmenovatel += ab
    return round(citatel / jmenovatel, 3) if jmenovatel > 0 else None

#: Prevodni tabulka {metrika: (dolni_mez, horni_mez, invertovat, vaha)}.
#:
#: Invertuji se vsechny tri metriky: u vsech znamena vyssi hodnota horsi
#: stav. U salinity i naroku na kyslik to plyne uz z povahy veci a proti
#: kontrolnim datum metodiky to vychazi jednoznacne - korelace mezi
#: hodnotou metriky a jejim EQR je -0,85 (SAL) a -0,94 (O2). Driv se
#: obe metriky neinvertovaly, takze multimetrika sla proti smyslu:
#: proti referencnim EQR vychazela korelace -0,53.
EQR_TABLE = {
    "FI01": (1.129, 1.983, True, 1.0),
    "FI02": (1.692, 2.356, True, 1.0),
    "FI03": (1.296, 2.501, True, 1.0),
}


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte FB hodnoceni pro vysychavy tok."""
    try:
        taxa_data = nacti_data_vzorku(db_connection, sample_id)
        if not taxa_data:
            return {"FB_POZN": "Ve vzorku nejsou zadna taxonomicka data"}

        taxalist = nacti_taxalist(db_connection, "taxalist_fb", TRAIT_SLOUPCE)
        data = vyres_synonyma(taxa_data, taxalist["by_name"])
        if not data:
            return {"FB_POZN": "Po vyreseni synonym nezbyly zadne taxony"}

        by_id = taxalist["by_id"]
        celkova_abundance = sum(data.values())
        metriky = {}

        # FI01: saprobni index
        citatel = jmenovatel = 0.0
        for taxon_id, abundance in data.items():
            info = by_id.get(taxon_id)
            if info is None or info["MSZS"] is None or info["MSZG"] is None:
                continue
            ab = to_float(abundance, 0.0)
            citatel += ab * info["MSZS"] * info["MSZG"]
            jmenovatel += ab * info["MSZG"]
        metriky["FI01"] = round(citatel / jmenovatel, 3) if jmenovatel > 0 else None

        # FI02, FI03: trait metriky vazene abundanci
        for metrika, trait in (("FI02", "SAL"), ("FI03", "O2")):
            metriky[metrika] = _vazeny_prumer(data, by_id, trait)

        eqr_hodnoty = preved_na_eqr(metriky, EQR_TABLE)
        multimetrika, pocet = prosty_prumer(eqr_hodnoty, odmocnina=True)
        trida = klasifikuj(multimetrika, potencial)

        pozn = f"Vysychavy tok, metrik pouzito: {pocet}/{len(METRIKY)}"

        smaz_vysledky(db_connection, sample_id, METRIKY + ["FB_CELKEM"])
        radky = [
            {
                "metric": m,
                "val": metriky[m],
                "eqr": eqr_hodnoty.get(f"{m}_EQR"),
                "class": None,
                "pozn": "Vysychavy tok",
            }
            for m in METRIKY
            if je_platna(metriky.get(m))
        ]
        radky.append(
            {
                "metric": "FB_CELKEM",
                "val": multimetrika,
                "eqr": multimetrika,
                "class": trida,
                "pozn": pozn,
            }
        )
        zapis_vysledky(db_connection, sample_id, radky)

        vysledek = dict(metriky)
        vysledek.update(eqr_hodnoty)
        vysledek["FB_CELKEM"] = multimetrika
        vysledek["FB_CLASS"] = trida
        vysledek["FB_POZN"] = pozn
        vysledek["FB_TYP_HODNOCENI"] = "POTENCIAL" if potencial else "STAV"
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"FB_POZN": f"Kriticka chyba: {e}"}
