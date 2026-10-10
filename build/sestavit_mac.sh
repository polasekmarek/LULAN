#!/usr/bin/env bash
# ===================================================================
#  Sestaveni LULANu pro macOS.
#
#  Spoustet z korene projektu:   build/sestavit_mac.sh
#
#  Vysledek:
#    dist/LULAN.app                 aplikace
#    build/vystup/LULAN-1.0.0.dmg   obraz k rozeslani
#
#  Predpoklady:
#    - Python 3.11 nebo novejsi
#    - virtualni prostredi .venv s balicky z requirements.txt
#    - PyInstaller  (pip install pyinstaller)
#
#  Aplikace neni podepsana, takze ji Gatekeeper pri prvnim spusteni
#  zablokuje. Jak s tim nalozit, popisuje PODPIS.md.
# ===================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
KOREN="$PWD"

# Cislo verze ma jedine misto - soubor VERZE v korenu projektu. Cte ho
# i predpis PyInstalleru a instalator pro Windows.
VERZE="$(tr -d '[:space:]' < VERZE 2>/dev/null)"
if [[ -z "$VERZE" ]]; then
    echo "Soubor VERZE chybi nebo je prazdny." >&2
    exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Tenhle skript patri na macOS. Pro Linux je build/sestavit_linux.sh," >&2
    echo "pro Windows build\\sestavit.bat." >&2
    exit 1
fi

echo
echo "=== 1. Kontrola souboru, ktere aplikace potrebuje ==="

CHYBI=0
overit() {
    if [[ -e "$1" ]]; then
        echo "  OK    $1"
    else
        echo "  CHYBI $1"
        CHYBI=$((CHYBI + 1))
    fi
}

overit "dtb/LULAN_dtb_001.db"
overit "dtb/ricni_sit.db"
overit "dtb/ciselnik_traits.csv"
overit "dtb/hodnoceni_zkratky.csv"
overit "img/filtr_ikona.png"
overit "img/filtr_ikona@2x.png"
overit "src/GIS/hrcr_S42.shp"
overit "src/GIS/hlavni_toky_S42.shp"
overit "LICENSE"
overit "VERZE"

if [[ "$CHYBI" -ne 0 ]]; then
    echo
    echo "Chybi $CHYBI souboru. Bez nich se cast programu nespusti spravne."
    echo "Podrobnosti jsou v UKLID.md, kapitola 1."
    read -r -p "Pokracovat presto? [a/N] " odpoved
    [[ "$odpoved" == "a" || "$odpoved" == "A" ]] || exit 1
fi

echo
echo "=== 2. Virtualni prostredi ==="
if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "Aktivovano .venv"
else
    echo ".venv nenalezeno, pouziva se systemovy Python."
fi

python3 -c "import PyInstaller" 2>/dev/null || {
    echo "PyInstaller neni nainstalovan. Instaluji..."
    python3 -m pip install pyinstaller
}

echo
echo "=== 3. Ikona aplikace ==="
# .icns nese vic velikosti najednou; kdyz chybi nebo je starsi nez
# zdrojovy obrazek, vyrobi se znovu.
if [[ ! -f "img/LULAN_icon.icns" || "img/LULAN_icon.png" -nt "img/LULAN_icon.icns" ]]; then
    python3 _tools/vyrob_icns.py || {
        echo "Ikonu se nepodarilo vyrobit, pokracuji bez ni."
    }
else
    echo "img/LULAN_icon.icns je aktualni"
fi

echo
echo "=== 4. Sestaveni aplikace ==="
rm -rf dist/LULAN dist/LULAN.app build/LULAN
pyinstaller build/lulan.spec --noconfirm --distpath dist --workpath build/prace

if [[ ! -d "dist/LULAN.app" ]]; then
    echo
    echo "LULAN.app nevznikl - neco je spatne." >&2
    exit 1
fi
echo "Hotovo: dist/LULAN.app"

echo
echo "=== 5. Podpis ==="
# Proc se podepisuje, i kdyz zadny certifikat nemame:
#
# Novejsi macOS (Sequoia a dal) uplne nepodepsanou aplikaci nespusti
# a ani ji nenabidne v Nastaveni v sekci Soukromi a zabezpeceni - tam
# se objevi jen aplikace podepsana, byt nenotarizovana. Takzvany
# ad-hoc podpis ("-") zadny certifikat nevyzaduje a presne tuhle mezeru
# zaplni: uzivatel dostane tlacitko Presto otevrit misto hluche zdi.
#
# Az certifikat bude, staci pred spustenim skriptu nastavit:
#     export LULAN_PODPIS="Developer ID Application: Jmeno (TEAMID)"
# Notarizace je pak jeste dalsi krok navic, viz PODPIS.md.
PODPIS="${LULAN_PODPIS:--}"

if [[ "$PODPIS" == "-" ]]; then
    echo "Podepisuji ad-hoc (bez certifikatu)."
else
    echo "Podepisuji certifikatem: $PODPIS"
fi

# --deep je u aplikaci s vlastnim behovym prostredim nutnost: uvnitr je
# nekolik set knihoven Qt a Pythonu a kazda musi mit podpis taky.
codesign --force --deep --sign "$PODPIS" \
         --options runtime --timestamp=none \
         "dist/LULAN.app" 2>/dev/null \
    || codesign --force --deep --sign "$PODPIS" "dist/LULAN.app"

if codesign --verify --deep --strict "dist/LULAN.app" 2>/dev/null; then
    echo "Podpis ověřen."
else
    echo "Varovani: podpis se nepodarilo overit; aplikace pujde spustit" >&2
    echo "jen po rucnim odstraneni karanteny (viz PODPIS.md)." >&2
fi

echo
echo "=== 6. Obraz disku (.dmg) ==="
# DMG je na macOS obvykla podoba instalace: uzivatel ho otevre a aplikaci
# pretahne do slozky Aplikace. Odkaz na ni se do obrazu prida, aby bylo
# na prvni pohled zrejme, co se ceka.
mkdir -p build/vystup
DMG="build/vystup/LULAN-${VERZE}.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "dist/LULAN.app" "$STAGE/"
ln -s /Applications "$STAGE/Aplikace"
cp LICENSE "$STAGE/LICENCE.txt" 2>/dev/null || true

rm -f "$DMG"
hdiutil create \
    -volname "LULAN ${VERZE}" \
    -srcfolder "$STAGE" \
    -ov -format UDZO \
    "$DMG" >/dev/null

echo "Hotovo: $DMG"

echo
echo "=== Sestaveni dokonceno ==="
du -sh dist/LULAN.app "$DMG" | sed 's/^/  /'
echo
if [[ "$PODPIS" == "-" ]]; then
    echo "Aplikace je podepsana jen ad-hoc, tedy bez overeni u Applu."
    echo "Pri prvnim spusteni ji macOS zablokuje; uzivatel ji povoli"
    echo "v Nastaveni > Soukromi a zabezpeceni. Podrobnosti v PODPIS.md."
else
    echo "Aplikace je podepsana certifikatem. Aby se spustila uplne bez"
    echo "varovani, je potreba ji jeste notarizovat - viz PODPIS.md."
fi
