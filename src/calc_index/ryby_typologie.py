"""
Typologie toku pro hodnoceni podle ryb (typy A-G).

Zdroj: Janac a kol. (2019), Metodika hodnoceni ekologickeho stavu utvaru
povrchovych vod tekoucich (kategorie reka) pomoci biologicke slozky ryby,
Tabulka 1 a Tabulka 2.

Typologie stoji na trech udajich:

    umori              Baltske (Odra) / Cerne (Dunaj) / Severni (Labe)
    nadmorska vyska    pasma >=500 / 400-500 / 250-400 / <250 m n.m.
    rad toku           Strahleruv rad; toky 1.-3. radu se NEHODNOTI

Vysledkem je jeden ze sedmi typu:

    A  horske potoky              E  parmove reky (vyssi)
    B  podhorske potoky a ricky   F  parmove reky (nizsi)
    C  podhorske ricky labske     G  nizinne reky
    D  nizinne ricky

Na tocich 1.-3. radu dle Strahlera neni vhodne pouzivat rybi spolecenstvo
jako bioindikator (Jurajda a kol. 2006, 2019), proto pro ne hodnoceni
neexistuje - funkce vrati None a volajici modul vzorek preskoci.
"""

from __future__ import annotations

#: Prevod sloupce `loc.UMORI` na umori v pojeti metodiky.
#:
#: Databaze LULANu vede umori podle hlavniho recistě (1 Labe, 2 Odra,
#: 3 Dunaj), metodika podle more, do ktereho odtekaji.
UMORI_NA_MORE = {
    1: "Severni",   # Labe   -> Severni more
    2: "Baltske",   # Odra   -> Baltske more
    3: "Cerne",     # Dunaj  -> Cerne more
}

#: Pasma nadmorske vysky (Tabulka 2), od nejvyssiho k nejnizsimu.
#: Dvojice (dolni_mez, index_sloupce_v_klici).
VYSKOVA_PASMA = (
    (500.0, 0),   # h >= 500
    (400.0, 1),   # 400 <= h < 500
    (250.0, 2),   # 250 <= h < 400
    (float("-inf"), 3),   # h < 250
)

#: Klic pro zarazeni profilu do typu toku (Tabulka 2).
#:
#: {umori: {Strahleruv rad: (typ pro >=500, 400-500, 250-400, <250)}}
#:
#: Kombinace, ktere v tabulce nejsou (napr. Baltske umori 8. radu),
#: v podminkach CR nenastavaji - viz kap. 2 metodiky.
KLIC_TYPU = {
    "Baltske": {
        4: ("A", "B", "B", "B"),
        5: ("A", "B", "B", "E"),
        6: ("A", "B", "B", "E"),
        7: ("A", "B", "B", "F"),
    },
    "Cerne": {
        4: ("A", "B", "B", "D"),
        5: ("A", "B", "B", "D"),
        6: ("A", "E", "E", "F"),
        7: ("A", "F", "F", "F"),
        8: ("A", "G", "G", "G"),
    },
    "Severni": {
        4: ("A", "B", "B", "B"),
        5: ("A", "C", "C", "C"),
        6: ("A", "C", "F", "F"),
        7: ("A", "F", "F", "F"),
        8: ("A", "G", "G", "G"),
        9: ("A", "G", "G", "G"),
    },
}

#: Nejnizsi Strahleruv rad, na kterem se ryby hodnoti.
NEJNIZSI_RAD = 4

VSECHNY_TYPY = ("A", "B", "C", "D", "E", "F", "G")


def vyskove_pasmo(mnm):
    """Vrati index vyskoveho pasma pro nadmorskou vysku, nebo None."""
    from .common import to_float

    mnm = to_float(mnm)
    if mnm is None:
        return None
    for dolni_mez, index in VYSKOVA_PASMA:
        if mnm >= dolni_mez:
            return index
    return None


def urci_typ(umori, mnm, strahler):
    """Zaradi profil do typu toku A-G podle Tabulky 2.

    Args:
        umori: hodnota sloupce `loc.UMORI` (1 Labe, 2 Odra, 3 Dunaj)
        mnm: nadmorska vyska [m n.m.]
        strahler: Strahleruv rad toku

    Returns:
        (typ, duvod) - typ je pismeno A-G nebo None; duvod je text
        vysvetlujici, proc typ nelze urcit (jinak None)
    """
    if strahler is None:
        return None, "Chybi Strahleruv rad lokality"
    try:
        rad = int(strahler)
    except (TypeError, ValueError):
        return None, f"Neplatny Strahleruv rad: {strahler!r}"

    if rad < NEJNIZSI_RAD:
        return None, (
            f"Nehodnoceno: tok {rad}. Strahlerova řádu, na tocích do "
            f"{NEJNIZSI_RAD - 1}. řádu se ryby jako bioindikátor nepoužívají"
        )

    more = UMORI_NA_MORE.get(umori)
    if more is None:
        return None, f"Nezname umori lokality: {umori!r}"

    pasmo = vyskove_pasmo(mnm)
    if pasmo is None:
        return None, "Chybi nadmorska vyska lokality"

    radek = KLIC_TYPU[more].get(rad)
    if radek is None:
        return None, (
            f"Pro umori {more} a {rad}. rad toku neni v Tab. 2 zadny typ"
        )

    return radek[pasmo], None


def popis_typu(typ):
    """Slovni popis typu toku."""
    return {
        "A": "horske potoky",
        "B": "podhorske potoky a ricky",
        "C": "podhorske ricky labske",
        "D": "nizinne ricky",
        "E": "parmove reky (vyssi)",
        "F": "parmove reky (nizsi)",
        "G": "nizinne reky",
    }.get(typ, "?")
