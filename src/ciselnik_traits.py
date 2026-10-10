"""
Prekladovy slovnik zkratek autekologickych charakteristik (traits).

Taxonomicke seznamy maji desitky sloupcu se zkratkami jako `SZX`, `HLI`
nebo `repr_frc`. Pro cteni je to nepouzitelne, proto se v prehledu
detailu taxonu misto zkratky ukazuje cesky popis z ciselniku
`dtb/ciselnik_traits.csv`.

Struktura ciselniku
-------------------
    CON_ID   slozka, ke ktere zkratka patri (MB, FB, MF, RYBY)
    ID       zkratka tak, jak se jmenuje sloupec v taxalistu
    CS       cesky popis

Tataz zkratka muze u ruznych slozek znamenat neco jineho, proto se hleda
nejdriv v ramci slozky a teprve pak napric.

Kodovani se hleda automaticky. Soubor byva ulozeny z Excelu, takze
prichazi v ruznych kodovanich - u macOS Excelu je to `mac_latin2`,
u Windows `cp1250`. Spatne uhodnute kodovani nezpusobi chybu, jen
rozsypany text, proto se vybira to, ktere da nejmene podezrelych znaku.
"""

from __future__ import annotations

import os

import csv_ciselnik
from cesty import v_korenu

#: Umisteni ciselniku vuci korenu projektu.
SOUBOR = os.path.join("dtb", "ciselnik_traits.csv")

#: Nazev slozky podle prefixu tabulky taxalistu. Makrozoobentos je
#: v ciselniku veden jednou jako `MB`, jednou jako `MZB` - beru obojí.
SLOZKA_TABULKY = {
    "taxalist_mzb": ("MB", "MZB"),
    "taxalist_fb": ("FB",),
    "taxalist_mf": ("MF",),
    "taxalist_ryby": ("RYBY",),
}

#: Sloupce, ktere se v taxalistu jmenuji jinak nez v ciselniku.
#: Nejde o jine veliciny, jen o jiny zapis tehoz - proto se prelozi
#: pres tuhle tabulku a v ciselniku se nic menit nemusi.
#: Dvojice prosel a odsouhlasil zadavatel.
#:
#: Prednost ma vzdy ciselnik: kdyz do nej pribude polozka pojmenovana
#: primo podle sloupce, alias se prestane pouzivat a lze ho smazat.
#: Presne to se stalo u teplotnich sloupcu `temp_pref_*` a
#: `temp_range_*`, ktere uz ciselnik vede pod jejich vlastnimi nazvy.
ALIASY = {
    "LC_FLEXIBLE": "FLEXIBLE",
    "LC_NOT_STRICT_FIXED": "NOT_STRICT_FIXED",
    "LC_STRICT_FIXED": "STRICT_FIXED",
    "ADD": "ADDX",
    "SIZE": "MM",
}

#: Popisy, ktere ciselnik nema v pouzitelne podobe.
#:
#: Ciselnik rozlisuje indikatory podle sezony (`IND_PERM_PODZ`,
#: `IND_PERN_JARO`, `IND_SUCHO_JARO`, `IND_SUCHO_POD`), ale taxalist
#: ma jen dva sloupce bez rozliseni sezony. Odkaz na sezonni kod by
#: tedy uzivatele mylil. Az ciselnik dostane sezonne neutralni polozky,
#: staci tyhle dva radky smazat.
VLASTNI_POPISY = {
    "indicator_perm": "indikátor permanentního průtoku",
    "indicator_int": "indikátor vysychání toku",
}


def cesta_k_ciselniku():
    return v_korenu(SOUBOR)


def nacti(cesta=None):
    """Nacte ciselnik.

    Returns:
        dict {(slozka, zkratka): popis}; prazdny, kdyz soubor chybi
    """
    popisy = {}
    for radek in csv_ciselnik.radky(cesta or cesta_k_ciselniku()):
        zkratka = (radek.get("ID") or "").strip()
        popis = (radek.get("CS") or "").strip()
        if zkratka and popis:
            popisy[((radek.get("CON_ID") or "").strip(), zkratka)] = popis
    return popisy


class Prekladac:
    """Prevadi zkratky traitu na ceske popisy.

    Ciselnik se nacte pri prvnim pouziti a drzi se v pameti - je maly
    a pri prochazeni taxonu by se jinak cetl znovu pro kazdy radek.
    """

    def __init__(self, cesta=None):
        self._cesta = cesta
        self._popisy = None

    @property
    def popisy(self):
        if self._popisy is None:
            self._popisy = nacti(self._cesta)
        return self._popisy

    def slozky(self, tabulka):
        """Ze jmena tabulky taxalistu odvodi kody slozky v ciselniku."""
        return SLOZKA_TABULKY.get(str(tabulka or "").lower(), ())

    def popis(self, zkratka, tabulka=None):
        """Vrati cesky popis zkratky, nebo samotnou zkratku.

        Poradi hledani:
          1. vlastni popis (ciselnik ho v pouzitelne podobe nema)
          2. ciselnik v ramci slozky - tataz zkratka muze u ruznych
             slozek znamenat neco jineho
          3. ciselnik napric slozkami - lepsi priblizny popis nez
             hola zkratka
        Kroky 2 a 3 se zkousi i pro alias, pokud sloupec nejaky ma.
        """
        if not zkratka:
            return zkratka
        if zkratka in VLASTNI_POPISY:
            return VLASTNI_POPISY[zkratka]

        for kod in (zkratka, ALIASY.get(zkratka)):
            if not kod:
                continue
            for slozka in self.slozky(tabulka):
                popis = self.popisy.get((slozka, kod))
                if popis:
                    return popis
            for (_, klic), popis in self.popisy.items():
                if klic == kod:
                    return popis
        return zkratka

    def popisek(self, zkratka, tabulka=None):
        """Popis se zkratkou v zavorce, nebo jen zkratka.

        Zkratka zustava videt zamerne - uzivatel podle ni hleda sloupec
        v metodikach a v exportech.
        """
        popis = self.popis(zkratka, tabulka)
        return zkratka if popis == zkratka else f"{popis} ({zkratka})"


#: Sdilena instance pro GUI.
PREKLADAC = Prekladac()
