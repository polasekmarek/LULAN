"""
Fytoplankton stojatych vod - multimetricky index CZ-PHYPI.

Metodika:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, kap. 6.
    metodiky/OOV-Metodika_hodnoceni_ ekologicky potencial_ kategorie_jezero-20140301.pdf

Metriky (Tabulka 4)
-------------------
    FPJ01  koncentrace chlorofylu-a [ug/l]
    FPJ02  objemova biomasa fytoplanktonu [mm3/l]
    FPJ03  podil sinic na celkove biomase [%]
    FPJ04  troficky index fytoplanktonu

Vsechny ctyri metriky rostou se zatizenim.

Troficky index
--------------
Podle Phillips a kol. (2013):

    TI = SUM(p_i * s_i)

kde p_i je proporcni zastoupeni taxonu v celkove biomase (0-1) a s_i jeho
troficke optimum (Priloha 2, modul `jezera_fp_optima`).

POZOR na jednu vec: metodika rika "p je proporční zastoupení (0-1) daného
taxonu v celkové biomase". Suma vah je tedy 1 jen tehdy, kdyz se scitaji
VSECHNY taxony vzorku vcetne tech bez znameho optima - a ty maji s = 0.
Nepocita se tedy vazeny prumer pres taxony se znamym optimem, nybrz suma
pres vsechny; taxony bez optima vysledek redi smerem k nule.

Podil sinic
-----------
"Pro výpočet tohoto ukazatele byla zahrnuta pouze biomasa druhů sinic
tvořících vodní květy, pikoplanktonní druhy nebyly započteny."

Pikoplanktonni rody se proto z citatele odectou - viz PIKOPLANKTON.

Vstupni data
------------
Biomasa taxonu se cte ze sloupce `data.BIOMASA` [mm3/l]. Kdyz chybi,
pouzije se `data.val` (pocetnost), coz je ale podle metodiky
"zcela nevhodné pro stanovení ekologického potenciálu" - metrika se v tom
pripade nespocita a do vysledku se zapise poznamka.

Hodnotici jednotka
------------------
Vzorek. Metodika doporucuje prumerovat pres vegetacni sezonu (duben-rijen,
min. 1x mesicne); prumerovani pres sezonu resi `jezera_runner`.
"""

from __future__ import annotations

from .common import to_float
from .jezera_common import (
    KLESA, MIN_PODIL_METRIK, ROSTE, TRIDY_JEZERA, eqr_z_bodu,
    klasifikuj_jezero, oboduj,
)
from .jezera_fp_optima import troficke_optimum, zarazeni

#: Metriky a jejich smer pusobeni.
METRIKY = {
    "FPJ01": ("Koncentrace chlorofylu-a [µg/l]", ROSTE),
    "FPJ02": ("Biomasa fytoplanktonu [mm³/l]", ROSTE),
    "FPJ03": ("Podíl sinic na biomase [%]", ROSTE),
    "FPJ04": ("Trofický index fytoplanktonu", ROSTE),
}

#: Hranicni hodnoty podle Tabulky 4, klic (A, G, H) - viz jezera_typologie.
#: Metodika uvadi hranice jen podle nadmorske vysky (A) a doby zdrzeni (H),
#: prumerna hloubka (G) se u fytoplanktonu neuplatnuje. Klic proto obsahuje
#: jen dvojici (A, H).
#:
#:   {(A, H): {metrika: (dolni, horni)}}
MEZE = {
    (1, 1): {"FPJ01": (30, 40), "FPJ02": (5, 10),
             "FPJ03": (15, 20), "FPJ04": (0.6, 0.8)},
    (1, 2): {"FPJ01": (20, 30), "FPJ02": (3, 5),
             "FPJ03": (10, 15), "FPJ04": (0.5, 0.6)},
    (1, 3): {"FPJ01": (10, 30), "FPJ02": (2, 5),
             "FPJ03": (10, 15), "FPJ04": (0.4, 0.5)},
    (2, 1): {"FPJ01": (20, 40), "FPJ02": (5, 10),
             "FPJ03": (15, 20), "FPJ04": (0.5, 0.6)},
    (2, 2): {"FPJ01": (10, 20), "FPJ02": (3, 8),
             "FPJ03": (10, 15), "FPJ04": (0.4, 0.5)},
    (2, 3): {"FPJ01": (10, 20), "FPJ02": (2, 5),
             "FPJ03": (10, 15), "FPJ04": (0.4, 0.5)},
    (3, 1): {"FPJ01": (5, 10), "FPJ02": (1.2, 2),
             "FPJ03": (1, 10), "FPJ04": (0.1, 0.2)},
    (3, 2): {"FPJ01": (5, 8), "FPJ02": (1, 1.2),
             "FPJ03": (1, 10), "FPJ04": (0.1, 0.2)},
    (3, 3): {"FPJ01": (3, 5), "FPJ02": (0.8, 1.2),
             "FPJ03": (1, 10), "FPJ04": (0.1, 0.2)},
}

#: Trida sinic v taxalistu.
SINICE = "Cyanobacteria"

#: Pikoplanktonni rody sinic - do podilu sinic se nezapocitavaji, protoze
#: netvori vodni kvety (kap. 6.2). Seznam odpovida rodum, ktere se v ceskych
#: nadrzich bezne vyskytuji v pikoplanktonni frakci.
PIKOPLANKTON = {
    "Aphanocapsa", "Aphanothece", "Cyanobium", "Cyanodictyon",
    "Cyanonephron", "Merismopedia", "Rhabdoderma", "Rhabdogloea",
    "Snowella", "Synechococcus", "Synechocystis",
}


def _rod(nazev):
    """Rodove jmeno z nazvu taxonu."""
    if not nazev:
        return None
    casti = str(nazev).strip().split()
    return casti[0] if casti else None


def _trida(taxon):
    """Trida taxonu - ze vstupnich dat, jinak dohledana podle rodu.

    Priloha 2 vede u kazdeho rodu i tridu, takze aplikace nepotrebuje
    zvlastni taxalist fytoplanktonu stojatych vod. Bez teto zalohy by
    metrika podilu sinic tise vychazela nulova - to je zradne, protoze
    nula je zaroven nejlepsi mozna hodnota.
    """
    if taxon.get("trida"):
        return taxon["trida"]
    return zarazeni(_rod(taxon.get("nazev")))[1]


def troficky_index(taxony):
    """Spocita troficky index fytoplanktonu.

    Args:
        taxony: seznam dictu s klici `nazev`, `biomasa` a volitelne
            `rad` a `trida`

    Returns:
        (index, podil_znamych) kde podil_znamych je podil biomasy taxonu,
        u kterych se optimum podarilo dohledat; None pri nulove biomase
    """
    celkem = sum(to_float(t.get("biomasa"), 0.0) or 0.0 for t in taxony)
    if celkem <= 0:
        return None, None

    index = 0.0
    znama = 0.0
    for t in taxony:
        biomasa = to_float(t.get("biomasa"), 0.0) or 0.0
        if biomasa <= 0:
            continue
        optimum, uroven = troficke_optimum(
            _rod(t.get("nazev")), t.get("rad"), t.get("trida"))
        index += (biomasa / celkem) * optimum
        if uroven != "vychozi":
            znama += biomasa
    return round(index, 4), round(znama / celkem, 3)


def podil_sinic(taxony):
    """Podil sinic tvoricich vodni kvety na celkove biomase [%].

    Args:
        taxony: seznam dictu s klici `nazev`, `biomasa`, `trida`

    Returns:
        (podil v procentech, podil biomasy bez znameho zarazeni);
        (None, None) pri nulove biomase
    """
    celkem = sum(to_float(t.get("biomasa"), 0.0) or 0.0 for t in taxony)
    if celkem <= 0:
        return None, None
    sinice = 0.0
    nezarazene = 0.0
    for t in taxony:
        biomasa = to_float(t.get("biomasa"), 0.0) or 0.0
        trida = _trida(t)
        if trida is None:
            nezarazene += biomasa
            continue
        if trida != SINICE:
            continue
        if _rod(t.get("nazev")) in PIKOPLANKTON:
            continue
        sinice += biomasa
    return round(sinice / celkem * 100, 3), round(nezarazene / celkem, 3)


def biomasa_celkem(taxony):
    """Celkova objemova biomasa fytoplanktonu [mm3/l]."""
    celkem = sum(to_float(t.get("biomasa"), 0.0) or 0.0 for t in taxony)
    return round(celkem, 4) if celkem > 0 else None


def spocitej_metriky(taxony, chlorofyl=None):
    """Spocita vsechny ctyri metriky CZ-PHYPI.

    Args:
        taxony: seznam dictu s klici `nazev`, `biomasa`, `rad`, `trida`
        chlorofyl: koncentrace chlorofylu-a [ug/l]

    Returns:
        (metriky, poznamky)
    """
    poznamky = []
    index, podil_znamych = troficky_index(taxony)
    if podil_znamych is not None and podil_znamych < 0.5:
        poznamky.append(
            f"trofická optima známa jen pro {podil_znamych * 100:.0f} % "
            f"biomasy — index je nadhodnocen směrem k nule"
        )

    sinice, bez_zarazeni = podil_sinic(taxony)
    if bez_zarazeni:
        poznamky.append(
            f"u {bez_zarazeni * 100:.0f} % biomasy se nepodařilo určit třídu — "
            f"podíl sinic může být podhodnocen"
        )

    metriky = {
        "FPJ01": to_float(chlorofyl),
        "FPJ02": biomasa_celkem(taxony),
        "FPJ03": sinice,
        "FPJ04": index,
    }
    if metriky["FPJ02"] is None:
        poznamky.append(
            "chybí objemová biomasa taxonů — metriky biomasy, podílu sinic "
            "a trofického indexu nelze spočítat (početnost metodika "
            "nepřipouští)"
        )
    if metriky["FPJ01"] is None:
        poznamky.append("chybí koncentrace chlorofylu-a")
    return metriky, poznamky


def vyhodnot(typ, taxony, chlorofyl=None):
    """Spocita CZ-PHYPI pro jeden vzorek.

    Args:
        typ: TypJezera z `jezera_typologie.urci_typ()`
        taxony: seznam dictu s klici `nazev`, `biomasa`, `rad`, `trida`
        chlorofyl: koncentrace chlorofylu-a [ug/l]

    Returns:
        dict s klici metriky, body, eqr, trida a poznamka
    """
    if typ is None:
        return {"eqr": None, "trida": None,
                "poznamka": "Nehodnoceno: neurčen typ vodního útvaru"}

    klic = (typ.vyska, typ.zdrzeni)
    meze = MEZE.get(klic)
    if meze is None:
        return {"eqr": None, "trida": None,
                "poznamka": f"Nehodnoceno: pro typ {typ.kod} nejsou meze"}

    metriky, poznamky = spocitej_metriky(taxony, chlorofyl)
    body = {}
    for kod, hodnota in metriky.items():
        dolni, horni = meze[kod]
        body[kod] = oboduj(hodnota, dolni, horni, METRIKY[kod][1])

    eqr = eqr_z_bodu(body.values(), MIN_PODIL_METRIK)
    chybi = sum(1 for b in body.values() if b is None)
    if eqr is None and chybi:
        poznamky.append(
            f"spočítány jen {len(body) - chybi} ze {len(body)} metrik — "
            f"na hodnocení to nestačí"
        )
    return {
        "metriky": metriky,
        "body": body,
        "eqr": eqr,
        "trida": klasifikuj_jezero(eqr, TRIDY_JEZERA),
        "typ": typ.kod,
        "poznamka": "; ".join(poznamky) or None,
    }
