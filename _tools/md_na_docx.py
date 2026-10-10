"""
Prevod DOKUMENTACE.md do wordovskeho dokumentu.

Prevod sam obstara pandoc; tenhle skript resi to, co pandoc neudela
dobre, a hlavne umoznuje vyrobit dokument znovu jednim prikazem, kdykoli
se markdown zmeni. Rucne slozeny .docx by se po prvni oprave textu
rozesel se zdrojem.

Co skript navic delá
--------------------
1. **Sirky bunek v tabulkach.** Pandoc zapise sirku tabulky v procentech
   a bunkam nedá zadnou. Word si s tim poradi, LibreOffice a Google Docs
   ale sloupce sesypou pod sebe a tabulka se rozpadne na odstavce.
   Skript prepocita sirky na pevne jednotky (DXA) a kazde bunce ji
   doplni.

2. **Chybejici styl tabulky.** Pandoc kazde tabulce priradi styl `Table`.
   Kdyz ho dokument nema, Word i LibreOffice tabulku rozhodi. Skript
   styl doplni.

3. **Rucni obsah.** V markdownu je seznam kapitol s odkazy, ve Wordu ho
   nahrazuje pravy obsah (pole TOC). Skript rucni seznam vynechá.

4. **Hlavicka uvodni tabulky.** Markdown ji ma prazdnou (vypada to lip),
   pandoc z takove tabulky udela odstavce. Skript ji doplni.

5. **Dvojity popisek obrazku.** V markdownu je popisek dvakrat - jako
   alternativni text a jako kurzivni radek pod obrazkem. Pandoc by
   z obou udelal popisek; skript ten alternativni vypusti.

Proc se nepouziva predloha zadavatele
-------------------------------------
Nabizelo by se prevzit styly z puvodniho dokumentu (`--predloha`), at
dokument dostane hlavicku s logem TACR. V praxi to ale nefunguje: styly
predlohy maji ceske nazvy, pandoc se odkazuje na anglicke, nadpisy maji
automaticke cislovani, ktere se scita s nasim, a tabulky se rozpadnou.
Vychozi styly pandocu davaji cisty a spravne vysazeny dokument; hlavicku
s logem lze do nej vlozit ve Wordu za par vterin.

Volba `--predloha` zustava pro pripad, ze se predloha upravi tak, aby
pandocu vyhovovala.

Pouziti:
    python _tools/md_na_docx.py
    python _tools/md_na_docx.py --vstup jiny.md --vystup jiny.docx
    python _tools/md_na_docx.py --predloha build/predloha_dokumentace.docx

Predpoklady: pandoc, knihovna lxml.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VYCHOZI_VSTUP = os.path.join(KOREN, "DOKUMENTACE.md")
VYCHOZI_VYSTUP = os.path.join(KOREN, "DOKUMENTACE.docx")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ---------------------------------------------------------------------
#  Uprava markdownu pred prevodem
# ---------------------------------------------------------------------

def priprav_markdown(cesta):
    """Vrati text markdownu upraveny pro prevod do Wordu."""
    with open(cesta, encoding="utf-8") as f:
        text = f.read()

    # Rucni seznam kapitol nahradi pravy obsah (pole TOC).
    text = re.sub(r"## Obsah\n.*?\n---\n", "", text, count=1, flags=re.S)

    # Tabulka bez zahlavi by se prevedla na odstavce.
    text = re.sub(r"^\|\s*\|\s*\|\n\|-+\|-+\|\n",
                  "| Položka | Hodnota |\n|---|---|\n",
                  text, count=1, flags=re.M)

    # Popisek obrazku je v markdownu dvakrat: jako alternativni text
    # (kvuli ctecum) a jako kurzivni radek pod obrazkem (kvuli cislovani
    # "Obr. 1"). Pandoc z alternativniho textu udela dalsi popisek, takze
    # by ve Wordu byly pod kazdym obrazkem dva. Alternativni text proto
    # pro Word vypustime.
    text = re.sub(r"^!\[[^\]]*\]\(", "![](", text, flags=re.M)
    return text


# ---------------------------------------------------------------------
#  Uprava predlohy
# ---------------------------------------------------------------------

def priprav_predlohu(cesta, cil):
    """Odebere z predlohy automaticke cislovani nadpisu.

    Returns:
        cesta k upravene predloze, nebo None kdyz predloha neexistuje
    """
    if not cesta or not os.path.exists(cesta):
        return None

    rozbaleno = os.path.join(cil, "predloha")
    with zipfile.ZipFile(cesta) as z:
        z.extractall(rozbaleno)

    styly = os.path.join(rozbaleno, "word", "styles.xml")
    if os.path.exists(styly):
        with open(styly, encoding="utf-8") as f:
            obsah = f.read()
        obsah = re.sub(
            r'<w:style [^>]*w:styleId="(?:Heading|Nadpis)\d"[^>]*>.*?</w:style>',
            lambda m: re.sub(r"<w:numPr>.*?</w:numPr>", "", m.group(0),
                             flags=re.S),
            obsah, flags=re.S)
        with open(styly, "w", encoding="utf-8") as f:
            f.write(obsah)

    upravena = os.path.join(cil, "predloha_upravena.docx")
    with zipfile.ZipFile(upravena, "w", zipfile.ZIP_DEFLATED) as z:
        for koren, _, soubory in os.walk(rozbaleno):
            for s in soubory:
                plna = os.path.join(koren, s)
                z.write(plna, os.path.relpath(plna, rozbaleno))
    return upravena


# ---------------------------------------------------------------------
#  Uprava hotoveho dokumentu
# ---------------------------------------------------------------------

def _sirka_sazby(strom):
    """Sirka sazebniho obrazce v DXA - sirka stranky bez okraju."""
    vychozi = 9072  # A4 na vysku s okraji 2,5 cm
    for sekce in strom.iter(f"{W}sectPr"):
        velikost = sekce.find(f"{W}pgSz")
        okraje = sekce.find(f"{W}pgMar")
        if velikost is None or okraje is None:
            continue
        try:
            sirka = int(velikost.get(f"{W}w"))
            vlevo = int(okraje.get(f"{W}left"))
            vpravo = int(okraje.get(f"{W}right"))
        except (TypeError, ValueError):
            continue
        if sirka - vlevo - vpravo > 0:
            return sirka - vlevo - vpravo
    return vychozi


def sirky_bunek(strom):
    """Doplni tabulkam pevne sirky sloupcu i bunek.

    Pandoc zapise sirku tabulky v procentech a bunkam nedá zadnou;
    u casti tabulek navic vynecha celou mrizku sloupcu. Word si domysli
    zbytek sam, ale LibreOffice a Google Docs sloupce sesypou a z tabulky
    zbyde rada odstavcu pod sebou. Pevna sirka v DXA (1440 na palec) to
    resi ve vsech trech.

    Chybi-li mrizka, pocet sloupcu se vezme z prvniho radku a sirka
    sazebniho obrazce se mezi ne rozdeli rovnym dilem.

    Returns:
        pocet upravenych tabulek
    """
    from lxml import etree

    sazba = _sirka_sazby(strom)
    upraveno = 0

    for tbl in strom.iter(f"{W}tbl"):
        radky = tbl.findall(f"{W}tr")
        if not radky:
            continue

        mrizka = tbl.find(f"{W}tblGrid")
        sloupce = ([int(g.get(f"{W}w", "0"))
                    for g in mrizka.findall(f"{W}gridCol")]
                   if mrizka is not None else [])

        if not sloupce or sum(sloupce) <= 0:
            pocet = max(len(r.findall(f"{W}tc")) for r in radky)
            if not pocet:
                continue
            sirka = sazba // pocet
            # Zbytek po deleni dostane posledni sloupec, aby soucet sedel.
            sloupce = [sirka] * (pocet - 1) + [sazba - sirka * (pocet - 1)]

            if mrizka is None:
                mrizka = etree.SubElement(tbl, f"{W}tblGrid")
            else:
                for g in list(mrizka):
                    mrizka.remove(g)
            tbl.remove(mrizka)
            # tblGrid patri hned za tblPr.
            vlastnosti = tbl.find(f"{W}tblPr")
            tbl.insert(1 if vlastnosti is not None else 0, mrizka)
            for w in sloupce:
                etree.SubElement(mrizka, f"{W}gridCol").set(f"{W}w", str(w))

        # Sirka cele tabulky: soucet sloupcu, v pevnych jednotkach.
        vlastnosti = tbl.find(f"{W}tblPr")
        if vlastnosti is not None:
            sirka = vlastnosti.find(f"{W}tblW")
            if sirka is not None:
                sirka.set(f"{W}type", "dxa")
                sirka.set(f"{W}w", str(sum(sloupce)))

        for radek in tbl.findall(f"{W}tr"):
            for i, bunka in enumerate(radek.findall(f"{W}tc")):
                if i >= len(sloupce):
                    continue
                _nastav_sirku_bunky(bunka, sloupce[i])
        upraveno += 1
    return upraveno


def _nastav_sirku_bunky(bunka, sirka):
    """Zapise sirku do vlastnosti bunky; tcPr musi byt prvni potomek."""
    from lxml import etree

    vlastnosti = bunka.find(f"{W}tcPr")
    if vlastnosti is None:
        vlastnosti = etree.SubElement(bunka, f"{W}tcPr")
        bunka.remove(vlastnosti)
        bunka.insert(0, vlastnosti)

    tcw = vlastnosti.find(f"{W}tcW")
    if tcw is None:
        tcw = etree.SubElement(vlastnosti, f"{W}tcW")
        vlastnosti.remove(tcw)
        vlastnosti.insert(0, tcw)
    tcw.set(f"{W}type", "dxa")
    tcw.set(f"{W}w", str(sirka))


#: Definice stylu tabulky, na ktery se pandoc odkazuje.
#:
#: Pandoc kazde tabulce priradi styl `Table`. Predloha od zadavatele ho
#: ale nema - jeji styly se jmenuji cesky (`Mkatabulky`, `Normlntabulka`).
#: Odkaz do prazdna pak LibreOffice i Word zmate natolik, ze tabulku
#: vykresli jako radu odstavcu pod sebou. Chybi-li styl, doplni se tenhle:
#: tenke linky kolem bunek, tucna hlavicka.
STYL_TABULKY = """
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
         w:type="table" w:styleId="Table">
  <w:name w:val="Table"/>
  <w:basedOn w:val="TableNormal"/>
  <w:tblPr>
    <w:tblBorders>
      <w:top w:val="single" w:sz="4" w:space="0" w:color="999999"/>
      <w:left w:val="single" w:sz="4" w:space="0" w:color="999999"/>
      <w:bottom w:val="single" w:sz="4" w:space="0" w:color="999999"/>
      <w:right w:val="single" w:sz="4" w:space="0" w:color="999999"/>
      <w:insideH w:val="single" w:sz="4" w:space="0" w:color="999999"/>
      <w:insideV w:val="single" w:sz="4" w:space="0" w:color="999999"/>
    </w:tblBorders>
    <w:tblCellMar>
      <w:top w:w="60" w:type="dxa"/>
      <w:left w:w="100" w:type="dxa"/>
      <w:bottom w:w="60" w:type="dxa"/>
      <w:right w:w="100" w:type="dxa"/>
    </w:tblCellMar>
  </w:tblPr>
</w:style>
"""


def doplneny_styl_tabulky(data):
    """Doplni do styles.xml styl `Table`, pokud tam neni.

    Returns:
        (nova data, True kdyz se doplnovalo)
    """
    from lxml import etree

    strom = etree.fromstring(data)
    for styl in strom.findall(f"{W}style"):
        if styl.get(f"{W}styleId") == "Table":
            return data, False

    strom.append(etree.fromstring(STYL_TABULKY.strip()))
    return etree.tostring(strom, xml_declaration=True,
                          encoding="UTF-8", standalone=True), True


def uprav_dokument(cesta):
    """Otevre hotovy .docx, upravi tabulky a ulozi zpet.

    Returns:
        (pocet upravenych tabulek, doplnil se styl tabulky?)
    """
    from lxml import etree

    docasny = cesta + ".tmp"
    upraveno = 0
    doplnen_styl = False
    with zipfile.ZipFile(cesta) as vstup:
        polozky = vstup.infolist()
        with zipfile.ZipFile(docasny, "w", zipfile.ZIP_DEFLATED) as vystup:
            for polozka in polozky:
                data = vstup.read(polozka.filename)
                if polozka.filename == "word/document.xml":
                    strom = etree.fromstring(data)
                    upraveno = sirky_bunek(strom)
                    data = etree.tostring(
                        strom, xml_declaration=True,
                        encoding="UTF-8", standalone=True)
                elif polozka.filename == "word/styles.xml":
                    data, doplnen_styl = doplneny_styl_tabulky(data)
                vystup.writestr(polozka, data)
    os.replace(docasny, cesta)
    return upraveno, doplnen_styl


# ---------------------------------------------------------------------

def preved(vstup, vystup, predloha=None, nadpis_obsahu="Obsah"):
    """Prevede markdown na .docx. Vraci pocet upravenych tabulek."""
    if not shutil.which("pandoc"):
        raise SystemExit(
            "Chybí pandoc. Nainstalujte ho:\n"
            "   macOS:  brew install pandoc\n"
            "   Linux:  sudo apt install pandoc\n"
            "   Windows: https://pandoc.org/installing.html")

    with tempfile.TemporaryDirectory() as docasny:
        md = os.path.join(docasny, "dokumentace.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write(priprav_markdown(vstup))

        prikaz = [
            "pandoc", md,
            "--from=markdown", "--to=docx",
            "--toc", "--toc-depth=3",
            "--metadata", f"toc-title={nadpis_obsahu}",
            # Obrazky jsou v markdownu relativne ke korenu projektu.
            f"--resource-path={os.path.dirname(os.path.abspath(vstup))}",
            "-o", vystup,
        ]
        upravena = priprav_predlohu(predloha, docasny)
        if upravena:
            prikaz.insert(-2, f"--reference-doc={upravena}")

        vysledek = subprocess.run(prikaz, capture_output=True, text=True)
        if vysledek.returncode != 0:
            raise SystemExit(f"pandoc selhal:\n{vysledek.stderr}")

    return uprav_dokument(vystup)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vstup", default=VYCHOZI_VSTUP)
    p.add_argument("--vystup", default=VYCHOZI_VYSTUP)
    p.add_argument("--predloha", default=None,
                   help="dokument, ze ktereho se prevezmou styly "
                        "(vychozi: styly pandocu - viz hlavicka skriptu)")
    args = p.parse_args()

    if not os.path.exists(args.vstup):
        print(f"Vstup neexistuje: {args.vstup}", file=sys.stderr)
        return 1

    predloha = args.predloha
    if predloha and not os.path.exists(predloha):
        print(f"Předloha {predloha} neexistuje, použijí se výchozí styly.")
        predloha = None

    tabulek, styl = preved(args.vstup, args.vystup, predloha)
    velikost = os.path.getsize(args.vystup) // 1024
    print(f"Hotovo: {args.vystup} ({velikost} kB, "
          f"upraveno {tabulek} tabulek"
          f"{', doplněn styl tabulky' if styl else ''})")
    print("\nVe Wordu jednou stiskněte Ctrl+A a F9, aby se naplnil obsah –")
    print("pole obsahu se plní až při otevření.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
