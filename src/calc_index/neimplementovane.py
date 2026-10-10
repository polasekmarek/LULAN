"""
Zastupne moduly pro dosud neimplementovane kombinace slozek a typu utvaru.

Kazda funkce vraci dict se strukturou shodnou s implementovanymi moduly,
takze volajici kod (registry, runner, GUI) s nimi pracuje stejne. Az bude
prislusna metodika k dispozici, staci vytvorit samostatny modul po vzoru
mzb_perennial_broditelne.py a prepsat odkaz v registry.py.

U slozek, pro ktere uz je metodika ekologickeho potencialu k dispozici,
jsou nize poznamenane konkretni hodnoty, aby je nebylo nutne znovu
dohledavat (zdroj: Opatrilova a kol. 2013).
"""

from __future__ import annotations


def _todo(prefix, popis, potencial=False):
    return {
        f"{prefix}_CELKEM": None,
        f"{prefix}_CLASS": None,
        f"{prefix}_POZN": f"{popis} zatim neni implementovano",
        f"{prefix}_TYP_HODNOCENI": "POTENCIAL" if potencial else "STAV",
    }


# Vsechny drive zastupne funkce uz maji vlastni modul:
#
#   fp_reka.py        fytoplankton toku
#   mf_reka.py        makrofyta toku
#   ryby_reka.py      ryby toku - ekologicky stav
#   ryby_potencial.py ryby toku - ekologicky potencial
#   jezera_runner.py  fytoplankton, makrofyta a ryby stojatych vod
#
# Modul zustava kvuli funkci _todo(), kterou pouziji dalsi metodiky,
# az na ne prijde rada (napr. makrozoobentos nebroditelnych toku - stav).
