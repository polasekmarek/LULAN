#!/usr/bin/env bash
# ===================================================================
#  Sestaveni LULANu pro Linux a vyroba balicku .deb.
#
#  Spoustet z korene projektu:   build/sestavit_linux.sh
#
#  Vysledek:
#    dist/LULAN/LULAN                       program se vsim, co potrebuje
#    build/vystup/lulan_1.0.0_amd64.deb     balicek k instalaci
#
#  Predpoklady:
#    - Python 3.11 nebo novejsi
#    - virtualni prostredi .venv s balicky z requirements.txt
#    - PyInstaller  (pip install pyinstaller)
#    - dpkg-deb (balicek dpkg-dev), na Ubuntu/Debianu byva uz nainstalovany
#
#  Kam se co instaluje
#  -------------------
#  Program i predloha databaze   /opt/lulan              jen ke cteni
#  Spoustec                      /usr/bin/lulan          odkaz
#  Polozka v nabidce             /usr/share/applications
#  Data uzivatele                ~/.local/share/LULAN    sem si program
#                                predlohu zkopiruje pri prvnim spusteni
#
#  Do /opt bezny uzivatel zapisovat nesmi, takze databaze tam zustat
#  nemuze. Program si ji proto pri prvnim spusteni prenese k sobe -
#  a odinstalace se jich nedotkne, takze o vlozene vzorky nikdo neprijde.
#
#  Proc balicek nese i Python a Qt
#  -------------------------------
#  Varianta zavisla na systemovem python3-pyqt6 by byla o rad mensi, ale
#  fungovala by jen tam, kde ma distribuce dost novou verzi. Takhle je
#  balicek vetsi (kolem 150 MB), zato se chova stejne na Ubuntu i Debianu
#  a nema zadne zavislosti krome systemovych knihoven.
# ===================================================================
set -euo pipefail

BALICEK="lulan"
cd "$(dirname "$0")/.."

# Cislo verze ma jedine misto - soubor VERZE v korenu projektu. Cte ho
# i predpis PyInstalleru a instalator pro Windows.
VERZE="$(tr -d '[:space:]' < VERZE 2>/dev/null)"
if [[ -z "$VERZE" ]]; then
    echo "Soubor VERZE chybi nebo je prazdny." >&2
    exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "Tenhle skript patri na Linux. Pro macOS je build/sestavit_mac.sh," >&2
    echo "pro Windows build\\sestavit.bat." >&2
    exit 1
fi

# Architektura v nazvoslovi Debianu: x86_64 se tam jmenuje amd64,
# aarch64 zase arm64.
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"

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
overit "img/LULAN_icon.png"
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
echo "=== 3. Sestaveni programu ==="
# Kdyz uz program sestaveny je a meni se jen baleni, da se krok preskocit:
#     LULAN_JEN_BALICEK=1 build/sestavit_linux.sh
# Obdoba windowsoveho build\instalator.bat.
if [[ "${LULAN_JEN_BALICEK:-}" == "1" ]]; then
    echo "Preskoceno (LULAN_JEN_BALICEK=1), pouziva se dist/LULAN/"
else
    rm -rf dist/LULAN build/LULAN
    pyinstaller build/lulan.spec --noconfirm --distpath dist --workpath build/prace
fi

if [[ ! -x "dist/LULAN/LULAN" ]]; then
    echo
    echo "Spustitelny soubor nevznikl - neco je spatne." >&2
    exit 1
fi
echo "Hotovo: dist/LULAN/LULAN"

echo
echo "=== 4. Balicek .deb ==="

if ! command -v dpkg-deb >/dev/null; then
    echo "Chybi dpkg-deb. Nainstalujte ho:  sudo apt install dpkg-dev" >&2
    echo "Program presto funguje: spustte dist/LULAN/LULAN" >&2
    exit 1
fi

STROM="build/prace/deb"
rm -rf "$STROM"
mkdir -p "$STROM/opt/lulan" \
         "$STROM/usr/bin" \
         "$STROM/usr/share/applications" \
         "$STROM/usr/share/doc/$BALICEK" \
         "$STROM/DEBIAN"

cp -R dist/LULAN/. "$STROM/opt/lulan/"
cp LICENSE "$STROM/usr/share/doc/$BALICEK/copyright"

# Ikony podle standardu hicolor, aby je nasla kazda plocha.
for HRANA in 16 32 48 64 128 256 512; do
    CIL="$STROM/usr/share/icons/hicolor/${HRANA}x${HRANA}/apps"
    mkdir -p "$CIL"
    if command -v convert >/dev/null; then
        convert "img/LULAN_icon.png" -resize "${HRANA}x${HRANA}" \
                "$CIL/lulan.png" 2>/dev/null || cp "img/LULAN_icon.png" "$CIL/lulan.png"
    else
        # Bez ImageMagicku se vsude pouzije puvodnich 512 px; system si
        # ikonu zmensi sam, jen o neco hure.
        cp "img/LULAN_icon.png" "$CIL/lulan.png"
    fi
done

# Spoustec. Odkaz se nepouziva zamerne: program si cestu k datum odvozuje
# od umisteni spustitelneho souboru a symlink by ho zavedl do /usr/bin.
cat > "$STROM/usr/bin/lulan" <<'SPOUSTEC'
#!/bin/sh
exec /opt/lulan/LULAN "$@"
SPOUSTEC
chmod 755 "$STROM/usr/bin/lulan"

cat > "$STROM/usr/share/applications/lulan.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=LULAN
GenericName=Hodnocení ekologického stavu vod
Comment=Hodnocení ekologického stavu vodních útvarů podle Rámcové směrnice o vodách
Exec=/opt/lulan/LULAN
Icon=lulan
Terminal=false
Categories=Science;Biology;Education;
StartupWMClass=LULAN
DESKTOP

VELIKOST_KB="$(du -sk "$STROM" | cut -f1)"

cat > "$STROM/DEBIAN/control" <<CONTROL
Package: $BALICEK
Version: $VERZE
Section: science
Priority: optional
Architecture: $ARCH
Maintainer: Masarykova univerzita <136750@mail.muni.cz>
Installed-Size: $VELIKOST_KB
Depends: libc6, libglib2.0-0, libgl1, libfontconfig1, libxkbcommon0, libdbus-1-3
Description: Hodnoceni ekologickeho stavu vodnich utvaru
 LULAN vyhodnocuje ekologicky stav a potencial vodnich utvaru podle
 Ramcove smernice o vodach pro vsechny biologicke slozky - makrozoobentos,
 fytobentos, fytoplankton, makrofyta a ryby.
 .
 Balicek obsahuje vlastni behove prostredi (Python a Qt), takze nevyzaduje
 zadne dalsi knihovny krome systemovych.
CONTROL

# Po instalaci se osvezi mezipameti plochy, jinak by se polozka v nabidce
# a ikona objevily az po odhlaseni.
cat > "$STROM/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    command -v update-desktop-database >/dev/null \
        && update-desktop-database -q /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null \
        && gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
fi
exit 0
POSTINST
chmod 755 "$STROM/DEBIAN/postinst"

cat > "$STROM/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    command -v update-desktop-database >/dev/null \
        && update-desktop-database -q /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null \
        && gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
fi
# Data uzivatele v ~/.local/share/LULAN se zamerne nemazou.
exit 0
POSTRM
chmod 755 "$STROM/DEBIAN/postrm"

mkdir -p build/vystup
DEB="build/vystup/${BALICEK}_${VERZE}_${ARCH}.deb"
rm -f "$DEB"
dpkg-deb --build --root-owner-group "$STROM" "$DEB" >/dev/null

echo "Hotovo: $DEB"

echo
echo "=== Sestaveni dokonceno ==="
du -sh "$DEB" | sed 's/^/  /'
echo
echo "Instalace:    sudo apt install ./$DEB"
echo "Odinstalace:  sudo apt remove $BALICEK"
