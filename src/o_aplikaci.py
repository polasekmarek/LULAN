"""
Texty pro dialog "O aplikaci" - licence, zdroje dat, podekovani.

POZOR - k licencim
------------------
Licence programu a licence dat jsou dve ruzne veci a je potreba je
drzet oddelene:

* **Zdrojovy kod LULANu** je vlastni dilo a lze ho uvolnit pod MIT.
  Kod neni odvozenym dilem z GIS dat - jen je cte.
* **Data, ktera se s aplikaci sirí**, pod MIT dat nejdou. Odvozena
  ricni sit (`dtb/ricni_sit.db`) i zdrojove vrstvy v `src/GIS/` jsou
  odvozenymi dily z DIBAVOD, ZABAGED a rozvodnic CHMU a ridi se
  licencemi svych spravcu.

"""

from __future__ import annotations

import os

from cesty import v_korenu

#: Zaloha pro pripad, ze soubor VERZE chybi. Meni se jen spolu s nim.
VYCHOZI_VERZE = "1.0.1"


def _nacti_verzi():
    """Precte cislo verze ze souboru `VERZE` v korenu projektu.

    Verze se drive psala na pet mist - do tohoto modulu, do predpisu
    PyInstalleru, do instalatoru a do obou skriptu pro macOS a Linux.
    Nez se stihlo vydani, cast z nich uz nesouhlasila. Ted je jedinym
    zdrojem soubor `VERZE`; vsechno ostatni ho cte.
    """
    try:
        with open(v_korenu("VERZE"), encoding="utf-8") as f:
            verze = f.read().strip()
        return verze or VYCHOZI_VERZE
    except OSError:
        return VYCHOZI_VERZE


#: Verze aplikace.
VERZE = _nacti_verzi()

#: Rok pro copyright a pro citaci dat CUZK.
ROK = 2026

#: Drzitel autorskych prav ke zdrojovemu kodu.
#: TODO: doplnit presne zneni (jmeno autora / pracoviste).
AUTOR = "Masarykova univerzita, Výzkumný ústav vodohospodářský TGM, v.v.i."

NAZEV = "LULAN"
PODTITUL = (
    "Limnologický Univerzální Laboratorně-Analytický Nástroj <br>—<br> "
    "nástroj sloužící zejména k hodnocení ekologického stavu útvarů povrchových vod "
)

#: Text MIT licence. Sablona - `{rok}` a `{autor}` se doplnuji.
MIT = """MIT License

Copyright (c) {rok} {autor}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

#: Podekovani poskytovateli podpory.
#: TODO: doplnit cislo a nazev projektu.
PODEKOVANI = """
<p>Vývoj aplikace podpořila <b>Technologická agentura České republiky</b>
v rámci projektu <i>SS06010258 - Hodnocení ekologického stavu vysychavých toků podle biologických složek </i>.</p>

<p>Poděkování patří rovněž autorům metodik hodnocení ekologického stavu
a autorům taxonomických seznamů a autekologických charakteristik, bez
kterých by hodnocení nebylo možné sestavit.</p>
"""

#: Poznamka o vztahu licence kodu a licenci dat.
LICENCE_DAT_POZNAMKA = """
<p>Pod MIT licencí
je <b>zdrojový kód</b> aplikace. Data, se kterými aplikace pracuje, se
řídí licencemi svých správců a MIT licence se na ně nevztahuje.</p>

<p>Týká se to zejména <b>odvozené říční sítě</b> (<code>ricni_sit.db</code>)
a podkladových GIS vrstev — jde o odvozená díla z DIBAVOD, ZABAGED
a rozvodnic ČHMÚ. Data ČÚZK jsou pod CC BY 4.0</p>

<p>Rovněž metodiky hodnocení, taxonomické seznamy a autekologické
charakteristiky jsou autorskými díly třetích stran.</p>
"""

#: Metodiky, podle kterych aplikace pocita.
METODIKY = (
    ("Makrozoobentos", "OOV, aktualizace 2019; velké nebroditelné řeky "
                       "Němejcová a kol. 2019"),
    ("Fytobentos", "OOV, aktualizace 2019"),
    ("Fytoplankton", "OOV, aktualizace 2019"),
    ("Makrofyta", "OOV, aktualizace 2019"),
    ("Ryby", "Janáč a kol. 2019; ekologický potenciál 2024"),
    ("Jezera", "Borovec a kol. 2014"),
    ("Ekologický potenciál", "OOV 2014"),
)


def _tabulka_metodik():
    radky = "".join(
        f"<tr><td valign='top'><b>{slozka}</b></td>"
        f"<td valign='top'>{zdroj}</td></tr>"
        for slozka, zdroj in METODIKY
    )
    return f"<table cellpadding='4' cellspacing='0'>{radky}</table>"


def html():
    """Sestavi obsah dialogu "O aplikaci"."""
    try:
        from abiotic_params import popis_zdroju_html
        zdroje = popis_zdroju_html()
    except Exception:  # noqa: BLE001 - dialog musi jit otevrit vzdy
        zdroje = "<p><i>Přehled zdrojů dat se nepodařilo načíst.</i></p>"

    return f"""
<h2>{NAZEV} {VERZE}</h2>
<p>{PODTITUL}</p>

<h3>Licence programu</h3>
<pre style="white-space: pre-wrap; font-size: 11px;">{MIT.format(
    rok=ROK, autor=AUTOR)}</pre>

<h3>Data a jejich licence</h3>
{LICENCE_DAT_POZNAMKA}
{zdroje}

<h3>Metodiky</h3>
{_tabulka_metodik()}

<h3>Poděkování</h3>
{PODEKOVANI}
"""


def licence_txt():
    """Vrati text MIT licence pro soubor LICENSE."""
    return MIT.format(rok=ROK, autor=AUTOR) + "\n"
