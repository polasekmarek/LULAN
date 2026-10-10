"""
Vymezeni velkych nebroditelnych rek (VR).

Metodika pro velke nebroditelne reky se NEUPLATNUJE na vsechny toky
7.-9. radu, ale pouze na vyjmenovane vodni utvary. Seznam je prevzaty
z tabulek 2 a 3 metodiky:

    Nemejcova D. a kol. (2019): Metodika hodnoceni biologicke slozky
    benticti bezobratli pro velke nebroditelne reky. VUV TGM.
    metodiky/OOV-metodika_MZB_VR_aktualizace-20191014.pdf

Prislusnost k umori je pro tuto metodiku podstatna: index REKOnstruovanych
taxocenoz MEPT se pocita proti jinemu seznamu ocekavanych taxonu pro povodi
Labe (sloupec TAXONY_MEPT_VLT v tabulce taxalist_mzb) a pro povodi Moravy
(sloupec TAXONY_MEPT_MO).

Rozhodovani podle tohoto seznamu je zamerne prisnejsi nez spolehani se na
sloupec utvary.BROD - pri chybnem importu by se jinak tise pouzila
nespravna metodika. Funkce zkontroluj_soulad() oba zdroje porovna.
"""

from __future__ import annotations

from PyQt6.QtSql import QSqlQuery

#: Nebroditelne vodni utvary typu 12_3 v umori Severniho more (povodi Labe).
#: Metodika, Tab. 2. Pro index REKO se pouziva sloupec TAXONY_MEPT_VLT.
UTVARY_LABE = {
    "HSL_0930": "Labe od Orlice po tok Chrudimka",
    "HSL_1180": "Labe od toku Chrudimka po tok Doubrava",
    "HSL_1320": "Labe od toku Doubrava po tok Polepka (Chotouchovsky potok) vcetne",
    "HSL_1340": "Labe od toku Polepka (Chotouchovsky potok) po tok Cidlina",
    "HSL_1480": "Labe od toku Cidlina po tok Mrlina",
    "HSL_1680": "Labe od toku Mrlina po tok Jizera",
    "HSL_2090": "Labe od toku Jizera po tok Vltava",
    "OHL_0030": "Labe od toku Vltava po tok Ohre",
    "OHL_0750": "Labe od toku Ohre po tok Bilina",
    "OHL_0940": "Labe od toku Bilina po Jilovsky potok",
    "OHL_1150": "Labe od toku Jilovsky potok po statni hranici",
    "DVL_0030": "Vltava od hraze nadrze Orlik po vzduti nadrze Slapy",
    "DVL_0110": "Vltava od hraze nadrze Slapy po tok Sazava",
    "DVL_0730": "Vltava od toku Sazava po tok Berounka",
    "DVL_0820": "Vltava od toku Berounka po usti do Labe",
    "DVL_0830": "Vranansko-horinsky plavebni kanal",
}

#: Nebroditelne vodni utvary typu 12_3 v umori Stredozemniho more (povodi Moravy).
#: Metodika, Tab. 3. Pro index REKO se pouziva sloupec TAXONY_MEPT_MO.
UTVARY_MORAVA = {
    "DYJ_1240": "Dyje od hraze nadrze Nove Mlyny III. po tok Odlehcovaci rameno Dyje",
    "DYJ_1260": "Dyje od toku Odlehcovaci rameno Dyje po tok Kyjovka (Stupava)",
    "DYJ_1300": "Dyje od toku Kyjovka (Stupava) po tok Morava",
    "MOV_0950": "Morava od toku Becva po tok Hana",
    "MOV_1170": "Morava od toku Hana po tok Drevnice",
    "MOV_1290": "Morava od toku Drevnice po tok Olsava",
    "MOV_1390": "Morava od toku Olsava po tok Radejovka",
    "MOV_1430": "Morava od toku Radejovka po statni hranici",
}

#: Nazev sloupce v taxalist_mzb se seznamem ocekavanych taxonu MEPT.
SLOUPEC_REKO = {
    "LABE": "TAXONY_MEPT_VLT",
    "MORAVA": "TAXONY_MEPT_MO",
}

#: Vsechny utvary, na ktere se metodika VR vztahuje.
VSECHNY_UTVARY = {**UTVARY_LABE, **UTVARY_MORAVA}


def je_velka_reka(id_utvaru):
    """True, pokud vodni utvar spada pod metodiku velkych nebroditelnych rek."""
    return id_utvaru in VSECHNY_UTVARY


def povodi(id_utvaru):
    """Vrati 'LABE' nebo 'MORAVA' podle umori, nebo None."""
    if id_utvaru in UTVARY_LABE:
        return "LABE"
    if id_utvaru in UTVARY_MORAVA:
        return "MORAVA"
    return None


def utvar_vzorku(sample_id, db_connection):
    """Zjisti ID vodniho utvaru, do ktereho vzorek patri."""
    query = QSqlQuery(db_connection)
    query.prepare(
        "SELECT l.VU FROM samples s JOIN loc l ON s.LOC_ID = l.KOD "
        "WHERE s.SAMPLE_ID = ?"
    )
    query.addBindValue(sample_id)
    if query.exec() and query.next():
        return query.value(0)
    return None


def zkontroluj_soulad(db_connection):
    """Porovna seznam z metodiky se sloupcem utvary.BROD v databazi.

    Returns:
        dict {'chybi_nebrod': [...], 'navic_nebrod': [...], 'neznam e': [...]}
        chybi_nebrod  - utvar je v metodice, ale v DB nema BROD='NEBROD'
        navic_nebrod  - utvar ma v DB BROD='NEBROD', ale v metodice neni
        nezname       - utvar z metodiky v databazi vubec neni
    """
    query = QSqlQuery(db_connection)
    v_databazi, nebrod = set(), set()
    if query.exec("SELECT ID_UTVARU, BROD FROM utvary"):
        while query.next():
            v_databazi.add(query.value(0))
            if query.value(1) == "NEBROD":
                nebrod.add(query.value(0))

    metodika = set(VSECHNY_UTVARY)
    return {
        "chybi_nebrod": sorted((metodika & v_databazi) - nebrod),
        "navic_nebrod": sorted(nebrod - metodika),
        "nezname": sorted(metodika - v_databazi),
    }


def popis_nesouladu(rozdily):
    """Prevede vysledek zkontroluj_soulad() na citelnou zpravu, nebo None."""
    if not any(rozdily.values()):
        return None

    radky = []
    if rozdily["chybi_nebrod"]:
        radky.append(
            "Útvary vyjmenované v metodice velkých řek, které v databázi "
            "nemají BROD='NEBROD':\n  " + ", ".join(rozdily["chybi_nebrod"])
        )
    if rozdily["navic_nebrod"]:
        radky.append(
            "Útvary označené v databázi jako NEBROD, které metodika "
            "velkých řek nevyjmenovává:\n  " + ", ".join(rozdily["navic_nebrod"])
        )
    if rozdily["nezname"]:
        radky.append(
            "Útvary z metodiky, které v databázi nejsou:\n  "
            + ", ".join(rozdily["nezname"])
        )
    return "\n\n".join(radky)
