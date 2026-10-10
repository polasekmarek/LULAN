"""
Vypocet indexu ekologickeho stavu / potencialu vodnich utvaru.

Balicek je rozdelen podle kombinaci (biologicka slozka x typ utvaru).
Kazda kombinace ma vlastni modul s vlastni prevodni tabulkou:

    mzb_perennial_broditelne.py     MZB, staletekouci broditelne toky
    mzb_perennial_nebroditelne.py   MZB, staletekouci nebroditelne toky
    mzb_intermittent.py             MZB, vysychave toky
    fb_perennial.py                 fytobentos, staletekouci toky
    fb_intermittent.py              fytobentos, vysychave toky
    mf_reka.py                      makrofyta, toky
    neimplementovane.py             zastupne funkce pro zbytek

Sdilene stavebni kameny:

    common.py       nacitani dat, taxonomie, adjustace, EQR engine, klasifikace
    mzb_metrics.py  vypocet metrik MB01-MB16
    registry.py     rozrazeni vzorku na spravnou metodiku
    runner.py       spousteni vypoctu, agregace do rocnich vysledku

Verejne API pouzivane aplikaci je reexportovano nize a zaroven zustava
dostupne pres puvodni modul calc_indexes.py.
"""

from .runner import (
    aggregate_results_to_year,
    calc_indexes,
    get_yearly_results_summary,
    run_index_calculation,
)
from .registry import vlastnosti_utvaru, vyber_funkci

__all__ = [
    "aggregate_results_to_year",
    "calc_indexes",
    "get_yearly_results_summary",
    "run_index_calculation",
    "vlastnosti_utvaru",
    "vyber_funkci",
]
