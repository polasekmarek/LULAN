"""
Ryby stojatych vod - multimetricky index CZ-FBI.

Metodika:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, kap. 8.
    Hranice trid podle Prilohy 3 (po interkalibraci C/BLI).

Vstupni data
------------
Ulovky z mnohookych tenatnich siti podle CSN EN 14 757. Kazdy zaznam nese:

    SIT       BT = bentická tenatní síť, PT = pelagická tenatní síť
    ZONA      H = hrázová část, P = přítoková část
    val       pocetnost [ind / 1000 m2 site a noc]
    BIOMASA   biomasa [kg / 1000 m2 site a noc]
    juv       priznak tohorocni (0+) ryby

BPT v tabulkach metodiky znamena "prumerny udaj z obou typu tenat". Modul
proto u BPT metrik pocita prumer hodnoty za BT a za PT (kdyz je k dispozici
jen jeden typ, pouzije se ten). Vyjimkou je pritomnost 0+ ryb, kde ma prumer
poctu druhu maly smysl - tam se bere SJEDNOCENI druhu nalezenych v obou
typech siti.

Dve zvlastni pravidla
---------------------
1. **Rybniky se podle ryb nehodnoti.** Kap. 3: "Metodika pro hodnocení
   ekologického stavu rybníků pomocí rybí složky nebyla vypracována",
   protoze "na rybnících rybářské hospodaření zcela rozhoduje o složení
   rybího společenstva". Viz `vyhodnot(rybnik=True)`.

2. **Okounovita obsadka vyrazuje metriku 0+ ryb.** Kap. 8.2: "pokud
   zastoupení okouna přesáhne 20 % biomasy ryb ve všech tenatních sítích,
   metrika Přítomnost 0+ ryb není použita." Duvodem je cyklovani populace
   okouna, ktere doasne potlaci vsechny 0+ ryby vcetne vlastniho potomstva -
   je to prirozeny jev, ne porucha reprodukce.

Vyber metrik podle typu
-----------------------
Rozhoduji jen dve pozice typoveho kodu: nadmorska vyska (A) a prumerna
hloubka (G). Kap. 8.2: "Faktory pro kategorizaci VÚ použité v předkládané
metodice jsou nadmořská výška a průměrná hloubka vody."

    G = 1  melke utvary (zprum < 5 m)  -> 5 metrik, prevzato z C/BLI
    G = 2  hluboke utvary               -> 8 metrik, vlastni system
"""

from __future__ import annotations

from .common import to_float
from .jezera_common import (
    KLESA, MIN_PODIL_METRIK, ROSTE, TRIDY_RYBY, eqr_z_bodu,
    klasifikuj_jezero, oboduj,
)

#: Nazvy metrik, typ site a smer pusobeni.
METRIKY = {
    "RYJ01": ("Biomasa ryb [kg/1000 m² a noc]", "BT", ROSTE),
    "RYJ02": ("Biomasa cejna velkého [%]", "BT", ROSTE),
    "RYJ03": ("Biomasa okouna říčního [%]", "BT", KLESA),
    "RYJ04": ("Početnost ježdíka obecného [%]", "BT", ROSTE),
    "RYJ05": ("Přítomnost 0+ ryb šesti běžných druhů", "BPT", KLESA),
    "RYJ06": ("Biomasa ryb u hráze 0–5 m [kg/1000 m² a noc]", "PT", ROSTE),
    "RYJ07": ("Biomasa ryb na přítoku 0–5 m [kg/1000 m² a noc]", "PT", ROSTE),
    "RYJ08": ("Početnost ryb [ind/1000 m² a noc]", "BT", ROSTE),
    "RYJ09": ("Biomasa okouna říčního [%]", "PT", KLESA),
    "RYJ10": ("Biomasa perlína ostrobřichého [%]", "BPT", KLESA),
    "RYJ11": ("Biomasa lososovitých ryb [%]", "BPT", KLESA),
}

#: Metriky melkych utvaru (G = 1) - Tabulka 8, radky *-1-*.
MELKE = ("RYJ01", "RYJ02", "RYJ03", "RYJ04", "RYJ05")

#: Metriky hlubokych utvaru (G = 2) - Tabulka 8, radky *-2-*.
HLUBOKE = ("RYJ06", "RYJ07", "RYJ08", "RYJ02", "RYJ04",
           "RYJ09", "RYJ10", "RYJ11", "RYJ05")

#: Hranicni hodnoty (Tabulka 8), klic (A, G) -> {metrika: (dolni, horni)}.
MEZE = {
    (1, 1): {"RYJ01": (60, 116), "RYJ02": (20, 39.5), "RYJ03": (5, 10.3),
             "RYJ04": (10, 20), "RYJ05": (2, 3)},
    (2, 1): {"RYJ01": (30, 60), "RYJ02": (20, 39.5), "RYJ03": (5, 10.3),
             "RYJ04": (10, 20), "RYJ05": (2, 3)},
    (3, 1): {"RYJ01": (30, 60), "RYJ02": (20, 39.5), "RYJ03": (5, 10.3),
             "RYJ04": (10, 20), "RYJ05": (2, 3)},
    (1, 2): {"RYJ06": (17, 35), "RYJ07": (35, 70), "RYJ08": (300, 600),
             "RYJ02": (5, 10), "RYJ04": (10, 20), "RYJ09": (10, 20),
             "RYJ10": (1, 5), "RYJ11": (1, 2), "RYJ05": (2, 3)},
    (2, 2): {"RYJ06": (17, 35), "RYJ07": (35, 70), "RYJ08": (300, 600),
             "RYJ02": (5, 10), "RYJ04": (10, 20), "RYJ09": (10, 20),
             "RYJ10": (1, 5), "RYJ11": (1, 2), "RYJ05": (2, 3)},
    # Nad 700 m n. m. jsou lososovite prirozenou soucasti spolecenstva,
    # proto ma metrika RYJ11 prisnejsi meze (> 5 | 2-5 | < 2).
    (3, 2): {"RYJ06": (17, 35), "RYJ07": (35, 70), "RYJ08": (300, 600),
             "RYJ02": (5, 10), "RYJ04": (10, 20), "RYJ09": (10, 20),
             "RYJ10": (1, 5), "RYJ11": (2, 5), "RYJ05": (2, 3)},
}

#: Indikatorove druhy. Klice jsou vedecke nazvy, hodnoty seznam prijimanych
#: zapisu (aby prosly i ceske nazvy z importu).
CEJN = "Abramis brama"
OKOUN = "Perca fluviatilis"
JEZDIK = "Gymnocephalus cernua"
PERLIN = "Scardinius erythrophthalmus"

#: Sest beznych druhu pro metriku pritomnosti 0+ ryb (kap. 8.2).
DRUHY_0PLUS = (
    "Abramis brama",            # cejn velky
    "Alburnus alburnus",        # ouklej obecna
    "Rutilus rutilus",          # plotice obecna
    "Sander lucioperca",        # candat obecny
    "Gymnocephalus cernua",     # jezdik obecny
    "Perca fluviatilis",        # okoun ricni
)

#: Rody celedi Salmonidae, ktere se v ceskych nadrzich vyskytuji.
SALMONIDAE = ("Salmo", "Salvelinus", "Oncorhynchus", "Thymallus", "Coregonus")

#: Podil biomasy okouna, nad kterym se metrika 0+ ryb nepouzije [%].
MEZ_OKOUNOVITE_OBSADKY = 20.0


def _je(nazev, druh):
    """Porovna nazev taxonu s vedeckym jmenem druhu (bez ohledu na velikost)."""
    return str(nazev or "").strip().lower().startswith(druh.lower())


def _je_lososovita(nazev):
    rod = str(nazev or "").strip().split()
    return bool(rod) and rod[0] in SALMONIDAE


def _soucet(ulovky, klic, sit=None, zona=None, filtr=None):
    """Soucet biomasy nebo pocetnosti pres vybrane ulovky."""
    celkem = 0.0
    for u in ulovky:
        if sit is not None and u.get("sit") != sit:
            continue
        if zona is not None and u.get("zona") != zona:
            continue
        if filtr is not None and not filtr(u.get("nazev")):
            continue
        hodnota = to_float(u.get(klic))
        if hodnota is not None:
            celkem += hodnota
    return celkem


def _podil(ulovky, klic, sit, filtr):
    """Podil vybranych taxonu na celku v dane siti [%]."""
    celkem = _soucet(ulovky, klic, sit=sit)
    if celkem <= 0:
        return None
    return round(_soucet(ulovky, klic, sit=sit, filtr=filtr) / celkem * 100, 3)


def _bpt(ulovky, klic, filtr):
    """Prumer podilu za BT a PT - v tabulkach oznaceno BPT."""
    hodnoty = [
        p for p in (_podil(ulovky, klic, "BT", filtr),
                    _podil(ulovky, klic, "PT", filtr))
        if p is not None
    ]
    if not hodnoty:
        return None
    return round(sum(hodnoty) / len(hodnoty), 3)


def pocet_druhu_0plus(ulovky):
    """Pocet z sesti beznych druhu, u kterych byly nalezeny 0+ ryby.

    Sjednoceni pres oba typy siti - pritomnost je bud, anebo neni, takze
    prumerovani poctu druhu by nedavalo smysl.
    """
    nalezene = set()
    for u in ulovky:
        if not u.get("juv"):
            continue
        for druh in DRUHY_0PLUS:
            if _je(u.get("nazev"), druh):
                nalezene.add(druh)
    return len(nalezene)


def podil_okouna_vsechny_site(ulovky):
    """Podil biomasy okouna ve vsech tenatnich sitich [%]."""
    celkem = _soucet(ulovky, "biomasa")
    if celkem <= 0:
        return None
    okoun = _soucet(ulovky, "biomasa",
                    filtr=lambda n: _je(n, OKOUN))
    return round(okoun / celkem * 100, 3)


def spocitej_metriky(ulovky):
    """Spocita vsechny metriky CZ-FBI, ktere jdou z dat odvodit.

    Args:
        ulovky: seznam dictu s klici `nazev`, `sit`, `zona`, `val`,
            `biomasa`, `juv`

    Returns:
        dict {kod_metriky: hodnota}
    """
    return {
        "RYJ01": _soucet(ulovky, "biomasa", sit="BT") or None,
        "RYJ02": _podil(ulovky, "biomasa", "BT", lambda n: _je(n, CEJN)),
        "RYJ03": _podil(ulovky, "biomasa", "BT", lambda n: _je(n, OKOUN)),
        "RYJ04": _podil(ulovky, "val", "BT", lambda n: _je(n, JEZDIK)),
        "RYJ05": float(pocet_druhu_0plus(ulovky)),
        "RYJ06": _soucet(ulovky, "biomasa", sit="PT", zona="H") or None,
        "RYJ07": _soucet(ulovky, "biomasa", sit="PT", zona="P") or None,
        "RYJ08": _soucet(ulovky, "val", sit="BT") or None,
        "RYJ09": _podil(ulovky, "biomasa", "PT", lambda n: _je(n, OKOUN)),
        "RYJ10": _bpt(ulovky, "biomasa", lambda n: _je(n, PERLIN)),
        "RYJ11": _bpt(ulovky, "biomasa", _je_lososovita),
    }


def vyhodnot(typ, ulovky, rybnik=False):
    """Spocita CZ-FBI pro jeden vzorek.

    Args:
        typ: TypJezera z `jezera_typologie.urci_typ()`
        ulovky: seznam dictu (viz `spocitej_metriky`)
        rybnik: True pro utvary typu rybnik - podle ryb se nehodnoti

    Returns:
        dict s klici metriky, body, eqr, trida a poznamka
    """
    if rybnik:
        return {"eqr": None, "trida": None, "poznamka":
                "Nehodnoceno: na rybnících rozhoduje o složení rybího "
                "společenstva rybářské hospodaření, metodika je podle ryb "
                "nehodnotí"}
    if typ is None:
        return {"eqr": None, "trida": None,
                "poznamka": "Nehodnoceno: neurčen typ vodního útvaru"}

    klic = (typ.vyska, typ.hloubka_prum)
    meze = MEZE.get(klic)
    if meze is None:
        return {"eqr": None, "trida": None,
                "poznamka": f"Nehodnoceno: pro typ {typ.kod} nejsou meze"}

    vsechny = spocitej_metriky(ulovky)
    pouzite = MELKE if typ.hloubka_prum == 1 else HLUBOKE

    poznamky = []
    okoun = podil_okouna_vsechny_site(ulovky)
    if okoun is not None and okoun > MEZ_OKOUNOVITE_OBSADKY:
        pouzite = tuple(k for k in pouzite if k != "RYJ05")
        poznamky.append(
            f"okounovitá obsádka ({okoun:.1f} % biomasy) — metrika "
            f"přítomnosti 0+ ryb se podle metodiky nepoužívá"
        )

    metriky, body = {}, {}
    for kod in pouzite:
        metriky[kod] = vsechny.get(kod)
        dolni, horni = meze[kod]
        body[kod] = oboduj(metriky[kod], dolni, horni, METRIKY[kod][2])

    chybi = [kod for kod in pouzite if body[kod] is None]
    if chybi:
        poznamky.append(
            "chybí data pro metriky: " + ", ".join(sorted(chybi)))

    eqr = eqr_z_bodu(body.values(), MIN_PODIL_METRIK)
    if eqr is None and body:
        poznamky.append(
            f"spočítáno jen {len(pouzite) - len(chybi)} z {len(pouzite)} "
            f"metrik — na hodnocení to nestačí"
        )
    return {
        "metriky": metriky,
        "body": body,
        "eqr": eqr,
        "trida": klasifikuj_jezero(eqr, TRIDY_RYBY),
        "typ": typ.kod,
        "poznamka": "; ".join(poznamky) or None,
    }
