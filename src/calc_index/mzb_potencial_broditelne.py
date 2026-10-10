"""
MZB - silne ovlivnene (HMWB) broditelne toky, ekologicky POTENCIAL.

Zdroj: Opatrilova L. a kol. (2013): Metoda pro hodnoceni ekologickeho
potencialu silne ovlivnenych a umelych vodnich utvaru - kategorie reka.

Postup vypoctu je shodny s hodnocenim stavu (mzb_perennial_broditelne.py) -
stejne typy lokalit, stejna sezonalita, stejne adjustace, stejne metriky
MB01-MB15 i stejne vahy. Lisi se pouze:

    * prevodni tabulka - horni meze metrik citlivych na hydromorfologii
      jsou snizene na uroven maximalniho ekologickeho potencialu
    * klasifikace - ctyri tridy misto peti, s ostrou nerovnosti

Modul proto pouziva spolecnou implementaci z mzb_perennial_broditelne.py
a jen ji preda jinou tabulku.
"""

from __future__ import annotations

from .mzb_perennial_broditelne import hodnoceni as _hodnoceni_spolecne
from .mzb_potencial_broditelne_table import EQR_TABLE


def hodnoceni(sample_id, db_connection, potencial=True):
    """Vypocte MZB hodnoceni ekologickeho potencialu silne ovlivneneho toku.

    Args:
        sample_id: ID vzorku
        db_connection: QSqlDatabase
        potencial: ponechano kvuli jednotnemu rozhrani; tento modul
            hodnoti vzdy potencial

    Returns:
        dict s hodnotami metrik, EQR, MZB_CELKEM, MZB_CLASS a MZB_POZN
    """
    return _hodnoceni_spolecne(
        sample_id,
        db_connection,
        potencial=True,
        tabulka=EQR_TABLE,
        popis="Ekologicky potencial (HMWB)",
    )
