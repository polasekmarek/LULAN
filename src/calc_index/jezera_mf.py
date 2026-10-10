"""
Makrofyta stojatych vod - multimetricky index CZ-MPHYI.

Metodika:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, kap. 7.

Metriky (Tabulka 6)
-------------------
    MFJ01  druhova pocetnost makrofyt [pocet druhu]
    MFJ02  pokryvnost v produkcni zone [%]

Obe metriky klesaji se zatizenim (vyssi hodnota = lepsi stav).

Na rozdil od fytoplanktonu a ryb jsou meze SPOLECNE pro vsechny typy -
Tabulka 6 uvadi u obou metrik klic "A-B-C-D-E-F-G-H", tedy libovolny typ.

Produkcni zona
--------------
"Tato zóna je pro potřeby hodnocení definována plochou dna mezi kótou
průměrné nadmořské výšky hladiny v období vegetační sezóny (duben-říjen)
a kótou hloubky s dostatečnými světelnými podmínkami pro růst makrofyt,
tj. odpovídajícími průměrné průhlednosti v období vegetační sezóny."

Spodni hranici produkcni zony tedy urcuje prumerna pruhlednost merena
Secchiho deskou. Modul ji nepocita - pokryvnost prichazi ze vstupnich dat
uz vztazena k produkcni zone. Funkce `hloubka_produkcni_zony()` slouzi
k tomu, aby uzivatel vedel, do jake hloubky ma transekty vyhodnotit.

Co se pocita za makrofyt
------------------------
"za vodní makrofyta jsou považovány mechorosty (Bryophyta), parožnatky
(Charophyta) a vyšší cévnaté rostliny, jejichž životní forma patří do
skupiny helofyt, hygrofyt nebo hydrofyt"

Vstupni data
------------
Pokryvnost jednotlivych druhu se cte ze sloupce `data.POKRYVNOST` [%],
druhova pocetnost je pocet ruznych taxonu ve vzorku. Celkova pokryvnost je
podle metodiky SOUCET pokryvnosti jednotlivych druhu ("která je součtem
pokryvností jednotlivých druhů vodních makrofyt"), takze muze presahnout
100 % - druhy se prekryvaji v patrech.
"""

from __future__ import annotations

from .common import to_float
from .jezera_common import (
    KLESA, TRIDY_JEZERA, eqr_z_bodu, klasifikuj_jezero, oboduj,
)

#: Metriky a jejich smer pusobeni.
METRIKY = {
    "MFJ01": ("Druhová početnost makrofyt", KLESA),
    "MFJ02": ("Pokryvnost v produkční zóně [%]", KLESA),
}

#: Hranicni hodnoty (Tabulka 6) - spolecne pro vsechny typy utvaru.
MEZE = {
    "MFJ01": (5, 10),
    "MFJ02": (10, 20),
}


def hloubka_produkcni_zony(pruhlednost):
    """Spodni hranice produkcni zony [m].

    Odpovida prumerne pruhlednosti (Secchi) za vegetacni sezonu.

    Args:
        pruhlednost: prumerna pruhlednost duben-rijen [m]

    Returns:
        hloubka v metrech nebo None
    """
    return to_float(pruhlednost)


def druhova_pocetnost(taxony):
    """Pocet ruznych taxonu makrofyt ve vzorku.

    Args:
        taxony: seznam dictu s klicem `nazev`

    Returns:
        pocet druhu; 0 pri prazdnem seznamu
    """
    return len({
        str(t.get("nazev", "")).strip().lower()
        for t in taxony
        if str(t.get("nazev", "")).strip()
    })


def celkova_pokryvnost(taxony):
    """Soucet pokryvnosti jednotlivych druhu [%].

    Args:
        taxony: seznam dictu s klicem `pokryvnost`

    Returns:
        soucet v procentech nebo None, kdyz zadny druh pokryvnost nema
    """
    hodnoty = [to_float(t.get("pokryvnost")) for t in taxony]
    platne = [h for h in hodnoty if h is not None]
    if not platne:
        return None
    return round(sum(platne), 2)


def spocitej_metriky(taxony):
    """Spocita obe metriky CZ-MPHYI.

    Returns:
        (metriky, poznamky)
    """
    poznamky = []
    pokryvnost = celkova_pokryvnost(taxony)
    if pokryvnost is None and taxony:
        poznamky.append("chybí údaje o pokryvnosti druhů")

    metriky = {
        "MFJ01": float(druhova_pocetnost(taxony)),
        "MFJ02": pokryvnost,
    }
    if metriky["MFJ01"] < 4:
        # kap. 7.2: "Hodnocení druhové početnosti vodní makrovegetace má
        # dobrou vypovídací hodnotu pouze v případě, že ji tvoří více než
        # čtyři druhy vodních makrofyt (Penning a kol. 2008a)."
        poznamky.append(
            f"nalezeny jen {metriky['MFJ01']:.0f} druhy — metodika upozorňuje, "
            f"že pod 4 druhy má metrika početnosti omezenou vypovídací hodnotu"
        )
    return metriky, poznamky


def vyhodnot(taxony, typ=None):
    """Spocita CZ-MPHYI pro jeden vzorek.

    Args:
        taxony: seznam dictu s klici `nazev` a `pokryvnost`
        typ: TypJezera; meze jsou pro vsechny typy stejne, typ se pouze
            zapise do vysledku

    Returns:
        dict s klici metriky, body, eqr, trida a poznamka
    """
    metriky, poznamky = spocitej_metriky(taxony)
    body = {
        kod: oboduj(hodnota, *MEZE[kod], METRIKY[kod][1])
        for kod, hodnota in metriky.items()
    }
    eqr = eqr_z_bodu(body.values())
    return {
        "metriky": metriky,
        "body": body,
        "eqr": eqr,
        "trida": klasifikuj_jezero(eqr, TRIDY_JEZERA),
        "typ": typ.kod if typ is not None else None,
        "poznamka": "; ".join(poznamky) or None,
    }
