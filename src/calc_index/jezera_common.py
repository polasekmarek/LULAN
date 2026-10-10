"""
Spolecny zaklad pro hodnoceni stojatych vod (kategorie jezero).

Vsechny tri biologicke slozky - fytoplankton (CZ-PHYPI), makrofyta
(CZ-MPHYI) i ryby (CZ-FBI) - pouzivaji tentyz postup (Borovec a kol. 2014,
kap. 6.3, 7.3 a 8.3):

  1. kazda metrika se oboduje 5 (nejlepsi), 3 (stredni) nebo 1 (nejhorsi)
  2. EQR = (Sum - Min) / (Max - Min), kde
         Sum = soucet bodu vsech metrik
         Min = pocet metrik        (vsechny metriky za 1 bod)
         Max = 5x pocet metrik     (vsechny metriky za 5 bodu)
  3. EQR se prevede na tridu podle kvantilu

Prevod na EQR je tedy jen linearni prepocet prumerneho bodoveho hodnoceni
z rozsahu <1, 5> na <0, 1>.

Tridy jsou pro fytoplankton a makrofyta ctyrstupnove (Tabulka 5 a 7),
pro ryby petistupnove podle Prilohy 3 - viz TRIDY_JEZERA a TRIDY_RYBY.
"""

from __future__ import annotations

from .common import to_float

#: Smer pusobeni metriky.
ROSTE = "roste"    # vyssi hodnota = horsi stav (napr. biomasa sinic)
KLESA = "klesa"    # vyssi hodnota = lepsi stav (napr. pruhlednost)

#: Bodove hodnoceni metrik.
NEJLEPSI, STREDNI, NEJHORSI = 5, 3, 1

#: Tridy pro fytoplankton a makrofyta (Tabulka 5 a Tabulka 7).
#: Metodika deli EQR na ctyri 25% kvantily; nejlepsi trida spojuje
#: "dobry a lepsi potencial" dohromady.
TRIDY_JEZERA = (
    (0.75, "dobrý a lepší potenciál"),
    (0.50, "střední potenciál"),
    (0.25, "poškozený potenciál"),
    (0.00, "zničený potenciál"),
)

#: Tridy pro ryby (Priloha 3). Puvodni Tabulka 9 mela tytez kvantily jako
#: ostatni slozky, ale po porovnani v ramci Centralni a pobaltske
#: geograficke interkalibracni skupiny byly hranice upraveny a rozdeleny
#: na pet stupnu. Metodika vyslovne rika, ze pro CZ-FBI plati Priloha 3.
TRIDY_RYBY = (
    (0.88, "lepší potenciál"),
    (0.63, "dobrý potenciál"),
    (0.36, "střední potenciál"),
    (0.16, "poškozený potenciál"),
    (0.00, "zničený potenciál"),
)


def oboduj(hodnota, dolni, horni, smer=ROSTE):
    """Oboduje jednu metriku podle dvou hranicnich hodnot.

    Tabulky metodiky uvadeji meze ve tvaru "< 30 | 30-40 | > 40". Prostredni
    pasmo je uzavrene, takze hodnota rovna hranici spada do stredniho pasma.

    Args:
        hodnota: namerena hodnota metriky
        dolni: nizsi z obou hranicnich hodnot
        horni: vyssi z obou hranicnich hodnot
        smer: ROSTE = vyssi hodnota znamena horsi stav,
              KLESA = vyssi hodnota znamena lepsi stav

    Returns:
        5, 3 nebo 1; None, kdyz hodnota neni cislo
    """
    x = to_float(hodnota)
    if x is None:
        return None
    if smer == ROSTE:
        if x < dolni:
            return NEJLEPSI
        return STREDNI if x <= horni else NEJHORSI
    if x > horni:
        return NEJLEPSI
    return STREDNI if x >= dolni else NEJHORSI


#: Nejmensi podil metrik, ktere musi jit spocitat, aby melo smysl EQR
#: vubec sestavovat.
#:
#: Bez teto pojistky by vzorek, u ktereho vetsina metrik chybi, dostal
#: EQR poskladane z hrstky zbylych - a protoze chybejici hodnota se
#: neboduje vubec, vysledek by pusobil jako plnohodnotny. Nejhorsi je
#: kombinace "chybi skoro vsechno" + "to zbyle vyslo spatne": vysledkem
#: je EQR 0,00 a trida "zniceny potencial", coz je tvrzeni o stavu
#: utvaru, pro ktere data nejsou.
MIN_PODIL_METRIK = 0.5


def eqr_z_bodu(body, min_podil=None):
    """Prepocte bodove hodnoceni metrik na EQR.

    Args:
        body: seznam bodovych hodnoceni (5, 3, 1); None se ignoruji
        min_podil: nejmensi podil spocitatelnych metrik; None = bez kontroly

    Returns:
        EQR v rozsahu <0, 1>, nebo None, kdyz nelze spocitat dost metrik
    """
    body = list(body)
    platne = [b for b in body if b is not None]
    if not platne:
        return None
    if min_podil is not None and body and len(platne) / len(body) < min_podil:
        return None
    soucet = sum(platne)
    minimum = NEJHORSI * len(platne)
    maximum = NEJLEPSI * len(platne)
    return round((soucet - minimum) / (maximum - minimum), 3)


def klasifikuj_jezero(eqr, tridy=TRIDY_JEZERA):
    """Zaradi EQR do tridy ekologickeho potencialu.

    Args:
        eqr: hodnota EQR
        tridy: TRIDY_JEZERA nebo TRIDY_RYBY

    Returns:
        nazev tridy nebo None
    """
    hodnota = to_float(eqr)
    if hodnota is None:
        return None
    for mez, nazev in tridy:
        if hodnota >= mez:
            return nazev
    return tridy[-1][1]


def prumer(hodnoty):
    """Prumer platnych cisel; None, kdyz zadne nejsou.

    Metodika u vetsiny ukazatelu pracuje s prumerem za vegetacni sezonu
    (duben-rijen), doporucena je 3leta datova sada se 7 udaji rocne.
    """
    cisla = [c for c in (to_float(h) for h in hodnoty) if c is not None]
    if not cisla:
        return None
    return sum(cisla) / len(cisla)
