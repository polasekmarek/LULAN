"""
Cteni ciselniku ulozenych jako CSV.

Ciselniky v `dtb/` pripravuje zadavatel v Excelu, takze prichazeji
v ruznych kodovanich - macOS Excel uklada `mac_latin2`, windowsovy
`cp1250`. Spatne uhodnute kodovani nezpusobi chybu, jen rozsypany
text, proto se zkousi vic moznosti a vybira se ta, ktera da nejmene
cizich znaku.

Modul vznikl vyclenenim z `ciselnik_traits`, kdyz pribyl druhy ciselnik
(zkratky metrik). Slo o tentyz kod dvakrat, a hlavne o tentyz pozadavek:
cist soubor, kteremu nikdo nerekl, v jakem je kodovani.
"""

from __future__ import annotations

import csv
import io
import os

#: Kodovani, ktera se zkousi, v poradi podle pravdepodobnosti.
KODOVANI = ("utf-8-sig", "mac_latin2", "cp1250", "iso-8859-2")

#: Znaky, ktere se v ciselnicich legitimne vyskytuji. Slouzi k rozpoznani
#: spatne uhodnuteho kodovani: spravne dekodovany text se do teto sady
#: skoro cely vejde, spatne dekodovany nadela stovky cizich znaku.
#:
#: Puvodne se to delalo obracene - vyjmenovanim "podezrelych" znaku -
#: ale takovy seznam je vzdy neuplny. Napriklad iso-8859-2 rozsypalo
#: text na znaky, ktere v nem nebyly, dostalo skore 0 a vyhralo.
POVOLENE = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
    "0123456789"
    " ;,.:-()/=+_%°'\"\n\r\t"
)


def precti(cesta):
    """Nacte soubor a vrati text v tom kodovani, ktere dava nejlepsi smysl.

    Returns:
        text souboru, nebo None kdyz se nepodarilo dekodovat zadnym
        ze zkousenych kodovani
    """
    with open(cesta, "rb") as f:
        data = f.read()

    nejlepsi, nejmene = None, None
    for kodovani in KODOVANI:
        try:
            text = data.decode(kodovani)
        except UnicodeDecodeError:
            continue
        skore = sum(1 for z in text if z not in POVOLENE)
        if nejmene is None or skore < nejmene:
            nejlepsi, nejmene = text, skore
        if skore == 0:
            break
    return nejlepsi


def radky(cesta, oddelovac=";"):
    """Nacte CSV jako seznam slovniku.

    Returns:
        list dictu podle hlavicky; prazdny seznam, kdyz soubor chybi
        nebo ho nelze precist
    """
    if not cesta or not os.path.exists(cesta):
        return []
    text = precti(cesta)
    if text is None:
        return []
    return list(csv.DictReader(io.StringIO(text), delimiter=oddelovac))
