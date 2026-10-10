"""
Vseobecne fyzikalne-chemicke slozky stojatych vod.

Metodika:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, kap. 4,
    Tabulka 3.

Na rozdil od biologickych slozek se tady NEPOCITA EQR (kap. 4):

    "Nejsou pro něj vyžadovány specifické postupy nastavení poměru
     ekologické kvality (EQR) jako v případě biologických složek, ale pro
     celkové hodnocení ekologického potenciálu vodního útvaru se navrhuje
     hodnocení fyzikálně-chemických složek jen pro první dvě třídy
     hodnocení."

Vysledkem je tedy jen zarazeni do tri urovni:

    MAX     dosahuje maximalniho potencialu (lepsi nez mez M/D)
    DOBRY   dosahuje dobreho potencialu     (mezi M/D a D/S)
    HORSI   nedosahuje dobreho potencialu   (za mezi D/S)

Hodnocene ukazatele (kap. 4.1)
------------------------------
    pruhlednost      prumer za vegetacni sezonu [m]        - klesa se zatizenim
    teplota          prumer a maximum [°C]                 - roste
    nasyceni O2      minimum a maximum [%]                 - oboustranne
    pH               minimum a maximum                     - oboustranne
    Pcelk            prumer [mg/l]                         - roste

Solnost (vodivost) se podle kap. 4.1.4 nehodnoti vubec: "Vzhledem k vysoké
variabilitě solnosti ... není tento ukazatel posuzován ani nejsou
nastavovány limitní hodnoty."

Skladani vysledku (kap. 4.2)
----------------------------
"V případě, že daný ukazatel je hodnocen podle dvou charakteristických
hodnot, provede se dvojí posouzení a výsledný stav pro daný ukazatel určí
méně příznivé hodnocení. Podobný postup je aplikován i v případě, že složka
obsahuje více ukazatelů ... V takovém případě výsledné hodnocení stavu
složky určuje nejhůře hodnocený ukazatel."

Rozhoduje tedy vzdy nejhorsi dilci vysledek.
"""

from __future__ import annotations

from .common import to_float

#: Urovne hodnoceni, od nejlepsi.
MAX, DOBRY, HORSI = "maximální potenciál", "dobrý potenciál", "horší než dobrý"
_PORADI = {MAX: 0, DOBRY: 1, HORSI: 2}

#: Typove specificke hodnoty (Tabulka 3), klic (A, H) - nadmorska vyska
#: a doba zdrzeni. Ostatni pozice typoveho kodu se neuplatnuji.
#:
#: Kazdy ukazatel ma dvojici (mez_MD, mez_DS); u oboustranne hodnocenych
#: ukazatelu je to dvojice dvojic (dolni, horni).
MEZE = {
    (1, 1): {"pruhlednost": (2.0, 1.8), "teplota": ((20, 27), (21, 28)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.5, 10.0), (5.0, 10.0)),
             "pcelk": (0.040, 0.060)},
    (1, 2): {"pruhlednost": (2.0, 1.8), "teplota": ((20, 27), (21, 28)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.5, 10.0), (5.0, 10.0)),
             "pcelk": (0.030, 0.040)},
    (1, 3): {"pruhlednost": (2.0, 1.8), "teplota": ((20, 27), (21, 28)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.5, 10.0), (5.0, 10.0)),
             "pcelk": (0.020, 0.030)},
    (2, 1): {"pruhlednost": (3.0, 2.5), "teplota": ((19, 25), (20, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.0, 9.5), (5.0, 10.0)),
             "pcelk": (0.030, 0.040)},
    (2, 2): {"pruhlednost": (3.0, 2.5), "teplota": ((19, 25), (20, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.0, 9.5), (5.0, 10.0)),
             "pcelk": (0.020, 0.030)},
    # Tabulka 3 ma u typu 2-*-3 prumernou teplotu D/S 19 (ne 20 jako
    # u ostatnich typu teze vyskove kategorie) - opsano doslova.
    (2, 3): {"pruhlednost": (3.0, 2.5), "teplota": ((19, 25), (19, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((6.0, 9.5), (5.0, 10.0)),
             "pcelk": (0.015, 0.020)},
    (3, 1): {"pruhlednost": (3.5, 3.0), "teplota": ((17, 25), (18, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((5.5, 8.5), (5.0, 9.0)),
             "pcelk": (0.015, 0.025)},
    (3, 2): {"pruhlednost": (3.5, 3.0), "teplota": ((17, 25), (18, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((5.5, 8.5), (5.0, 9.0)),
             "pcelk": (0.012, 0.020)},
    (3, 3): {"pruhlednost": (3.5, 3.0), "teplota": ((17, 25), (18, 26)),
             "kyslik": ((65, 150), (50, 200)), "ph": ((5.5, 8.5), (5.0, 9.0)),
             "pcelk": (0.010, 0.015)},
}

POPISY = {
    "pruhlednost": "Průhlednost [m]",
    "teplota": "Teplota vody [°C]",
    "kyslik": "Nasycení kyslíkem [%]",
    "ph": "pH",
    "pcelk": "Celkový fosfor [mg/l]",
}


def _horsi(a, b):
    """Z dvojice hodnoceni vrati to mene prizive; None se ignoruje."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _PORADI[a] >= _PORADI[b] else b


def _pod_mez(hodnota, mez_md, mez_ds):
    """Ukazatel, ktery se zhorsuje smerem DOLU (pruhlednost)."""
    x = to_float(hodnota)
    if x is None:
        return None
    if x >= mez_md:
        return MAX
    return DOBRY if x >= mez_ds else HORSI


def _nad_mez(hodnota, mez_md, mez_ds):
    """Ukazatel, ktery se zhorsuje smerem NAHORU (teplota, fosfor)."""
    x = to_float(hodnota)
    if x is None:
        return None
    if x <= mez_md:
        return MAX
    return DOBRY if x <= mez_ds else HORSI


def _v_rozmezi(hodnota, md, ds):
    """Ukazatel hodnoceny oboustranne (kyslik, pH).

    Args:
        md: (dolni, horni) mez maximalniho potencialu
        ds: (dolni, horni) mez dobreho potencialu
    """
    x = to_float(hodnota)
    if x is None:
        return None
    if md[0] <= x <= md[1]:
        return MAX
    return DOBRY if ds[0] <= x <= ds[1] else HORSI


def vyhodnot(typ, pruhlednost=None, teplota_prumer=None, teplota_max=None,
             kyslik_min=None, kyslik_max=None, ph_min=None, ph_max=None,
             pcelk=None, hloubka_profilu=None):
    """Vyhodnoti vseobecne fyzikalne-chemicke slozky.

    Args:
        typ: TypJezera z `jezera_typologie.urci_typ()`
        pruhlednost: prumer za vegetacni sezonu [m]
        teplota_prumer, teplota_max: prumerna a maximalni teplota [°C]
        kyslik_min, kyslik_max: minimalni a maximalni nasyceni [%]
        ph_min, ph_max: minimalni a maximalni pH
        pcelk: prumerna koncentrace celkoveho fosforu [mg/l]
        hloubka_profilu: hloubka vodniho sloupce v reprezentativnim profilu
            [m]; kdyz pruhlednost dosahuje az na dno, hodnoti se ukazatel
            jako lepsi nez M/D (kap. 4.2)

    Returns:
        dict s klici ukazatele (dilci hodnoceni), vysledek a poznamka
    """
    if typ is None:
        return {"vysledek": None,
                "poznamka": "Nehodnoceno: neurčen typ vodního útvaru"}

    meze = MEZE.get((typ.vyska, typ.zdrzeni))
    if meze is None:
        return {"vysledek": None,
                "poznamka": f"Nehodnoceno: pro typ {typ.kod} nejsou meze"}

    poznamky = []
    ukazatele = {}

    # Pruhlednost "az na dno" se podle kap. 4.2 hodnoti jako lepsi nez M/D.
    dno = to_float(hloubka_profilu)
    videt = to_float(pruhlednost)
    if dno is not None and videt is not None and videt >= dno:
        ukazatele["pruhlednost"] = MAX
        poznamky.append("průhlednost až na dno — hodnoceno jako lepší než M/D")
    else:
        ukazatele["pruhlednost"] = _pod_mez(pruhlednost, *meze["pruhlednost"])

    md, ds = meze["teplota"]
    ukazatele["teplota"] = _horsi(
        _nad_mez(teplota_prumer, md[0], ds[0]),
        _nad_mez(teplota_max, md[1], ds[1]),
    )

    md, ds = meze["kyslik"]
    ukazatele["kyslik"] = _horsi(
        _v_rozmezi(kyslik_min, md, ds), _v_rozmezi(kyslik_max, md, ds))

    md, ds = meze["ph"]
    ukazatele["ph"] = _horsi(
        _v_rozmezi(ph_min, md, ds), _v_rozmezi(ph_max, md, ds))

    ukazatele["pcelk"] = _nad_mez(pcelk, *meze["pcelk"])

    chybi = [POPISY[k] for k, v in ukazatele.items() if v is None]
    if chybi:
        poznamky.append("chybí data: " + ", ".join(chybi))

    vysledek = None
    for hodnoceni in ukazatele.values():
        vysledek = _horsi(vysledek, hodnoceni)

    return {
        "ukazatele": ukazatele,
        "vysledek": vysledek,
        "typ": typ.kod,
        "poznamka": "; ".join(poznamky) or None,
    }
