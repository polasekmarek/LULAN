"""
Verejne rozhrani pro vypocet indexu ekologickeho stavu.

Vlastni vypocet je rozdelen do balicku `calc_index/` - kazda kombinace
biologicke slozky a typu utvaru ma tam vlastni modul s vlastni prevodni
tabulkou. Tento soubor zustava zachovan jako vstupni bod, aby zbytek
aplikace (main_app_deploy.py) nemusel menit importy.

Pouziti:
    from calc_indexes import run_index_calculation, get_yearly_results_summary

Puvodni monoliticka verze je ulozena v _archiv/src/calc_indexes_puvodni.py.
Prehled zmen a opravenych chyb najdete v OPRAVY.md.
"""

from calc_index import (
    aggregate_results_to_year,
    calc_indexes,
    get_yearly_results_summary,
    run_index_calculation,
    vlastnosti_utvaru,
    vyber_funkci,
)

# Zpetne kompatibilni aliasy k puvodnim nazvum funkci
get_utvar_properties = vlastnosti_utvaru
select_hodnoceni_function = vyber_funkci

__all__ = [
    "aggregate_results_to_year",
    "calc_indexes",
    "get_yearly_results_summary",
    "run_index_calculation",
    "get_utvar_properties",
    "select_hodnoceni_function",
]
