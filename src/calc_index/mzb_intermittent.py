"""
MZB - vysychave (intermittent) toky, ekologicky stav / potencial.

Bez rozliseni typologie - jeden postup pro vsechny vysychave toky.

Metriky:
    MI01  Podil posvatek (Plecoptera) na celkove abundanci [%]
    MI02  Margalefuv index diverzity
    MI03  Saprobita (SZA + SZP) [%], vazeno log-abundanci
    MI04  Teplomilnost (temp_pref_WAR + temp_pref_EUT) [%], vazeno log-abundanci
    MI05  Reprodukcni strategie (repr_frc + repr_tec) [%], vazeno log-abundanci

Multimetrika = odmocnina z prosteho prumeru EQR jednotlivych metrik.

Dva detaily, na kterych zalezi vic, nez se zda
--------------------------------------------

**MI01 a MI02 se pocitaji z celeho vzorku**, ne jen z taxonu, ktere zna
taxalist. Diverzita i celkova abundance jsou vlastnosti vzorku; kdyby se
pocitaly az z taxonu po vyreseni synonym, kazda mezera v taxalistu by
Margalefuv index snizila a podil posvatek naopak zvysila. Overeno proti
kalibracnim datum metodiky: pri pocitani z celeho vzorku sedi Margaleff
u vsech 222 jarnich vzorku presne, pri pocitani jen ze znamych taxonu
u 24 z nich.

**Trait metriky MI03-MI05 vazi log-abundanci** ln(x+1), stejne jako
metriky staletekoucich toku (viz `mzb_metrics._vazeny_trait`). Trait
hodnoty jsou v taxalistu rozdelene po deseti bodech mezi valence dane
vlastnosti, vysledek je proto podil v procentech.
"""

from __future__ import annotations

from .common import (
    je_platna,
    klasifikuj,
    log_abundance,
    nacti_data_vzorku,
    nacti_taxalist,
    patri_do_skupiny,
    preved_na_eqr,
    prosty_prumer,
    safe_log,
    smaz_vysledky,
    to_float,
    vyres_synonyma,
    zapis_vysledky,
)

#: Vsechny valence dane vlastnosti. Nacitaji se cele, ne jen sledovane
#: dve - jinak by ve jmenovateli chybely taxony, ktere vlastnost maji
#: popsanou, ale u sledovanych valenci maji nulu. Takovy taxon do
#: jmenovatele patri: je to taxon, ktery sledovanou vlastnost nema, ne
#: taxon, o kterem se nic nevi. Bez toho metriky vyskoci nahoru -
#: u MI05 az na sedminasobek.
VALENCE = {
    ("SZA", "SZP"): ["SZX", "SZO", "SZB", "SZA", "SZP"],
    ("temp_pref_WAR", "temp_pref_EUT"): [
        "temp_pref_VCO", "temp_pref_COD", "temp_pref_MOD",
        "temp_pref_WAR", "temp_pref_EUT",
    ],
    ("repr_frc", "repr_tec"): [
        "repr_ovo", "repr_fie", "repr_cie", "repr_fic", "repr_frc",
        "repr_vec", "repr_tec", "repr_ase", "repr_pas",
    ],
}

#: Sloupce taxalistu, ktere je potreba nacist.
TRAIT_SLOUPCE = [s for valence in VALENCE.values() for s in valence]

#: Soucet bodu, ktere se mezi valence jedne vlastnosti rozdeluji.
BODU_NA_VLASTNOST = 10.0

METRIKY = ["MI01", "MI02", "MI03", "MI04", "MI05"]

#: Prevodni tabulka {metrika: (dolni_mez, horni_mez, invertovat, vaha)}.
#: Vahy jsou u vysychavych toku shodne - multimetrika je prosty prumer.
EQR_TABLE = {
    "MI01": (0.0, 87.435, False, 1.0),
    "MI02": (4.028, 10.754, False, 1.0),
    "MI03": (11.629, 48.025, True, 1.0),
    "MI04": (43.121, 75.602, True, 1.0),
    "MI05": (0.0, 24.998, False, 1.0),
}


def _vazeny_podil(data, by_id, traity):
    """Podil sledovanych valenci na celku [%], vazeny log-abundanci.

    Do prumeru vstupuji taxony, ktere maji danou vlastnost v taxalistu
    popsanou - tedy takove, u nichz je alespon jedna valence te
    vlastnosti nenulova. Taxon s nulou u sledovanych dvou valenci, ale
    nenulovy jinde, tedy do jmenovatele patri; prispiva do nej nulou,
    coz je vecne spravne - je to taxon, ktery sledovanou vlastnost nema.
    """
    vsechny = VALENCE[tuple(traity)]
    citatel = 0.0
    jmenovatel = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or not any(info.get(t) for t in vsechny):
            continue
        vaha = log_abundance(to_float(abundance, 0.0))
        if vaha <= 0:
            continue
        citatel += vaha * sum(info.get(t) or 0.0 for t in traity)
        jmenovatel += vaha
    if jmenovatel <= 0:
        return None
    return round(citatel / jmenovatel / BODU_NA_VLASTNOST * 100, 3)


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte MZB hodnoceni pro vysychavy tok."""
    try:
        taxa_data = nacti_data_vzorku(db_connection, sample_id)
        if not taxa_data:
            return {"MZB_POZN": "Ve vzorku nejsou zadna taxonomicka data"}

        taxalist = nacti_taxalist(db_connection, "taxalist_mzb", TRAIT_SLOUPCE)
        data = vyres_synonyma(taxa_data, taxalist["by_name"])
        if not data:
            return {"MZB_POZN": "Po vyreseni synonym nezbyly zadne taxony"}

        by_id = taxalist["by_id"]
        cache = {}
        metriky = {}

        # MI01 a MI02 se pocitaji z celeho vzorku, vcetne taxonu, ktere
        # taxalist nezna - viz poznamka v hlavicce modulu.
        celkova_abundance = sum(
            to_float(z["abundance"], 0.0) for z in taxa_data)
        pocet_taxonu = len(taxa_data)

        # MI01: podil posvatek. Ktery taxon je posvatka, urcuje taxalist,
        # ale delitelem je abundance celeho vzorku.
        plecoptera = sum(
            ab for tid, ab in data.items()
            if patri_do_skupiny(tid, ("Plecoptera",), by_id, cache)
        )
        metriky["MI01"] = (
            round(plecoptera / celkova_abundance * 100, 3)
            if celkova_abundance > 0 else None
        )

        # MI02: Margalefuv index
        metriky["MI02"] = (
            round((pocet_taxonu - 1) / safe_log(celkova_abundance), 3)
            if celkova_abundance > 1 else None
        )

        # MI03-MI05: trait metriky
        metriky["MI03"] = _vazeny_podil(data, by_id, ("SZA", "SZP"))
        metriky["MI04"] = _vazeny_podil(
            data, by_id, ("temp_pref_WAR", "temp_pref_EUT")
        )
        metriky["MI05"] = _vazeny_podil(data, by_id, ("repr_frc", "repr_tec"))

        eqr_hodnoty = preved_na_eqr(metriky, EQR_TABLE)
        multimetrika, pocet = prosty_prumer(eqr_hodnoty, odmocnina=True)
        trida = klasifikuj(multimetrika, potencial)

        pozn = f"Vysychavy tok, metrik pouzito: {pocet}/{len(METRIKY)}"

        smaz_vysledky(db_connection, sample_id, METRIKY + ["MZB_CELKEM"])
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
