"""
Vypocet metrik MB01-MB16 pro makrozoobentos (MZB).

Metriky se pocitaji z adjustovanych dat vzorku a trait hodnot z tabulky
`taxalist_mzb`. Modul je sdileny vsemi MZB variantami (broditelne /
nebroditelne toky); jednotlive varianty se lisi az prevodem na EQR.

Prehled metrik:
    MB01  Saprobni index (vazeny SZS podle SZG)
    MB02  Litoral - preference litoralu (HLI)
    MB03  RETI - podil retencnich funkcnich skupin
    MB04  EPT Abu - log-abundance Ephemeroptera + Plecoptera + Trichoptera [%]
    MB05  Margalefuv index diverzity
    MB06  Metaritral (ZMR) [%]
    MB07  B-index - shoda pozorovanych a predikovanych taxonu [%]
    MB08  Ephemeroptera Abu [%]
    MB09  Epiritral (ZER) [%]
    MB10  Hyporitral (ZHR) [%]
    MB11  Pocet taxonu pakomaru (Chironomidae)
    MB12  Pocet celedi
    MB13  EPT Tax - pocet taxonu EPT
    MB14  Plecoptera Abu [%]
    MB15  Spasaci (FGR)
"""

from __future__ import annotations

from .common import (
    aplikuj_adjustace,
    log_abundance,
    nacti_adjustaci,
    nacti_taxalist,
    patri_do_skupiny,
    to_float,
    vyres_synonyma,
)

#: Trait sloupce, ktere MZB metriky potrebuji z tabulky taxalist_mzb.
TRAIT_SLOUPCE = [
    "SZS", "SZG",              # saprobita
    "HLI",                     # litoral
    "ZER", "ZMR", "ZHR", "ZEP",  # zonace: epi- / meta- / hyporitral, epipotamal
    "FGR", "FMI", "FXY", "FSH",  # funkcni skupiny
    "FGA", "FAF", "FPF", "FPR", "FPA", "FOT",
    "SPEAR_ORG",               # index citlivosti SPEAR organic
]

EPT = ("Ephemeroptera", "Plecoptera", "Trichoptera")


def priprav_data(db_connection, sample_id, metr_adj_type, pred_adj_type):
    """Nacte a adjustuje data vzorku pro vypocet MZB metrik.

    Returns:
        dict s klici:
            taxalist   - vysledek nacti_taxalist()
            metr_data  - {taxon_id: abundance} po METR adjustaci
            pred_data  - {taxon_id: abundance} po PRED adjustaci
        nebo None, pokud vzorek neobsahuje pouzitelna data.
    """
    from .common import nacti_data_vzorku

    from .common import nezname_taxony, ohlas_nezname

    taxa_data = nacti_data_vzorku(db_connection, sample_id)
    if not taxa_data:
        return None

    taxalist = nacti_taxalist(db_connection, "taxalist_mzb", TRAIT_SLOUPCE)

    # Taxony, ktere v seznamu nejsou, by pri reseni synonym tise vypadly.
    # U pocetnych druhu to vysledek posouva, proto na ne upozornime.
    chybejici = nezname_taxony(taxa_data, taxalist["by_name"])
    poznamka = ohlas_nezname(chybejici, taxa_data, sample_id, "taxalist_mzb")

    # Prejmenovane taxony maji v adjustacnim predpisu jeste stare ID,
    # proto si drzime, pod jakym jmenem byl taxon ve vzorku zapsany.
    puvodni_id = {}
    resolved = vyres_synonyma(taxa_data, taxalist["by_name"], puvodni_id)
    if not resolved:
        return None

    children = taxalist["children"]
    metr_data = aplikuj_adjustace(
        resolved, nacti_adjustaci(db_connection, metr_adj_type), children,
        puvodni_id,
    )
    pred_data = aplikuj_adjustace(
        resolved, nacti_adjustaci(db_connection, pred_adj_type), children,
        puvodni_id,
    )

    return {
        "taxalist": taxalist,
        "metr_data": metr_data,
        "pred_data": pred_data,
        "chybejici": chybejici,
        "poznamka": poznamka,
    }


def _vazeny_trait(data, by_id, trait, nasobitel=1.0, delitel=10.0):
    """Log-vazeny prumer jedne trait hodnoty pres taxony vzorku.

    Vraci None, pokud zadny taxon nema danou trait hodnotu.
    """
    citatel = 0.0
    jmenovatel = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or info.get(trait) is None:
            continue
        log_ab = log_abundance(abundance)
        if log_ab <= 0:
            continue
        citatel += log_ab * info[trait] / delitel
        jmenovatel += log_ab
    if jmenovatel <= 0:
        return None
    return round(citatel / jmenovatel * nasobitel, 5)


def _podil_skupiny(data, by_id, skupiny, cache):
    """Podil log-abundance dane taxonomicke skupiny na celku [%]."""
    skupina_log = 0.0
    celkem_log = 0.0
    for taxon_id, abundance in data.items():
        log_ab = log_abundance(abundance)
        if log_ab <= 0:
            continue
        celkem_log += log_ab
        if patri_do_skupiny(taxon_id, skupiny, by_id, cache):
            skupina_log += log_ab
    if celkem_log <= 0:
        return None
    return round(skupina_log / celkem_log * 100, 5)


def spocitej_metriky(priprava, db_connection=None, loc_id=None, season=None):
    """Spocita metriky MB01-MB15 pro pripravena data vzorku.

    Args:
        priprava: vysledek priprav_data()
        db_connection, loc_id, season: potrebne pro MB07 (B-index);
            pokud nejsou zadany, MB07 se nepocita

    Returns:
        dict {nazev_metriky: hodnota nebo None}
    """
    by_id = priprava["taxalist"]["by_id"]
    data = priprava["metr_data"]
    cache = {}
    m = {}

    # --- MB01: saprobni index ---
    citatel = jmenovatel = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or info["SZS"] is None or info["SZG"] is None:
            continue
        ab = to_float(abundance, 0.0)
        citatel += ab * info["SZS"] * info["SZG"]
        jmenovatel += ab * info["SZG"]
    m["MB01"] = round(citatel / jmenovatel, 5) if jmenovatel > 0 else None

    # --- MB02: litoral ---
    m["MB02"] = _vazeny_trait(data, by_id, "HLI", nasobitel=100.0)

    # --- MB03 + MB15: funkcni skupiny ---
    fg = ["FGR", "FMI", "FXY", "FSH", "FGA", "FAF", "FPF", "FOT"]
    soucty = {k: 0.0 for k in fg}
    log_celkem = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or any(info[k] is None for k in fg):
            continue
        log_ab = log_abundance(abundance)
        if log_ab <= 0:
            continue
        for k in fg:
            soucty[k] += log_ab * info[k] / 10
        log_celkem += log_ab

    jmenovatel_reti = sum(soucty.values())
    if log_celkem > 0 and jmenovatel_reti > 0:
        m["MB03"] = round(
            (soucty["FGR"] + soucty["FXY"] + soucty["FSH"]) / jmenovatel_reti, 5
        )
        # cVSpas je podle metodiky procentualni zastoupeni potravni strategie
        # spasacu, tedy stejne jako metriky zonace se uvadi v procentech.
        m["MB15"] = round(soucty["FGR"] / log_celkem * 100, 5)
    else:
        m["MB03"] = None
        m["MB15"] = None

    # --- MB04, MB08, MB13, MB14: taxonomicke skupiny ---
    m["MB04"] = _podil_skupiny(data, by_id, EPT, cache)
    m["MB08"] = _podil_skupiny(data, by_id, ("Ephemeroptera",), cache)
    m["MB14"] = _podil_skupiny(data, by_id, ("Plecoptera",), cache)

    m["MB13"] = sum(
        1 for tid in data if patri_do_skupiny(tid, EPT, by_id, cache)
    )

    # --- MB05: Margalefuv index ---
    #
    # Metodika uvadi (S-1)/ln(N). Ve jmenovateli se ale stejne jako
    # u ostatnich metrik pouziva transformace ln(N+1) - proti oficialnim
    # hodnotam sedi presne u 176 vzorku misto 149. Rozdil je maly, protoze
    # celkova abundance jde do stovek az tisicu, ale je systematicky.
    celkova_abundance = sum(data.values())
    m["MB05"] = (
        round((len(data) - 1) / log_abundance(celkova_abundance), 5)
        if celkova_abundance > 1
        else None
    )

    # --- MB06, MB09, MB10: zonace ---
    m["MB06"] = _vazeny_trait(data, by_id, "ZMR", nasobitel=100.0)
    m["MB09"] = _vazeny_trait(data, by_id, "ZER", nasobitel=100.0)
    m["MB10"] = _vazeny_trait(data, by_id, "ZHR", nasobitel=100.0)

    # --- MB16: ricni zonace epipotamal ---
    m["MB16"] = _vazeny_trait(data, by_id, "ZEP", nasobitel=100.0)

    # --- MB17: index citlivosti spolecenstva SPEAR organic ---
    #
    # Na rozdil od metrik zonace se nedeli souctem logaritmovanych abundanci,
    # ale POCTEM TAXONU ve vzorku:
    #
    #     SPEAR = SUM(ln(abundance + 1) * SPEAR_ORG) / N
    #
    # kde N je pocet taxonu ve vzorku. Nejde tedy o vazeny prumer, ale
    # o soucet prispevku vydeleny poctem taxonu.
    # Pozor na zaklad logaritmu: na rozdil od ostatnich metrik se zde pouziva
    # DEKADICKY logaritmus. S prirozenym vychazi index zhruba 2,3x nizsi
    # (az -3,1 misto oficialnich -1,1).
    from math import log10

    citatel = 0.0
    for taxon_id, abundance in data.items():
        info = by_id.get(taxon_id)
        if info is None or info.get("SPEAR_ORG") is None:
            continue
        ab = to_float(abundance, 0.0)
        if ab <= 0:
            continue
        citatel += log10(ab + 1.0) * info["SPEAR_ORG"]
    m["MB17"] = round(citatel / len(data), 5) if data else None

    # --- MB11: pocet taxonu pakomaru ---
    m["MB11"] = sum(
        1 for tid in data if patri_do_skupiny(tid, ("Chironomidae",), by_id, cache)
    )

    # --- MB12: pocet celedi ---
    from .common import spocitej_celedi

    m["MB12"] = spocitej_celedi(data, by_id)

    # --- MB07: B-index ---
    m["MB07"] = None
    if db_connection is not None and loc_id and season:
        m["MB07"] = _b_index(
            priprava["pred_data"], by_id, db_connection, loc_id, season,
            priprava["taxalist"],
        )

    return m


def _b_index(pred_data, by_id, db_connection, loc_id, season, taxalist):
    """B-index: shoda pozorovanych taxonu s predikci modelu B_index2.

    Vraci procento pozorovanych taxonu vuci sume pravdepodobnosti
    predikovanych taxonu (pravdepodobnost >= 50 %), nebo None.
    """
    try:
        import os
        import sys

        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        from B_index2 import PredictTaxaBatch

        predictor = PredictTaxaBatch(db_path=db_connection.databaseName())
        predictor.connect()
        try:
            predikce = predictor.process_single_locality(loc_id, season)
        finally:
            predictor.disconnect()

        if not predikce:
            return None

        predikovane = {taxon: val for taxon, val in predikce if val >= 50}
        suma_pravdepodobnosti = sum(predikovane.values())
        if not predikovane or suma_pravdepodobnosti <= 0:
            return None

        # Predikcni model pouziva jiny zapis nazvu nez taxonomicky seznam
        # ("Elmis sp. lv." vs "Elmis sp. Lv."), proto se porovnava az po
        # sjednoceni zapisu - jinak by se cast taxonu nikdy nesparovala
        # a index B vychazel systematicky nizsi.
        #
        # Navic drzi jmena ve stavu, v jakem byla podkladova databaze
        # porizena, takze cast z nich je dnes v seznamu vedena jako
        # synonymum (Lasiocephala basalis -> Lepidostoma basale). Data
        # vzorku uz pres vyres_synonyma() prosla, predikce ne - obe strany
        # proto jeste prevedeme na platna jmena.
        from .common import mapa_synonym, normalizuj_pro_porovnani

        synonyma = mapa_synonym(taxalist)

        def klic(nazev):
            n = normalizuj_pro_porovnani(nazev)
            return synonyma.get(n, n)

        pozorovane = {
            klic(by_id[tid]["name"]) for tid in pred_data if tid in by_id
        }
        shody = pozorovane & {klic(t) for t in predikovane}

        # Index B = zjisteny pocet taxonu / ocekavany pocet taxonu.
        # Pravdepodobnosti jsou ulozene v procentech, proto nasobeni stem.
        #
        # Metodika (kap. 5.5): "Index B se pohybuje od 0 nad 1, pricemz
        # hodnoty vyssi nez 1 lze povazovat za 1." Vice zjistenych taxonu,
        # nez model ocekaval, uz nelze povazovat za lepsi shodu.
        b_index = len(shody) / suma_pravdepodobnosti * 100
        return round(min(b_index, 1.0), 5)

    except Exception as e:  # noqa: BLE001 - B-index je volitelny, nesmi shodit vypocet
        print(f"[MZB] B-index nebylo mozne spocitat: {e}")
        return None
