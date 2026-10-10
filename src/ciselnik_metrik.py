"""
Prekladovy slovnik zkratek metrik a multimetrik.

Ve vysledcich hodnoceni jsou metriky vedene pod kody jako `MB01` nebo
`RY_TD`. Kdo metodiku nezna nazpamet, z takoveho prehledu nic nevycte,
proto se vedle kodu ukazuje cesky nazev z ciselniku
`dtb/hodnoceni_zkratky.csv`.

Struktura ciselniku
-------------------
    zkratka   kod metriky tak, jak je ulozeny ve sloupci METRIC
    popis     cesky nazev

Proc samostatny soubor a ne spolecny s traity
---------------------------------------------
Zvazovaly se tri cesty:

1. Zapsat popisy primo do kodu. Odpada soubor navic, ale kazda zmena
   metodiky by znamenala zasah do zdrojaku a nove sestaveni aplikace.
   Zadavatel si texty upravuje sam, takze tudy ne.

2. Slouzit vse do jednoho ciselniku s traity. Jenze traity popisuji
   vlastnosti taxonu a metriky vysledky hodnoceni - jsou to dva ruzne
   slovniky, ktere se udrzuji zvlast a maji i jinou strukturu (traity
   rozlisuji slozku, metriky ji nesou uz v samotnem kodu). Slucovani by
   si vyzadalo rozlisovaci sloupec a hrozila by srazka zkratek.

3. Samostatny soubor, spolecny kod na cteni. Zvoleno: kazdy ciselnik
   zustava tim, cim je, a o kodovani se stara jeden sdileny modul
   (`csv_ciselnik`).

Zkratka zustava videt i po prelozeni - uzivatel podle ni hleda metriku
v metodice a v exportech.
"""

from __future__ import annotations

import os
import re

import csv_ciselnik
from cesty import v_korenu

#: Umisteni ciselniku vuci korenu projektu.
SOUBOR = os.path.join("dtb", "hodnoceni_zkratky.csv")

#: Nazvy sloupcu v ciselniku. Prvni nalezeny se pouzije - kdyby soubor
#: prisel s hlavickou v anglictine nebo velkymi pismeny, cist pujde dal.
SLOUPCE_ZKRATKA = ("zkratka", "ZKRATKA", "kod", "KOD", "ID", "METRIC")
SLOUPCE_POPIS = ("popis", "POPIS", "nazev", "NAZEV", "CS")

#: Souhrnna hodnoceni slozek, ktera ciselnik nevede - jejich kod vznika
#: az za behu slozenim nazvu slozky a slova CELKEM.
SOUHRNY = {
    "MB": "makrozoobentos",
    "MZB": "makrozoobentos",
    "FB": "fytobentos",
    "FP": "fytoplankton",
    "MF": "makrofyta",
    "RY": "ryby",
    "RYBY": "ryby",
    "CHEM": "fyzikálně-chemické složky",
}

#: Metriky, ktere uz neexistuji, ale jejich vysledky zustaly v databazi
#: z drivejsich verzi vypoctu. Nikam se nevypisuji - jinak by uzivatel
#: cetl cislo, ktere zadna platna metodika nezna.
#:
#: Prepocet je nesmaze: zahazuje jen vysledky metrik, ktere prave pocita,
#: a tuhle uz zadny modul nepocita. Ze seznamu jde radek vyradit teprve
#: tehdy, kdyz se odpovidajici radky z tabulky `results` smazou.
ZASTARALE = frozenset({"RYBY_01"})

#: Kod slozky a poradove cislo oddelene podtrzitkem - `FB_01`, `MF_01`.
#: Vysledky nesou obe podoby zapisu, ciselnik jen tu bez podtrzitka,
#: takze se zkousi i ona.
PODTRZITKO = re.compile(r"^([A-Z]+)_(\d+)$")


def cesta_k_ciselniku():
    return v_korenu(SOUBOR)


def _sjednoceny(kod):
    """Kod bez podtrzitka mezi kodem slozky a cislem.

    `FB_01` i `FB01` je tataz metrika; porovnavat se proto musi az
    sjednocena podoba, a to na obou stranach.
    """
    klic = str(kod or "").strip().upper()
    shoda = PODTRZITKO.match(klic)
    return shoda.group(1) + shoda.group(2) if shoda else klic


#: Zastarale kody ve sjednocene podobe, aby na zapisu nezalezelo.
_ZASTARALE_SJEDNOCENE = frozenset(_sjednoceny(k) for k in ZASTARALE)


def je_zastarala(kod):
    """Jde o metriku, ktera uz se nepocita a nema se zobrazovat?"""
    if not kod:
        return False
    return _sjednoceny(kod) in _ZASTARALE_SJEDNOCENE


def _hodnota(radek, nazvy):
    for nazev in nazvy:
        if radek.get(nazev):
            return str(radek[nazev]).strip()
    return ""


def nacti(cesta=None):
    """Nacte ciselnik.

    Returns:
        dict {zkratka: popis}; prazdny, kdyz soubor chybi
    """
    popisy = {}
    for radek in csv_ciselnik.radky(cesta or cesta_k_ciselniku()):
        zkratka = _hodnota(radek, SLOUPCE_ZKRATKA)
        popis = _hodnota(radek, SLOUPCE_POPIS)
        if zkratka and popis:
            popisy[zkratka.upper()] = popis
    return popisy


class Prekladac:
    """Prevadi kody metrik na ceske nazvy.

    Ciselnik se nacte pri prvnim pouziti a drzi se v pameti - prochazeni
    vysledku by ho jinak cetlo znovu pro kazdy radek.
    """

    def __init__(self, cesta=None):
        self._cesta = cesta
        self._popisy = None

    @property
    def popisy(self):
        if self._popisy is None:
            self._popisy = nacti(self._cesta)
        return self._popisy

    def popis(self, kod):
        """Vrati cesky nazev metriky, nebo samotny kod.

        Krome ciselniku zna souhrnna hodnoceni typu `MB_CELKEM`, ktera
        ciselnik nevede - jejich kod se sklada az pri vypoctu.
        """
        if not kod:
            return kod
        klic = str(kod).strip().upper()

        popis = self.popisy.get(klic)
        if popis:
            return popis

        # `FB_01` a `FB01` je tataz metrika, jen jinak zapsana.
        popis = self.popisy.get(_sjednoceny(klic))
        if popis:
            return popis

        if klic.endswith("_CELKEM"):
            slozka = SOUHRNY.get(klic[:-len("_CELKEM")])
            if slozka:
                return f"celkové hodnocení — {slozka}"
            return "celkové hodnocení"

        return kod

    def popisek(self, kod):
        """Nazev s kodem v zavorce, nebo jen kod.

        Kod zustava videt zamerne - uzivatel podle nej hleda metriku
        v metodikach a v exportech.
        """
        popis = self.popis(kod)
        return kod if popis == kod else f"{popis} ({kod})"


#: Sdilena instance pro GUI.
PREKLADAC = Prekladac()
