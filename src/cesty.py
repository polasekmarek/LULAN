"""
Jedno misto, kde se urcuje, kde lezi data aplikace.

Cestu k datum potrebuje pet modulu a kazdy si ji drive odvozoval sam
z `__file__`. To funguje pri behu ze zdrojaku, ale ne u zabalene
aplikace: `__file__` tam ukazuje dovnitr balicku PyInstalleru, ne vedle
spustitelneho souboru, takze odvozena cesta minula adresar s daty.

Kde data u zabalene verze lezi
------------------------------
PyInstaller 6 uklada pribalena data do podadresare `_internal` vedle
spustitelneho souboru, ne primo k nemu - starsi rady je davaly rovnou
vedle .exe. Presnou cestu hlasi `sys._MEIPASS`, ktery PyInstaller
nastavuje v obou pripadech (u --onefile miri do docasneho rozbaleneho
adresare). Rozhoduje proto `sys._MEIPASS`, a `v_korenu()` navic zkusi
i misto vedle .exe, aby na rozlozeni balicku vubec nezalezelo.

Odvozovat cestu jako `dirname(sys.executable)` byla chyba: v Program
Files pak program hledal `LULAN\\dtb\\LULAN_dtb_001.db`, zatimco soubor
lezel v `LULAN\\_internal\\dtb\\LULAN_dtb_001.db`. Databaze se proto
nenasla, nezkopirovala se do dat uzivatele a spusteni skoncilo hlaskou
"unable to open database file".
"""

from __future__ import annotations

import os
import sys


def je_zabalena():
    """Bezi aplikace ze zabaleneho spustitelneho souboru?"""
    return bool(getattr(sys, "frozen", False))


def _koren_zdrojaku():
    """Koren projektu pri behu ze zdrojaku (o uroven vys nez `src/`)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def vedle_programu():
    """Adresar se spustitelnym souborem.

    U zabalene verze adresar, do ktereho program nainstaloval
    instalator; pri behu ze zdrojaku koren projektu.
    """
    if je_zabalena():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _koren_zdrojaku()


def koren():
    """Adresar, ve kterem lezi data dodavana s aplikaci."""
    if je_zabalena():
        return getattr(sys, "_MEIPASS", None) or vedle_programu()
    return _koren_zdrojaku()


def v_korenu(*casti):
    """Cesta k dodavanemu souboru.

    Hleda nejdriv tam, kam data ulozil PyInstaller, a kdyz tam soubor
    neni, zkusi jeste vedle spustitelneho souboru. Ta druha moznost
    pokryva starsi rady PyInstalleru i pripad, kdy nekdo data vedle
    programu dolozi rucne. Kdyz soubor neni ani tam, vraci se prvni
    cesta - volajici si sam rozhodne, co s chybejicim souborem.
    """
    cesta = os.path.join(koren(), *casti)
    if os.path.exists(cesta):
        return cesta
    if je_zabalena():
        zaloha = os.path.join(vedle_programu(), *casti)
        if os.path.exists(zaloha):
            return zaloha
    return cesta
