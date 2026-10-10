# -*- mode: python ; coding: utf-8 -*-
"""
Predpis pro PyInstaller - zabaleni LULANu do jednoho adresare.

Spousti se z korene projektu:

    pyinstaller build/lulan.spec --noconfirm

Vysledkem je `dist/LULAN/` se spustitelnym souborem a vsim, co potrebuje.
Na macOS vznikne navic `dist/LULAN.app`.

Jeden predpis pro tri systemy
-----------------------------
PyInstaller neumi sestavit pro jinou platformu, nez na ktere bezi, takze
se pousti na kazdem systemu zvlast - seznam dat a skrytych importu ale
zustava spolecny, aby se neudrzoval trikrat. Co se lisi, resi vetveni
u definice EXE nize.

Hotovy adresar pak prebira baleni te ktere platformy:

    Windows   build/lulan.iss        Inno Setup -> instalator .exe
    macOS     build/sestavit_mac.sh  .app -> obraz .dmg
    Linux     build/sestavit_linux.sh   -> balicek .deb

Proc adresar a ne jeden soubor
------------------------------
Volba `--onefile` slepi vse do jedineho .exe, ktere se pri kazdem
spusteni rozbali do docasneho adresare. U LULANu by to znamenalo
rozbalovat 90 MB dat pri kazdem startu - a hlavne by antiviry takove
chovani hlasily jako podezrele. Adresarova podoba startuje okamzite
a instalator si s ni poradi lip.
"""

import os
import re
import sys

# PyInstaller spousti spec s promennou SPECPATH; koren je o uroven vys.
KOREN = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # noqa: F821


def data(zdroj, cil):
    """Dvojice (cesta na disku, cilovy adresar v balicku)."""
    return (os.path.join(KOREN, zdroj), cil)


#: Soubory, ktere aplikace cte za behu. Kdyz nektery chybi, PyInstaller
#: to mlcky preskoci - proto je kontrola v `sestavit.bat`.
DATA = [
    data("dtb/LULAN_dtb_001.db", "dtb"),
    data("dtb/ricni_sit.db", "dtb"),
    data("dtb/ciselnik_traits.csv", "dtb"),
    data("dtb/hodnoceni_zkratky.csv", "dtb"),
    data("img/LULAN_icon.ico", "img"),
    data("img/LULAN_icon.png", "img"),
    data("img/filtr_ikona.png", "img"),
    data("img/filtr_ikona@2x.png", "img"),
    data("LICENSE", "."),
    # Cislo verze cte za behu `o_aplikaci`; bez nej by dialog O aplikaci
    # ukazoval zalozni hodnotu zapsanou v kodu.
    data("VERZE", "."),
]

# Vrstvy pro mapku. Shapefile je vzdy nekolik souboru se stejnym zakladem.
for zaklad in ("hrcr_S42", "hlavni_toky_S42"):
    for pripona in (".shp", ".shx", ".dbf", ".prj"):
        cesta = os.path.join(KOREN, "src", "GIS", zaklad + pripona)
        if os.path.exists(cesta):
            DATA.append((cesta, os.path.join("src", "GIS")))

#: Moduly, ktere se importuji az za behu, takze je PyInstaller sam
#: nenajde - vyber vypocetni metody se dela podle obsahu databaze.
#: Importy schovane uvnitr funkci projde staticka analyza mlcky, takze
#: chybejici modul se projevi az za behu, a nekdy jen tim, ze se ticho
#: preskoci vypocet - proto se sem vypisuji vsechny.
SKRYTE_IMPORTY = [
    "calc_index.registry",
    "calc_index.runner",
    "calc_index.jezera_runner",
    "editor_vzorku",
    "uloziste",
    "ciselnik_traits",
    "ciselnik_metrik",
    "csv_ciselnik",
    "radek_filtru",
    "export_csv",
    "import_csv",
    "o_aplikaci",
    "mapa_lokalit",
    "calc_indexes",
    "abiotic_params",
    "ricni_sit",
    "sirky_sloupcu",
    # B-index si mzb_metrics natahuje az ve chvili vypoctu, a to uvnitr
    # try/except - bez tohoto radku by metrika v zabalene verzi mlcky
    # vracela None.
    "B_index2",
    # pyproj se importuje take az ve funkci. Krome kodu s sebou nese
    # databazi souradnicovych systemu (proj.db), kterou pribali hook
    # PyInstalleru - ten se ale spusti jen tehdy, kdyz o baliku vi.
    "pyproj",
]

#: Baliky, ktere se do vysledku pribalit nemaji. Geopandas a shapely
#: pouziva jen generator ricni site v `_tools/`, ne aplikace - a pridaly
#: by pres 200 MB. Zbytek jsou vyvojove nastroje a jina GUI Qt.
VYNECHAT = [
    "geopandas", "shapely", "fiona", "matplotlib", "openpyxl",
    "IPython", "jupyter", "notebook", "pytest", "setuptools",
    "tkinter", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth",
    "PyQt6.QtMultimedia", "PyQt6.QtDesigner", "PyQt6.QtHelp",
]

# ---------------------------------------------------------------------
#  Rozdily mezi platformami
# ---------------------------------------------------------------------
#  Jeden spec pro vsechny tri systemy. PyInstaller neumi sestavit pro
#  jinou platformu, nez na ktere bezi, takze se spousti na kazdem zvlast
#  - ale predpis muze zustat spolecny, aby se seznam dat a skrytych
#  importu neudrzoval trikrat.
#
#  Lisi se tri veci:
#    ikona    Windows chce .ico, macOS .icns, Linux ikonu v programu
#             vubec nepouziva (bere ji ze souboru .desktop)
#    verze    zdroj VERSIONINFO je vylucne windowsova zalezitost
#    obal     na macOS se z vysledku jeste sklada .app

def _verze():
    """Cislo verze ze souboru VERZE v korenu projektu."""
    try:
        with open(os.path.join(KOREN, "VERZE"), encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        print("Varovani: soubor VERZE chybi, pouzivam 0.0.0")
        return "0.0.0"


VERZE = _verze()


def _versioninfo():
    """Vyrobi popis verze pro Windows s aktualnim cislem.

    Predloha `build/verze.txt` nese texty (nazev, vydavatel, copyright);
    cisla verze se do ni doplni odsud, aby se nemusela udrzovat dvakrat.
    Windows chtejí ctverici cisel, proto se doplnuje nula.
    """
    predloha = os.path.join(SPECPATH, "verze.txt")  # noqa: F821
    if not os.path.exists(predloha):
        return None

    cisla = (VERZE.split(".") + ["0", "0", "0", "0"])[:4]
    ctverice = ", ".join(cisla)
    tecky = ".".join(cisla)

    with open(predloha, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"filevers=\([^)]*\)", f"filevers=({ctverice})", text)
    text = re.sub(r"prodvers=\([^)]*\)", f"prodvers=({ctverice})", text)
    text = re.sub(r'(StringStruct\("(?:File|Product)Version", ")[^"]*"',
                  rf'\g<1>{tecky}"', text)

    vystup = os.path.join(SPECPATH, "verze_generovano.txt")  # noqa: F821
    with open(vystup, "w", encoding="utf-8") as f:
        f.write(text)
    return vystup


if sys.platform == "win32":
    IKONA = os.path.join(KOREN, "img", "LULAN_icon.ico")
    VERZE_SOUBOR = _versioninfo()
elif sys.platform == "darwin":
    IKONA = os.path.join(KOREN, "img", "LULAN_icon.icns")
    VERZE_SOUBOR = None
else:
    IKONA = None
    VERZE_SOUBOR = None

# Chybejici ikona neni duvod sestaveni zastavit - jen bude vypadat hure.
if IKONA and not os.path.exists(IKONA):
    print(f"Varovani: ikona {IKONA} neexistuje, pokracuji bez ni.")
    IKONA = None

a = Analysis(  # noqa: F821
    [os.path.join(KOREN, "src", "main_app_deploy.py")],
    pathex=[os.path.join(KOREN, "src")],
    binaries=[],
    datas=DATA,
    hiddenimports=SKRYTE_IMPORTY,
    hookspath=[],
    runtime_hooks=[],
    excludes=VYNECHAT,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LULAN",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX komprese casto spousti plane poplachy antiviru
    console=False,      # okenni aplikace, konzole se neotevira
    icon=IKONA,
    version=VERZE_SOUBOR,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LULAN",
)

if sys.platform == "darwin":
    # Z adresare se jeste udela .app, aby slo s programem zachazet jako
    # s kazdou jinou macOS aplikaci - pretahnout do Aplikaci, spustit
    # z Launchpadu, mit vlastni ikonu.
    app = BUNDLE(  # noqa: F821
        coll,
        name="LULAN.app",
        icon=IKONA,
        # Stejny identifikator jako AppUserModelID na Windows. Podle nej
        # si system pamatuje nastaveni okna a prava aplikace.
        bundle_identifier="cz.muni.lulan",
        version=VERZE,
        info_plist={
            "CFBundleName": "LULAN",
            "CFBundleDisplayName": "LULAN",
            "CFBundleShortVersionString": VERZE,
            "CFBundleVersion": VERZE,
            # Bez tohohle by macOS aplikaci vykresloval ve dvojnasobnych
            # pixelech a na Retine by byla rozmazana.
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright":
                "© Masarykova univerzita, licence MIT",
        },
    )
