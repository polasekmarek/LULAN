"""
Typologie utvaru stojatych vod (kategorie jezero).

Podle metodiky Borovec a kol. (2014), Tabulka 1: typ je urcen osmimistnym
kodem ve formatu A-B-C-D-E-F-G-H, kde jednotlive pozice znamenaji:

    A  nadmorska vyska hladiny [m n. m. Bpv]
    B  zemepisna sirka        (v CR vzdy 1)
    C  zemepisna delka        (v CR vzdy 1)
    D  maximalni hloubka [m]
    E  geologie
    F  velikost [km2]         (v CR vzdy 1)
    G  prumerna hloubka [m]
    H  doba zdrzeni vody [rok]

V metodice se kod zapisuje jako `2BC21F22` - pozice B, C a F maji v CR
jedinou moznou hodnotu, takze se misto cislice pise pismeno pozice.

Na hranicni hodnoty metrik ma vliv **jen A, G a H** (str. 7):

    "typologie VÚ je založená zejména na údajích o nadmořské výšce,
     průměrné hloubce a době zdržení vody. Ostatní charakteristiky jsou
     pouze popisného charakteru, bez vlivu na nastavení hraničních hodnot
     jednotlivých metrik."

Proto se hranice metrik vyhledavaji podle zkraceneho klice (A, G, H) -
funkce `klic_metrik()`. Fyzikalne-chemicke slozky a fytoplankton pouzivaji
(A, H), ryby (A, G) a makrofyta zadny - viz jednotlive moduly.

Pouziti:
    from calc_index.jezera_typologie import urci_typ
    typ, duvod = urci_typ(mnm=354.1, zmax=28.5, plocha=3.642,
                          zprum=9.3, trt=0.14, geologie=2)
    # typ.kod == "2BC21F22"
"""

from __future__ import annotations

from dataclasses import dataclass

from .common import to_float


@dataclass(frozen=True)
class TypJezera:
    """Typ utvaru stojatych vod."""

    vyska: int          # A
    hloubka_max: int    # D
    geologie: int       # E
    hloubka_prum: int   # G
    zdrzeni: int        # H

    @property
    def kod(self):
        """Osmimistny kod ve tvaru, ktery pouziva metodika."""
        return (f"{self.vyska}BC{self.hloubka_max}{self.geologie}"
                f"F{self.hloubka_prum}{self.zdrzeni}")

    @property
    def klic_metrik(self):
        """Klic pro vyhledani hranicnich hodnot: (A, G, H)."""
        return (self.vyska, self.hloubka_prum, self.zdrzeni)

    def __str__(self):
        return self.kod


#: Pozice A - nadmorska vyska hladiny [m n. m.].
def _vyska(h):
    if h < 200:
        return 1
    if h < 700:
        return 2
    return 3


#: Pozice D - maximalni hloubka [m]. Metodika uvadi zmax < 13 a zmax > 13;
#: presna rovnost neni osetrena, radime ji k melčim (< 13 je kategorie 1).
def _hloubka_max(z):
    return 1 if z < 13 else 2


#: Pozice G - prumerna hloubka [m]. Tataz nejednoznacnost jako u D:
#: metodika ma zprum < 5 a zprum > 5. Podle Prilohy 1 (napr. Hubenov
#: zprum 5,9 -> kategorie 2, Olesna 4,7 -> kategorie 1) plati, ze hranice
#: patri k hlubsi kategorii az od 5 vys.
def _hloubka_prum(z):
    return 1 if z < 5 else 2


#: Pozice H - doba zdrzeni vody [rok].
def _zdrzeni(t):
    if t <= 0.1:
        return 1
    if t < 0.5:
        return 2
    return 3


def urci_typ(mnm=None, zmax=None, zprum=None, trt=None, geologie=None,
             plocha=None):
    """Urci typ utvaru stojatych vod.

    Args:
        mnm: nadmorska vyska hladiny zasobniho prostoru [m n. m. Bpv]
        zmax: maximalni hloubka [m]
        zprum: prumerna hloubka [m]
        trt: doba zdrzeni vody [rok]
        geologie: 1 = krystalinikum a vulkanity,
                  2 = piskovce, jilovce, kvarter; None = 1
        plocha: plocha hladiny [km2], jen pro kontrolu (metodika hodnoti
                utvary nad 0,5 km2)

    Returns:
        (TypJezera, duvod) - pri chybejicim udaji (None, text duvodu)
    """
    hodnoty = {}
    for nazev, hodnota in (("nadmořskou výšku", mnm),
                           ("maximální hloubku", zmax),
                           ("průměrnou hloubku", zprum),
                           ("dobu zdržení", trt)):
        cislo = to_float(hodnota)
        if cislo is None:
            return None, f"Nehodnoceno: chybí {nazev}"
        hodnoty[nazev] = cislo

    geo = to_float(geologie)
    typ = TypJezera(
        vyska=_vyska(hodnoty["nadmořskou výšku"]),
        hloubka_max=_hloubka_max(hodnoty["maximální hloubku"]),
        geologie=int(geo) if geo in (1, 2) else 1,
        hloubka_prum=_hloubka_prum(hodnoty["průměrnou hloubku"]),
        zdrzeni=_zdrzeni(hodnoty["dobu zdržení"]),
    )

    plocha_km2 = to_float(plocha)
    if plocha_km2 is not None and plocha_km2 <= 0.5:
        return typ, (f"Upozornění: plocha {plocha_km2:.3f} km² je pod hranicí "
                     f"0,5 km², kterou metodika pro vymezení útvarů používá")
    return typ, None


def typ_z_kodu(kod):
    """Rozlozi kod z metodiky (napr. '2BC21F22') zpet na TypJezera.

    Slouzi ke kontrole proti Priloze 1 metodiky.

    Returns:
        TypJezera nebo None, kdyz kod neodpovida ocekavanemu tvaru
    """
    if not kod or len(kod) != 8:
        return None
    try:
        return TypJezera(
            vyska=int(kod[0]),
            hloubka_max=int(kod[3]),
            geologie=int(kod[4]),
            hloubka_prum=int(kod[6]),
            zdrzeni=int(kod[7]),
        )
    except (ValueError, IndexError):
        return None
