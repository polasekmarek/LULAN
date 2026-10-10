"""
Rozrazovaci registr - vyber hodnotici metodiky podle vzorku a utvaru.

Misto vnorenych if/elif je mapovani vedeno jako tabulka REGISTR:

    (slozka, kategorie, hmwb, vysychavost, broditelnost) -> hodnotici funkce

Zastupny znak "*" znamena, ze na dane vlastnosti nezalezi. Klice se
vyhodnocuji od nejkonkretnejsiho k nejobecnejsimu, takze vyjimky staci
pridat jako konkretnejsi radek.

Vlastnosti utvaru (tabulka `utvary`):
    KATEGORIE   R = tekouci voda (reka), J = stojata voda (jezero)
    HMWB        P = prirozeny utvar        -> hodnoti se ekologicky STAV
                S = silne ovlivneny (HMWB) -> hodnoti se ekologicky POTENCIAL
                U = umely (AWB)            -> biologicke slozky se nehodnoti
    VYSYCHAVY   P = staletekouci (perennial), I = vysychavy (intermittent)
    BROD        B = broditelny, NEBROD = nebroditelny

Pravidla pro silne ovlivnene a umele utvary vychazeji z metodiky
Opatrilova a kol. (2013), Metoda pro hodnoceni ekologickeho potencialu
silne ovlivnenych a umelych vodnich utvaru - kategorie reka:

  * makrozoobentos ma pro HMWB vlastni prevodni tabulku (snizene horni meze)
  * fytobentos a makrofyta se u HMWB hodnoti SHODNE s prirozenymi utvary
    (metodika, kap. 6)
  * u umelych utvaru (AWB) se biologicke slozky nehodnoti vubec, hodnoceni
    se provadi pouze podle fyzikalne-chemickych parametru (metodika, kap. 6)
"""

from __future__ import annotations

from itertools import product

from PyQt6.QtSql import QSqlQuery

from . import neimplementovane
from .jezera_runner import fp_jezero, mf_jezero, ryby_jezero
from .fb_intermittent import hodnoceni as fb_intermittent
from .fb_perennial import hodnoceni as fb_perennial
from .fp_reka import hodnoceni as fp_reka
from .mf_reka import hodnoceni as mf_reka
from .mzb_intermittent import hodnoceni as mzb_intermittent
from .mzb_perennial_broditelne import hodnoceni as mzb_perennial_broditelne
from .mzb_perennial_nebroditelne import hodnoceni as mzb_perennial_nebroditelne
from .mzb_potencial_broditelne import hodnoceni as mzb_potencial_broditelne
from .mzb_velke_reky import hodnoceni as mzb_velke_reky
from .ryby_potencial import hodnoceni as ryby_potencial
from .ryby_reka import hodnoceni as ryby_reka
from .velke_reky_utvary import je_velka_reka, utvar_vzorku

#: Vychozi vlastnosti utvaru, pokud vzorek nema prirazeny vodni utvar.
VYCHOZI_UTVAR = {
    "kategorie": "R",
    "hmwb": "P",
    "vysychavy": "P",
    "brod": "B",
}

#: Sloupce, ktere musi tabulka `utvary` mit, aby slo rozhodnout o metodice.
OCEKAVANE_SLOUPCE_UTVARU = (
    "ID_UTVARU", "KATEGORIE", "HMWB", "VYSYCHAVY", "BROD",
)

#: Hodnoty sloupce HMWB, u kterych se hodnoti potencial misto stavu.
HMWB_POTENCIAL = ("S", "U")

#: Hodnota sloupce HMWB pro umely utvar - biologicke slozky se nehodnoti.
HMWB_UMELY = "U"

#: Hodnoty `samples.INTERMITTENT`, ktere znamenaji "vzorek z vysychaveho
#: useku". Sloupec je textovy a napric zdroji se plni ruzne.
PRIZNAK_VYSYCHAVY = {"TRUE", "T", "1", "ANO", "Y", "YES", "I"}


def _vysychavy_vzorek(hodnota):
    """Rika, zda je vzorek oznacen jako pochazejici z vysychaveho useku."""
    return str(hodnota or "").strip().upper() in PRIZNAK_VYSYCHAVY

#: (slozka, kategorie, hmwb, vysychavost, broditelnost) -> hodnotici funkce
#: None znamena, ze se dana kombinace nehodnoti vubec.
REGISTR = {
    # --- Fytobentos -------------------------------------------------------
    # Hodnoceni HMWB je shodne s prirozenymi utvary (metodika 2013, kap. 6).
    ("FB", "R", "U", "*", "*"): None,   # umely utvar - biologie se nehodnoti
    ("FB", "R", "*", "I", "*"): fb_intermittent,
    ("FB", "R", "*", "P", "*"): fb_perennial,
    ("FB", "J", "*", "*", "*"): None,   # fytobentos se v jezerech nehodnoti

    # --- Makrozoobentos ---------------------------------------------------
    # POZOR: vzorky z vyjmenovanych utvaru velkych nebroditelnych rek se do
    # teto tabulky vubec nedostanou - odchyti je drive kontrola v
    # vyber_funkci_pro_vzorek(). Viz velke_reky_utvary.py.
    ("MZB", "R", "U", "*", "*"): None,  # umely utvar - biologie se nehodnoti
    # silne ovlivnene broditelne toky maji vlastni prevodni tabulku
    ("MZB", "R", "S", "P", "B"): mzb_potencial_broditelne,
    ("MZB", "R", "*", "I", "*"): mzb_intermittent,
    ("MZB", "R", "*", "P", "NEBROD"): mzb_perennial_nebroditelne,
    ("MZB", "R", "*", "P", "*"): mzb_perennial_broditelne,
    ("MZB", "J", "*", "*", "*"): None,  # makrozoobentos se v jezerech nehodnoti

    # --- Fytoplankton -----------------------------------------------------
    # Stav i potencial resi jeden modul, lisi se jen prevodni tabulkou;
    # o tom, ktera se pouzije, rozhoduje priznak `potencial`.
    ("FP", "R", "U", "*", "*"): None,
    ("FP", "R", "*", "*", "*"): fp_reka,
    ("FP", "J", "*", "*", "*"): fp_jezero,

    # --- Makrofyta --------------------------------------------------------
    # Hodnoceni HMWB je shodne s prirozenymi utvary (metodika 2013, kap. 6).
    ("MF", "R", "U", "*", "*"): None,
    ("MF", "R", "*", "*", "*"): mf_reka,
    ("MF", "J", "*", "*", "*"): mf_jezero,

    # --- Ryby -------------------------------------------------------------
    # Stav podle Janac a kol. (2019), potencial podle Janac a kol. (2024).
    # U potencialu se meze a vahy neberou podle typu toku, ale podle
    # kategorie silne ovlivneneho utvaru - proto vlastni modul.
    ("RYBY", "R", "U", "*", "*"): ryby_potencial,
    ("RYBY", "R", "S", "*", "*"): ryby_potencial,
    ("RYBY", "R", "*", "*", "*"): ryby_reka,
    ("RYBY", "J", "*", "*", "*"): ryby_jezero,
}

#: Slozky, u kterych se v jezerech hodnoti vzdy potencial, nikdy stav.
JEZERA_VZDY_POTENCIAL = {"FP", "MF", "RYBY"}

#: Slozky, u kterych se ani u HMWB nemeni hranice trid - hodnoti se
#: shodne s prirozenymi utvary (metodika 2013, kap. 6).
HMWB_HODNOTI_JAKO_STAV = {"FB", "MF"}

#: Lokality, na ktere uz bylo upozorneno, ze nemaji prirazeny vodni utvar.
#: Bez toho by se hlaska vypsala pro kazdy vzorek zvlast (stovky radku).
_ohlasene_lokality = set()

#: Bylo uz upozorneno na nezmigrovanou databazi?
_ohlasena_migrace = False


def vycisti_hlaseni():
    """Vyprazdni seznam uz ohlasenych lokalit bez vodniho utvaru."""
    global _ohlasena_migrace
    _ohlasene_lokality.clear()
    _ohlasena_migrace = False


def zkontroluj_schema(db_connection):
    """Overi, ze tabulka `utvary` ma ocekavane sloupce.

    Sloupec HMWB se drive jmenoval HMCH; migrace uz je soucasti dodavane
    databaze, takze se tady jen overuje, ze schema odpovida.

    Returns:
        (v_poradku, zprava) - zprava je None, kdyz je vse v poradku
    """
    query = QSqlQuery(db_connection)
    if not query.exec("PRAGMA table_info(utvary)"):
        return True, None

    sloupce = []
    while query.next():
        sloupce.append(query.value(1))

    if not sloupce:
        return True, None

    chybi = [s for s in OCEKAVANE_SLOUPCE_UTVARU if s not in sloupce]
    if not chybi:
        return True, None

    return False, (
        f"Tabulka `utvary` nemá sloupce: {', '.join(chybi)}.\n"
        f"Nalezené sloupce: {', '.join(sloupce)}.\n\n"
        f"Použijte databázi dodanou s aplikací."
    )


def vlastnosti_utvaru(sample_id, db_connection):
    """Nacte vlastnosti vodniho utvaru, do ktereho vzorek patri.

    Pokud utvar neni prirazen, vrati VYCHOZI_UTVAR.

    Vysychavost se bere z utvaru, ale priznak `samples.INTERMITTENT`
    ma prednost, kdyz je nastaveny na TRUE. Vysychani je vlastnost
    useku toku, ne celeho utvaru - utvar byva rozsahly a jeho zarazeni
    hrube. Kdyz tedy odberatel u vzorku vyslovne zaznamena, ze lokalita
    vysycha, hodnoti se vzorek podle metodiky vysychavych toku, i kdyz
    je utvar veden jako staletekouci.

    Opacne to neplati: prazdna hodnota ani FALSE zarazeni utvaru
    neprepisuji. FALSE je totiz ve vetsine zaznamu jen nevyplnena
    vychozi hodnota, ne uvazene popreni vysychavosti.

    Returns:
        dict s klici kategorie, hmwb, vysychavy, brod
    """
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT u.KATEGORIE, u.HMWB, u.VYSYCHAVY, u.BROD, s.LOC_ID,
               s.INTERMITTENT
        FROM samples s
        LEFT JOIN loc l ON s.LOC_ID = l.KOD
        LEFT JOIN utvary u ON l.VU = u.ID_UTVARU
        WHERE s.SAMPLE_ID = ?
        """
    )
    query.addBindValue(sample_id)

    if not query.exec() or not query.next():
        global _ohlasena_migrace
        if not _ohlasena_migrace:
            _ohlasena_migrace = True
            v_poradku, zprava = zkontroluj_schema(db_connection)
            if not v_poradku:
                print(f"[registry] {zprava}")
        return dict(VYCHOZI_UTVAR)

    vysychavy_vzorek = _vysychavy_vzorek(query.value(5))

    if query.value(0) is None:
        lokalita = query.value(4)
        if lokalita not in _ohlasene_lokality:
            _ohlasene_lokality.add(lokalita)
            print(
                f"[registry] Lokalita {lokalita or '?'} nema prirazeny vodni "
                f"utvar - pouzity vychozi vlastnosti {VYCHOZI_UTVAR}"
            )
        utvar = dict(VYCHOZI_UTVAR)
        if vysychavy_vzorek:
            utvar["vysychavy"] = "I"
        return utvar

    return {
        "kategorie": query.value(0),
        "hmwb": query.value(1),
        "vysychavy": "I" if vysychavy_vzorek else query.value(2),
        "brod": query.value(3),
    }


def vyber_funkci(slozka, utvar):
    """Vybere hodnotici funkci pro danou slozku a vlastnosti utvaru.

    Returns:
        (funkce, potencial) - funkce je None, pokud se kombinace nehodnoti
    """
    kategorie = utvar.get("kategorie") or VYCHOZI_UTVAR["kategorie"]
    hmwb = utvar.get("hmwb") or VYCHOZI_UTVAR["hmwb"]
    vysychavy = utvar.get("vysychavy") or VYCHOZI_UTVAR["vysychavy"]
    brod = utvar.get("brod") or VYCHOZI_UTVAR["brod"]

    # U silne ovlivnenych (S) a umelych (U) utvaru se hodnoti ekologicky
    # potencial, u prirozenych (P) ekologicky stav.
    potencial = hmwb in HMWB_POTENCIAL

    # Fytobentos a makrofyta se ale i u HMWB hodnoti shodne s prirozenymi
    # utvary - vcetne hranic trid (metodika 2013, kap. 6).
    if slozka in HMWB_HODNOTI_JAKO_STAV:
        potencial = False

    if kategorie == "J" and slozka in JEZERA_VZDY_POTENCIAL:
        potencial = True

    # projit klice od nejkonkretnejsiho po nejobecnejsi
    for k, h, v, b in product(
        (kategorie, "*"), (hmwb, "*"), (vysychavy, "*"), (brod, "*")
    ):
        klic = (slozka, k, h, v, b)
        if klic in REGISTR:
            return REGISTR[klic], potencial

    return None, potencial


#: Slozky, u kterych se pro vyjmenovane utvary velkych nebroditelnych rek
#: pouziva samostatna metodika (Nemejcova a kol. 2019).
VELKE_REKY_SLOZKY = {"MZB": mzb_velke_reky}


def vyber_funkci_pro_vzorek(slozka, utvar, sample_id, db_connection):
    """Vybere hodnotici funkci pro konkretni vzorek.

    Na rozdil od vyber_funkci() zohledni i prislusnost vodniho utvaru
    k vyjmenovanym velkym nebroditelnym rekam. Tato kontrola ma prednost
    pred sloupcem BROD - metodika velke reky vymezuje seznamem utvaru,
    nikoli Strahlerovym radem ani broditelnosti.

    Returns:
        (funkce, potencial)
    """
    if slozka in VELKE_REKY_SLOZKY:
        id_utvaru = utvar_vzorku(sample_id, db_connection)
        if je_velka_reka(id_utvaru):
            # umely utvar se nehodnoti ani zde
            if utvar.get("hmwb") == HMWB_UMELY:
                return None, True
            potencial = utvar.get("hmwb") in HMWB_POTENCIAL
            return VELKE_REKY_SLOZKY[slozka], potencial

    return vyber_funkci(slozka, utvar)


def duvod_nehodnoceni(slozka, utvar):
    """Vrati text vysvetlujici, proc se kombinace nehodnoti.

    Pouziva runner pro srozumitelnou poznamku ve vysledcich.
    """
    if utvar.get("hmwb") == HMWB_UMELY:
        return (
            "Umely vodni utvar - biologicke slozky se nehodnoti, "
            "hodnoceni se provadi pouze podle fyzikalne-chemickych parametru"
        )
    if utvar.get("kategorie") == "J":
        return f"Slozka {slozka} se v jezerech nehodnoti"
    return (
        f"Pro kombinaci {slozka} + kategorie={utvar.get('kategorie')}, "
        f"HMWB={utvar.get('hmwb')} neni definovana metodika"
    )
