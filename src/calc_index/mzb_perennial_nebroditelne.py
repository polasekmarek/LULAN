"""
MZB - staletekouci (perennial) nebroditelne toky (velke reky).

NEIMPLEMENTOVANO. Metodika pro nebroditelne toky se lisi od broditelnych
zpusobem odberu i sadou metrik - misto MB01-MB15 pouziva metriky REKO MEPT,
Margaleuv index, ricni zonaci epipotamal, EPT Abu, saprobni index a
SPEAR organic (Nemejcova a kol., 2013). Hodnoceni se provadi na letnich
vzorcich.

Az bude metodika hodnoceni STAVU k dispozici, doplni se sem vypocet metrik
a prevodni tabulka; tabulka pro ekologicky POTENCIAL je uz znama a je
prepsana nize (POTENCIAL_MEZE).
"""

from __future__ import annotations

TODO_POZNAMKA = "MZB hodnoceni nebroditelnych toku zatim neni implementovano"

#: Prevodni meze pro ekologicky POTENCIAL velkych nebroditelnych rek.
#:
#: Zdroj: Opatrilova a kol. (2013), Tab. 5 - hodnoceni letnich vzorku.
#: Format {metrika: (dolni_mez, horni_mez, invertovat, vaha)}.
#: Vahy vsech metrik jsou podle metodiky rovny 1.
#: Tridy potencialu dle Tab. 8 (viz common.HRANICE_POTENCIAL).
POTENCIAL_MEZE = {
    "REKO_MEPT": (0.0, 0.4, False, 1.0),      # REKOnstruovane taxocenozy MEPT
    "DIV_MARG": (0.4, 11.0, False, 1.0),      # Margalefuv index diverzity
    "ZEPOTA": (8.6, 34.5, False, 1.0),        # ricni zonace: epipotamal [%]
    "EPT_ABU": (0.0, 32.0, False, 1.0),       # % abundanci EPT taxonu
    "SAPR_INDEX": (1.7, 3.5, True, 1.0),      # saprobni index
    "SPEAR_ORG": (-1.23, -0.07, False, 1.0),  # SPEAR organic
}


def hodnoceni(sample_id, db_connection, potencial=False):
    """Zastupna implementace - vraci pouze informaci o neimplementovanosti."""
    return {
        "MZB_CELKEM": None,
        "MZB_CLASS": None,
        "MZB_POZN": TODO_POZNAMKA,
        "MZB_TYP_HODNOCENI": "POTENCIAL" if potencial else "STAV",
    }
