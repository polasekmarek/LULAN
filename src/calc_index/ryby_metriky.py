"""
Metriky ceskeho multimetrickeho indexu (CZI) pro ryby.

Zdroj: Janac a kol. (2019), kap. 3, Tabulka 3 a Tabulka 4.

Metriky
-------
    TD   pocet typickych taxonu daneho typu toku
    AR   abundance reofilu [ks/100 m]; u typu A abundance TYPICKYCH taxonu
    ND1  pocet nezadoucich taxonu (typy A-C) / pritomnost invaznich (D-G)
    ND2  relativni zastoupeni nezadoucich taxonu (0-1)
    TA   celkova abundance vsech juvenilnich ryb - pouziva se pouze pri
         hodnoceni potencialu u kategorii I a VI (Janac a kol. 2024)

Zarazeni taxonu drzi taxonomicky seznam `taxalist_ryby`:

    R           reofilni taxon
    EL          eurytopni nebo limnofilni taxon
    I           invazni taxon
    A az G      taxon je typicky pro tok daneho typu

Ve vsech sloupcich je priznak 1 nebo prazdno.

Determinacni uroven
-------------------
Metodika (kap. 5): "u vetsiny taxonu je pozadovana presnost urceni do druhu;
pokud maji vsechny ceske druhy daneho rodu stejne ekologicke naroky
rozhodujici pro vypocet CZI, je vyzadovana presnost urceni do rodu (hrouzci,
vranky)."

Typicke taxony se proto pocitaji na urovni zaznamu, ktery ma priznak
vyplneny NEJVYSE v rodokmenu: nalez `Lampetra planeri` i `Lampetra
fluviatilis` v jednom vzorku je jeden typicky taxon (`Lampetra sp.`),
protoze Tab. 4 vede mihule jako jednu polozku.
"""

from __future__ import annotations

from math import log

from .common import nacti_data_vzorku, nacti_taxalist, taxonomicka_cesta, vyres_synonyma

#: Sloupce taxonomickeho seznamu, ktere nesou zarazeni taxonu.
TRAIT_SLOUPCE = ["R", "EL", "I", "A", "B", "C", "D", "E", "F", "G"]

#: Typy toku, u kterych jsou nezadoucimi taxony eurytopni a limnofilni ryby.
#: U zbylych typu (D-G) se za nezadouci povazuji taxony invazni.
TYPY_S_EL = ("A", "B", "C")

#: Taxony, ktere Tab. 4 vede jako JEDNU polozku, ale v taxonomickem seznamu
#: stoji vedle sebe - rodokmen je proto neslouci.
#:
#: * "Hrouzci Gobio sp./Romanogobio sp." jsou dva samostatne rody
#: * "Pstruh obecny Salmo trutta" ma v seznamu jeste obe formy (morphy),
#:   ktere jsou vedene jako sourozenci druhu, ne jako jeho potomci
#:
#: Bez tohoto sloucení by vzorek s hrouzkem obecnym i ostroretkou
#: (Romanogobio) vykazal o jeden typicky taxon vic, nez metodika pocita.
EKVIVALENTNI_SKUPINY = {
    "Gobio sp.": "Gobio sp./Romanogobio sp.",
    "Gobio gobio": "Gobio sp./Romanogobio sp.",
    "Romanogobio sp.": "Gobio sp./Romanogobio sp.",
    "Gobio sp./Romanogobio sp.": "Gobio sp./Romanogobio sp.",
    "Salmo trutta m. fario": "Salmo trutta",
    "Salmo trutta m. trutta": "Salmo trutta",
}


def je_priznak(hodnota):
    """True, pokud je priznak v taxalistu vyplneny."""
    if hodnota is None:
        return False
    if isinstance(hodnota, str):
        return hodnota.strip() not in ("", "0")
    return bool(hodnota)


def nacti_vzorek(db_connection, sample_id):
    """Nacte a vyresi taxony vzorku ryb.

    Returns:
        (data, taxalist) kde data je dict {taxon_id: abundance},
        nebo (None, taxalist) pokud vzorek neobsahuje pouzitelne zaznamy
    """
    taxalist = nacti_taxalist(db_connection, "taxalist_ryby", TRAIT_SLOUPCE)
    taxa = nacti_data_vzorku(db_connection, sample_id)
    if not taxa:
        return None, taxalist
    data = vyres_synonyma(taxa, taxalist["by_name"])
    return (data or None), taxalist


def nositel_priznaku(taxon_id, sloupec, by_id):
    """Najde v rodokmenu taxonu nejvyssi zaznam s vyplnenym priznakem.

    Vraci klic pod kterym se taxon pocita - jmeno nejvyssiho zaznamu
    s priznakem, prevedene pres EKVIVALENTNI_SKUPINY. Diky tomu se dva
    druhy tehoz rodu zapocitaji jako jeden taxon (mihule, vranky, hrouzci).
    Pokud priznak nema nikdo v rodokmenu, vraci None.
    """
    nalezeno = None
    for taxon in taxonomicka_cesta(taxon_id, by_id):
        if je_priznak(by_id.get(taxon["ID"], {}).get(sloupec)):
            nalezeno = taxon["NAME"]
    if nalezeno is None:
        return None
    return EKVIVALENTNI_SKUPINY.get(nalezeno, nalezeno)


def _skupina(data, by_id, sloupec):
    """Vrati {klic_taxonu: soucet abundanci} pro dany priznak."""
    vysledek = {}
    for taxon_id, abundance in data.items():
        nositel = nositel_priznaku(taxon_id, sloupec, by_id)
        if nositel is None:
            continue
        vysledek[nositel] = vysledek.get(nositel, 0.0) + (abundance or 0.0)
    return vysledek


def spocitej_metriky(data, taxalist, typ):
    """Spocita hodnoty metrik TD, AR, ND1, ND2 a TA.

    Args:
        data: {taxon_id: abundance} po vyreseni synonym
        taxalist: vysledek nacti_taxalist pro `taxalist_ryby`
        typ: typ toku A-G

    Returns:
        dict s klici RY_TD, RY_AR, RY_ND1, RY_ND2, RY_TA a pomocnymi klici
        "_nezadouci" (nazev skupiny nezadoucich taxonu), "_typickych"
        a "_bez_priznaku" (taxony, ktere Tab. 4 metodiky nezna)
    """
    by_id = taxalist["by_id"]

    typicke = _skupina(data, by_id, typ)
    reofilni = _skupina(data, by_id, "R")
    celkem = sum(a or 0.0 for a in data.values())

    # nezadouci taxony: A-C eurytopni + limnofilni, D-G invazni
    sloupec_nezadouci = "EL" if typ in TYPY_S_EL else "I"
    nezadouci = _skupina(data, by_id, sloupec_nezadouci)
    nezadouci_abundance = sum(nezadouci.values())

    # TD - pocet typickych taxonu
    td = len(typicke)

    # AR - u typu A jen typicke taxony (vranka, pstruh, mihule),
    # u ostatnich typu vsechny reofilni taxony (metodika, kap. 3)
    ar = sum(typicke.values()) if typ == "A" else sum(reofilni.values())

    # ND1 - u typu A-C pocet nezadoucich taxonu,
    # u typu D-G pouha pritomnost (0 nebo 1)
    nd1 = len(nezadouci) if typ in TYPY_S_EL else (1 if nezadouci else 0)

    # ND2 - podil nezadoucich na celkove abundanci; prazdny vzorek resi
    # volajici modul (CZI = 0), zde jen zabranime deleni nulou
    nd2 = (nezadouci_abundance / celkem) if celkem > 0 else 0.0

    return {
        "RY_TD": float(td),
        "RY_AR": float(ar),
        "RY_ND1": float(nd1),
        "RY_ND2": float(nd2),
        "RY_TA": float(celkem),
        "_nezadouci": (
            "eurytopni a limnofilni" if typ in TYPY_S_EL else "invazni"
        ),
        "_typickych": sorted(typicke),
        "_bez_priznaku": bez_priznaku(data, by_id),
    }


def bez_priznaku(data, by_id):
    """Taxony vzorku, ktere nemaji ani jeden priznak R / EL / I.

    Takovy taxon do zadne metriky nevstoupi, ale do celkove abundance ano.
    Nebezpecne je to u ND1 a ND2: kdyz vzorek tvori druh, ktery Tab. 4
    metodiky nezna, vyjde "zadne nezadouci taxony" a obe metriky dostanou
    plny pocet bodu. Vzorek slozeny vyhradne z karase stribriteho zapsaneho
    pod starym jmenem `Carassius auratus` tak vychazel na CZI 0,25 misto 0.

    Duvody byvaji dva a je treba je rozlisit:

      * taxon je synonymum druhu z Tab. 4, ale v taxalistu mu chybi odkaz
        ve sloupci SYN - to je chyba v datech a da se opravit;
      * druh v Tab. 4 opravdu neni (napr. sumecek americky Ameiurus
        nebulosus nebo losos obecny Salmo salar) - metodika ho neskoruje.

    Returns:
        serazeny seznam jmen taxonu bez priznaku
    """
    nalezene = set()
    for taxon_id, abundance in data.items():
        if not abundance:
            continue
        if any(nositel_priznaku(taxon_id, s, by_id) for s in ("R", "EL", "I")):
            continue
        # nacti_taxalist() drzi jmeno pod klicem "name" (mala pismena);
        # "NAME" ma jen vysledek taxonomicka_cesta().
        info = by_id.get(taxon_id)
        if info and info.get("name"):
            nalezene.add(info["name"])
    return sorted(nalezene)


# ---------------------------------------------------------------------------
# Prevod na EQR
# ---------------------------------------------------------------------------

def transformuj(hodnota, predpis):
    """Aplikuje transformaci metriky.

    Predpis je jeden z:
        None            bez transformace
        "ln5"           ln(5x + 1)
        "ln10"          ln(10x + 1)
        "ln100"         ln(100x + 1)
        "ln1"           ln(x + 1)
    """
    if predpis is None:
        return hodnota
    nasobitel = {"ln5": 5.0, "ln10": 10.0, "ln100": 100.0, "ln1": 1.0}[predpis]
    return log(nasobitel * hodnota + 1.0)


def eqr(hodnota, mez, penalizujici, transformace=None):
    """Prevede hodnotu metriky na EQR.

    Metodika (kap. 3): dolni mez je u vsech metrik a typu toku nula, takze
    EQR je prosty pomer k horni mezi. Transformace se aplikuje na namerenou
    hodnotu I na mez.

    Args:
        hodnota: zjistena hodnota metriky
        mez: horni mez (max) z Tab. 3
        penalizujici: True u metrik, ktere stoupaji se zatizenim (ND1, ND2)
        transformace: predpis pro funkci transformuj()

    Returns:
        EQR v intervalu <0, 1>
    """
    if hodnota is None or mez is None or mez <= 0:
        return None

    # "Pokud zjistena hodnota metriky (X) presahuje horni mez (max),
    #  je hodnota X snizena na hodnotu max."
    hodnota = min(hodnota, mez)

    x = transformuj(hodnota, transformace)
    m = transformuj(mez, transformace)
    if m <= 0:
        return None

    podil = x / m
    return max(0.0, min(1.0, 1.0 - podil if penalizujici else podil))
