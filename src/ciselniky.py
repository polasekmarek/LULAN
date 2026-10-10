"""
Ciselniky kodovanych sloupcu a jejich prevod na citelne popisky.

Databaze drzi u vodnich utvaru jednopismenne kody (KATEGORIE = "R",
HMWB = "P", ...). Pro vypocet jsou pohodlne, pro uzivatele necitelne.
Tady je jedno misto, ktere urcuje:

  * jake hodnoty jsou v danem sloupci povolene
  * jak se maji zobrazovat v aplikaci
  * jak popsat sloupec v hlavicce tabulky

Modul nezavisi na PyQt, aby sel pouzit i pri importu z CSV a v testech.
"""

from __future__ import annotations


class Ciselnik:
    """Prevod mezi kodem v databazi a popiskem v aplikaci.

    Args:
        sloupec: nazev sloupce v databazi
        popisek: text do hlavicky tabulky
        polozky: dvojice (kod, popisek) v poradi, v jakem se maji nabizet
        vychozi: kod pouzity u nove zalozeneho zaznamu
    """

    def __init__(self, sloupec, popisek, polozky, vychozi=None):
        self.sloupec = sloupec
        self.popisek = popisek
        self.polozky = tuple(polozky)
        self.vychozi = vychozi if vychozi is not None else polozky[0][0]
        self._na_popisek = {kod: text for kod, text in polozky}
        self._na_kod = {text.upper(): kod for kod, text in polozky}
        # at projde i zadani kodu primo
        for kod, _text in polozky:
            self._na_kod.setdefault(str(kod).upper(), kod)

    @property
    def kody(self):
        return tuple(kod for kod, _ in self.polozky)

    @property
    def popisky(self):
        return tuple(text for _, text in self.polozky)

    def popis(self, kod):
        """Kod -> popisek. Neznamou hodnotu vrati beze zmeny."""
        if kod is None or kod == "":
            return ""
        return self._na_popisek.get(str(kod).strip(), str(kod))

    def kod(self, hodnota):
        """Popisek (nebo kod) -> kod. Pri nezname hodnote vrati None."""
        if hodnota is None:
            return None
        return self._na_kod.get(str(hodnota).strip().upper())

    def je_platny(self, kod):
        return kod is not None and str(kod).strip() in self._na_popisek


#: Ciselniky sloupcu tabulky `utvary`.
UTVARY = {
    c.sloupec: c
    for c in (
        Ciselnik(
            "KATEGORIE", "KATEGORIE",
            (("R", "ŘEKA"), ("J", "JEZERO")),
        ),
        Ciselnik(
            "HMWB", "HMWB",
            (("P", "PŘIROZENÝ"),
             ("S", "S. OVLIVNĚNÝ"),
             ("U", "UMĚLÝ")),
        ),
        Ciselnik(
            "VYSYCHAVY", "VYSYCHAVOST",
            (("P", "PERENIÁLNÍ"), ("I", "VYSYCHAVÝ")),
        ),
        Ciselnik(
            "BROD", "BRODITELNOST",
            (("B", "BRODITELNÝ"), ("NEBROD", "NEBRODITELNÝ")),
        ),
    )
}

#: Popisky ostatnich sloupcu tabulky `utvary`.
UTVARY_POPISKY = {
    "ID_UTVARU": "KÓD ÚTVARU",
    "NAZ_UTVARU": "NÁZEV ÚTVARU",
    "DILCI_POVODI": "DÍLČÍ POVODÍ",
}


def popisek_sloupce(sloupec, ciselniky=None, popisky=None):
    """Vrati text do hlavicky tabulky pro dany sloupec."""
    ciselniky = UTVARY if ciselniky is None else ciselniky
    popisky = UTVARY_POPISKY if popisky is None else popisky
    if sloupec in ciselniky:
        return ciselniky[sloupec].popisek
    return popisky.get(sloupec, sloupec)


def zkontroluj_utvar(zaznam):
    """Overi kodovane sloupce jednoho utvaru.

    Args:
        zaznam: dict {sloupec: hodnota}

    Returns:
        list chybovych hlasek; prazdny seznam znamena, ze je vse v poradku
    """
    chyby = []
    for sloupec, ciselnik in UTVARY.items():
        if sloupec not in zaznam:
            continue
        hodnota = zaznam[sloupec]
        if hodnota is None or str(hodnota).strip() == "":
            chyby.append(
                f"{ciselnik.popisek}: hodnota musí být vyplněná "
                f"({', '.join(ciselnik.popisky)})"
            )
            continue
        if not ciselnik.je_platny(hodnota):
            chyby.append(
                f"{ciselnik.popisek}: '{hodnota}' není povolená hodnota "
                f"({', '.join(ciselnik.popisky)})"
            )
    return chyby


def vychozi_utvar():
    """Vychozi hodnoty kodovanych sloupcu pro nove zalozeny utvar."""
    return {sloupec: c.vychozi for sloupec, c in UTVARY.items()}
