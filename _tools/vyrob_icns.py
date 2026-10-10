"""
Vyrobi macOS ikonu (.icns) z jednoho PNG.

macOS chce ikonu ve vlastnim formatu `.icns`, ktery nese vic velikosti
najednou - jinou pouzije Finder v seznamu, jinou Dock a jinou nahled.
Kdyby se dodala jen jedna, system by si zbytek doskaloval sam a ikona
by byla rozmazana.

Na Macu by stacil systemovy `iconutil`, jenze ten na Windows ani na
Linuxu neni - a sestaveni ma jit pripravit odkudkoli. Format `.icns`
je pritom jednoduchy: hlavicka, a za ni bloky, z nichz kazdy ma ctyri
znaky typu, delku a data. Novejsi typy (`ic07` a dal) berou PNG rovnou,
takze staci obrazek zmensit a vlozit.

Pouziti:
    python _tools/vyrob_icns.py                 # img/LULAN_icon.png -> .icns
    python _tools/vyrob_icns.py vstup.png vystup.icns
"""

from __future__ import annotations

import io
import os
import struct
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VYCHOZI_VSTUP = os.path.join(KOREN, "img", "LULAN_icon.png")
VYCHOZI_VYSTUP = os.path.join(KOREN, "img", "LULAN_icon.icns")

#: (typ bloku, hrana v pixelech). Typy s `2x` jsou verze pro displeje
#: s vysokym rozlisenim - maji dvojnasobek pixelu na tutez velikost.
#: Starsi typy (`is32`, `il32`) tu nejsou zamerne: pouzivaji vlastni
#: kompresi a modernimu macOS staci PNG.
VELIKOSTI = (
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),   # 512@2x
    ("ic11", 32),     # 16@2x
    ("ic12", 64),     # 32@2x
    ("ic13", 256),    # 128@2x
    ("ic14", 512),    # 256@2x
)


def png_ve_velikosti(obrazek, hrana):
    """Zmensi obrazek na zadanou hranu a vrati ho jako PNG v pameti."""
    from PIL import Image

    zmenseny = obrazek.resize((hrana, hrana), Image.LANCZOS)
    buf = io.BytesIO()
    zmenseny.save(buf, format="PNG")
    return buf.getvalue()


def vyrob(vstup=None, vystup=None):
    """Slozi .icns ze zdrojoveho PNG.

    Returns:
        cesta k vytvorenemu souboru
    """
    from PIL import Image

    vstup = vstup or VYCHOZI_VSTUP
    vystup = vystup or VYCHOZI_VYSTUP

    obrazek = Image.open(vstup).convert("RGBA")
    if obrazek.width != obrazek.height:
        print(f"Varování: {os.path.basename(vstup)} není čtvercový "
              f"({obrazek.width}×{obrazek.height}) — ikona bude zkreslená.")

    bloky = []
    preskocene = []
    for typ, hrana in VELIKOSTI:
        if hrana > obrazek.width:
            # Zvetsovat zdroj nema smysl - vznikla by jen rozmazana
            # varianta, kterou by system stejne radeji nepouzil.
            preskocene.append(hrana)
            continue
        data = png_ve_velikosti(obrazek, hrana)
        # Kazdy blok: 4 znaky typu + delka vcetne teto hlavicky (4+4 B).
        bloky.append(typ.encode("ascii") + struct.pack(">I", len(data) + 8)
                     + data)

    telo = b"".join(bloky)
    # Hlavicka souboru: 'icns' + celkova delka vcetne hlavicky.
    soubor = b"icns" + struct.pack(">I", len(telo) + 8) + telo

    os.makedirs(os.path.dirname(vystup), exist_ok=True)
    with open(vystup, "wb") as f:
        f.write(soubor)

    if preskocene:
        print(f"Vynecháno {sorted(set(preskocene))} px — zdroj má jen "
              f"{obrazek.width} px a zvětšovat ho nemá smysl.")
    return vystup, len(bloky)


def main():
    vstup = sys.argv[1] if len(sys.argv) > 1 else None
    vystup = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        cesta, pocet = vyrob(vstup, vystup)
    except ImportError:
        raise SystemExit(
            "Chybí knihovna Pillow. Nainstalujte ji: pip install pillow")
    except OSError as chyba:
        raise SystemExit(f"Nepodařilo se vyrobit ikonu: {chyba}")

    velikost = os.path.getsize(cesta)
    print(f"Hotovo: {cesta} ({velikost // 1024} kB, {pocet} velikostí)")


if __name__ == "__main__":
    main()
