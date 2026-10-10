"""
Jednotny import dat z CSV.

Puvodne mela kazda tabulka vlastni importni metodu v `main_app_deploy.py`
(lokality, vzorky, vodni utvary) a vsechny delaly v podstate totez - nacist
soubor, overit hlavicku, prevest typy, vlozit radky. Lisily se ale v tom,
co kontroluji a jak se chovaji pri chybe.

Tady je misto toho POPIS tabulek: kazdy sloupec ma typ, priznak povinnosti,
popis a ukazkovou hodnotu. Z popisu se odvodi

  * vzorovy soubor ke stazeni (`sablona_csv`)
  * kontrola pred importem (`zkontroluj`)
  * vlastni zapis do databaze (`importuj`)

Novou tabulku staci pridat do POPISY - GUI ji nabidne samo.

Modul zamerne nezavisi na PyQt: pracuje s obycejnym sqlite3 spojenim, takze
se da spustit i z prikazove radky nebo z testu.

Pouziti z prikazove radky:
    python src/import_csv.py --seznam
    python src/import_csv.py --sablona lokality > lokality.csv
    python src/import_csv.py --kontrola lokality soubor.csv --db dtb/LULAN.db
    python src/import_csv.py --import lokality soubor.csv --db dtb/LULAN.db
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field

#: Oddelovace, ktere se pri nacitani zkousi (v tomto poradi).
ODDELOVACE = (";", "\t", ",")

#: Kodovani, ktera se pri nacitani zkousi.
KODOVANI = ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2")

#: Formaty data, ktere import prijima. Vystup je vzdy "DD.MM.RRRR".
FORMATY_DATA = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y",
                "%d.%m.%y", "%d. %m. %Y")

FORMAT_DATA_DB = "%d.%m.%Y"
FORMAT_CASU_DB = "%d.%m.%Y %H:%M:%S"


# ---------------------------------------------------------------------------
# Popis sloupce a tabulky
# ---------------------------------------------------------------------------

@dataclass
class Sloupec:
    """Jeden sloupec importni tabulky.

    Args:
        nazev: nazev sloupce v CSV i v databazi
        popis: text do vzoroveho souboru a do chybovych hlasek
        typ: "text" | "cislo" | "cele" | "datum" | "volba"
        povinny: True = bez nej import neprobehne
        vzor: ukazkova hodnota do vzoroveho souboru
        volby: povolene hodnoty u typu "volba"
        rozsah: (min, max) u typu "cislo" a "cele"
        vychozi: cim se doplni prazdna hodnota u povinneho sloupce
    """

    nazev: str
    popis: str
    typ: str = "text"
    povinny: bool = False
    vzor: str = ""
    volby: tuple = ()
    rozsah: tuple | None = None
    vychozi: str | None = None


@dataclass
class Tabulka:
    """Popis jedne importovatelne tabulky."""

    klic: str
    nazev: str
    tabulka: str
    popis: str
    sloupce: list = field(default_factory=list)
    #: Sloupce, jejichz kombinace urcuje jiz existujici zaznam.
    klicove: tuple = ()
    #: Klic patri cele skupine radku, ne jednomu radku.
    #:
    #: U vzorku je klicem SAMPLE + TYP + LOC_ID + DATE, jenze jeden radek
    #: souboru je jeden taxon - klic se tedy opakuje tolikrat, kolik ma
    #: vzorek taxonu. Upozorneni "klic je v souboru vicekrat" by tu hlasilo
    #: kazdy druhy a dalsi radek, prestoze je vse v poradku. Misto nej se
    #: sestavi prehled (viz `souhrn`).
    klic_sdileny: bool = False
    #: Volitelna funkce, ktera ze zkontrolovanych radku sestavi prehled
    #: pro potvrzovaci dialog. Dostane (radky, znama_id) a vraci seznam
    #: textovych radku.
    souhrn: object = None
    #: Nazev sloupce s casem posledni zmeny, doplni se automaticky.
    sloupec_dtch: str | None = "DTCH"
    #: Poznamka, ktera se vypise do hlavicky vzoroveho souboru.
    poznamka: str = ""
    #: Starsi nazvy sloupcu, ktere se pri nacitani prevedou na dnesni
    #: ({stary_nazev: novy_nazev}).
    aliasy: dict = field(default_factory=dict)
    #: Volitelna kontrola pres cely radek. Dostane pripraveny dict hodnot
    #: a vraci text chyby, nebo None. Slouzi na pravidla, ktera nejdou
    #: vyjadrit u jednotliveho sloupce - napr. "aspon jedna z hodnot".
    kontrola_radku: object = None

    def sloupec(self, nazev):
        for s in self.sloupce:
            if s.nazev == nazev:
                return s
        return None

    @property
    def povinne(self):
        return [s.nazev for s in self.sloupce if s.povinny]


# ---------------------------------------------------------------------------
# Popisy jednotlivych tabulek
# ---------------------------------------------------------------------------

UMORI_VOLBY = ("1", "2", "3")
TYPY_VZORKU = ("MZB", "FB", "FP", "MF", "RYBY", "CHEM")

POPISY = {}


def _pridej(t):
    POPISY[t.klic] = t
    return t


_pridej(Tabulka(
    klic="lokality",
    nazev="Lokality (odběrné profily)",
    tabulka="loc",
    popis="Odběrné profily s abiotickými parametry.",
    klicove=("KOD",),
    poznamka=(
        "Povinný je pouze KOD. Abiotické parametry lze nechat prázdné - "
        "aplikace je umí dopočítat z WGS84 souřadnic (menu Nástroje).\n"
        "Sloupec KATEGORIE rozhoduje, která sada parametrů se použije: "
        "u tekoucích vod (R) Strahlerův řád, plocha povodí a sklon, "
        "u stojatých vod (J) hloubky a doba zdržení. Nevyplněná hodnota "
        "se bere jako R."
    ),
    sloupce=[
        Sloupec("KOD", "kód lokality, musí být jedinečný", "text",
                povinny=True, vzor="REF_001"),
        Sloupec("KATEGORIE", "R = tekoucí voda, J = stojatá voda", "volba",
                vzor="R", volby=("R", "J")),
        Sloupec("VU", "kód vodního útvaru, na kterém profil leží", "text",
                vzor="BER_0010"),
        Sloupec("TOK", "název toku", "text", vzor="Mže"),
        Sloupec("PROFIL", "označení profilu", "text", vzor="nad Stříbrem"),
        Sloupec("WGS84_LAT", "zeměpisná šířka ve stupních (WGS84)", "cislo",
                vzor="49.7534", rozsah=(48.0, 51.5)),
        Sloupec("WGS84_LON", "zeměpisná délka ve stupních (WGS84)", "cislo",
                vzor="13.0021", rozsah=(12.0, 19.0)),
        Sloupec("STRAHLER", "Strahlerův řád toku (1-9)", "cele",
                vzor="4", rozsah=(1, 9)),
        Sloupec("MNM", "nadmořská výška [m n. m.]", "cislo",
                vzor="412.5", rozsah=(0, 1700)),
        Sloupec("PLOCHA_POV", "plocha povodí [km2]", "cislo", vzor="128.4"),
        Sloupec("KM_OD_PRAM", "vzdálenost od pramene [km]", "cislo",
                vzor="23.7"),
        Sloupec("SLOPE", "podélný sklon toku [promile]", "cislo", vzor="4.2"),
        Sloupec("UMORI", "úmoří: 1 = Labe, 2 = Odra, 3 = Dunaj", "volba",
                vzor="1", volby=UMORI_VOLBY),
        # Parametry stojatych vod (KATEGORIE = J). U tekoucich vod zustavaji
        # prazdne. Typologii jezer urcuje nadmorska vyska, prumerna hloubka
        # a doba zdrzeni (Borovec a kol. 2014, Tab. 1).
        Sloupec("MAX_HLOUBKA", "jen jezera: maximální hloubka [m]", "cislo",
                vzor=""),
        Sloupec("PRUM_HLOUBKA", "jen jezera: průměrná hloubka [m]", "cislo",
                vzor=""),
        Sloupec("PLOCHA_KM2", "jen jezera: plocha hladiny [km2]", "cislo",
                vzor=""),
        Sloupec("TRT", "jen jezera: doba zdržení vody [rok]", "cislo",
                vzor=""),
        Sloupec("GEOLOGIE",
                "jen jezera: 1 = krystalinikum a vulkanity, "
                "2 = pískovce, jílovce, kvartér", "volba",
                vzor="", volby=("1", "2")),
    ],
))

_pridej(Tabulka(
    klic="utvary",
    nazev="Vodní útvary",
    tabulka="utvary",
    popis="Vodní útvary a jejich vlastnosti rozhodující o metodice hodnocení.",
    klicove=("ID_UTVARU",),
    aliasy={"HMCH": "HMWB"},
    poznamka=(
        "Sloupec HMWB rozhoduje, zda se počítá ekologický stav (P) nebo "
        "potenciál (S); u umělých útvarů (U) se biologické složky nehodnotí. "
        "Starší exporty se sloupcem HMCH se načtou také."
    ),
    sloupce=[
        Sloupec("ID_UTVARU", "kód vodního útvaru", "text",
                povinny=True, vzor="BER_0010"),
        Sloupec("NAZ_UTVARU", "název útvaru", "text",
                vzor="Mže od pramene po vzdutí nádrže Lučina"),
        Sloupec("DILCI_POVODI", "kód dílčího povodí", "text", vzor="BER"),
        Sloupec("KATEGORIE", "R = řeka, J = jezero", "volba",
                povinny=True, vzor="R", volby=("R", "J")),
        Sloupec("HMWB", "P = přirozený, S = silně ovlivněný, U = umělý",
                "volba", povinny=True, vzor="P", volby=("P", "S", "U")),
        Sloupec("VYSYCHAVY", "P = perenální (stálý tok), I = vysychavý",
                "volba", povinny=True, vzor="P", volby=("P", "I")),
        Sloupec("BROD", "B = broditelný, NEBROD = nebroditelný", "volba",
                povinny=True, vzor="B", volby=("B", "NEBROD")),
    ],
))

def _sklonuj(pocet, jeden, dva, pet):
    """Ceske sklonovani podle poctu: 1 taxon, 2 taxony, 5 taxonu."""
    if pocet == 1:
        return jeden
    if 2 <= pocet <= 4:
        return dva
    return pet


def _souhrn_vzorku(radky, znama_id=None):
    """Prehled vzorku a poctu jejich polozek pro potvrzovaci dialog.

    Soubor ma jeden radek na taxon, takze samotny pocet radku uzivateli
    nic nerekne. Podstatne je, kolik vzorku se chysta naimportovat
    a kolik ma ktery taxonu.

    Args:
        radky: zkontrolovane radky (Vysledek.radky)
        znama_id: klice vzorku, ktere uz v databazi jsou

    Returns:
        seznam textovych radku
    """
    znama_id = znama_id or set()

    # Pocita se pocet ruznych nazvu, ne radku: radky tehoz taxonu
    # v temze vzorku import sloucí do jednoho.
    vzorky = {}
    for r in radky:
        klic = (r.get("SAMPLE"), r.get("TYP"), r.get("LOC_ID"), r.get("DATE"))
        vzorky.setdefault(klic, set()).add(r.get("NAME"))

    if not vzorky:
        return []

    pocet = len(vzorky)
    text = [f"Chystáte se importovat {pocet} "
            f"{_sklonuj(pocet, 'vzorek', 'vzorky', 'vzorků')}:"]

    # Serazeno podle kodu vzorku, aby se v dlouhem seznamu dalo hledat.
    for klic in sorted(vzorky, key=lambda k: tuple(str(x or "") for x in k)):
        n = len(vzorky[klic])
        # U chemie nejsou taxony, ale parametry.
        veci = ("parametr", "parametry", "parametrů") if klic[1] == "CHEM" \
            else ("taxon", "taxony", "taxonů")
        znacka = "  (už v databázi)" if klic in znama_id else ""
        text.append(f"   {klic[0]} ({klic[1]}, {klic[3]}) — "
                    f"{n} {_sklonuj(n, *veci)}{znacka}")

    jiz = sum(1 for k in vzorky if k in znama_id)
    if jiz:
        text.append("")
        text.append(f"{jiz} z nich už v databázi "
                    f"{_sklonuj(jiz, 'je', 'jsou', 'je')} — co s nimi, "
                    "se zeptám v dalším kroku.")
    return text


def _kontrola_vzorku(radek):
    """U vzorku musi byt vyplnena aspon jedna kvantitativni hodnota.

    U tekoucich vod je to vzdy VAL (abundance nebo namerena hodnota),
    u stojatych vod ji ale nahrazuje BIOMASA (fytoplankton, ryby) nebo
    POKRYVNOST (makrofyta). Kdyby byl VAL povinny natvrdo, nesel by
    fytoplanktonni vzorek s biomasou naimportovat vubec.
    """
    if any(radek.get(s) is not None
           for s in ("VAL", "BIOMASA", "POKRYVNOST")):
        return None
    return "musí být vyplněna aspoň jedna z hodnot VAL, BIOMASA, POKRYVNOST"


_pridej(Tabulka(
    klic="vzorky",
    nazev="Vzorky a jejich data",
    tabulka="samples",
    popis=(
        "Odběry a naměřené hodnoty. Jeden řádek = jeden taxon (nebo chemický "
        "parametr) v jednom vzorku."
    ),
    klicove=("SAMPLE", "TYP", "LOC_ID", "DATE"),
    klic_sdileny=True,
    souhrn=lambda radky, znama: _souhrn_vzorku(radky, znama),
    sloupec_dtch="DTCH",
    kontrola_radku=_kontrola_vzorku,
    poznamka=(
        "Řádky se stejným SAMPLE, NAME, TYP, LOC_ID a DATE se sloučí - "
        "u biologických složek součtem abundancí, u chemie (TYP = CHEM) "
        "průměrem. Lokalita, která v databázi není, se založí prázdná."
    ),
    sloupce=[
        Sloupec("SAMPLE", "kód vzorku", "text", povinny=True,
                vzor="REF_001_J_MZB"),
        Sloupec("TYP", "biologická složka nebo CHEM", "volba", povinny=True,
                vzor="MZB", volby=TYPY_VZORKU),
        Sloupec("LOC_ID", "kód lokality (viz tabulka lokalit)", "text",
                povinny=True, vzor="REF_001"),
        Sloupec("DATE", "datum odběru", "datum", povinny=True,
                vzor="15.04.2024"),
        Sloupec("NAME", "název taxonu, u chemie kód parametru", "text",
                povinny=True, vzor="Baetis rhodani"),
        Sloupec("VAL", "abundance nebo naměřená hodnota", "cislo",
                vzor="56"),
        Sloupec("CF", "příznak nejisté determinace (cf.)", "text", vzor=""),
        Sloupec("JUV", "příznak juvenilního stadia; u ryb ve stojatých "
                "vodách označuje tohoroční (0+) rybu", "text", vzor=""),
        # Sloupce pro stojate vody. U tekoucich vod zustavaji prazdne.
        Sloupec("BIOMASA",
                "jen jezera: fytoplankton objemová biomasa [mm3/l], "
                "ryby biomasa úlovku [kg/1000 m2 sítě a noc]", "cislo",
                vzor=""),
        Sloupec("POKRYVNOST", "jen jezera: pokryvnost druhu makrofyt [%]",
                "cislo", vzor=""),
        Sloupec("SIT", "jen jezera, ryby: BT = bentická, PT = pelagická "
                "tenatní síť", "volba", vzor="", volby=("BT", "PT")),
        Sloupec("ZONA", "jen jezera, ryby: H = hrázová, P = přítoková část",
                "volba", vzor="", volby=("H", "P")),
    ],
))


# ---------------------------------------------------------------------------
# Vzorovy soubor
# ---------------------------------------------------------------------------

def sablona_csv(klic, oddelovac=";"):
    """Sestavi obsah vzoroveho CSV souboru pro danou tabulku.

    Soubor ma tri casti:
      * komentarove radky (zacinaji #) s popisem sloupcu
      * hlavicku s nazvy sloupcu
      * jeden ukazkovy radek s vyplnenymi hodnotami

    Komentarove radky import ignoruje, takze soubor lze nahrat i s nimi.
    """
    popis = POPISY[klic]
    vystup = io.StringIO()

    vystup.write(f"# Vzorový soubor pro import: {popis.nazev}\n")
    vystup.write(f"# {popis.popis}\n")
    if popis.poznamka:
        for radek in _zalom(popis.poznamka, 76):
            vystup.write(f"# {radek}\n")
    vystup.write("#\n# Sloupce:\n")
    for s in popis.sloupce:
        znacka = "povinný" if s.povinny else "volitelný"
        detail = f" ({', '.join(s.volby)})" if s.volby else ""
        vystup.write(f"#   {s.nazev:<14} {znacka:<10} {s.typ:<6} "
                     f"{s.popis}{detail}\n")
    vystup.write("#\n# První datový řádek je ukázkový - přepište ho "
                 "vlastními hodnotami.\n")

    zapis = csv.writer(vystup, delimiter=oddelovac, lineterminator="\n")
    zapis.writerow([s.nazev for s in popis.sloupce])
    zapis.writerow([s.vzor for s in popis.sloupce])
    return vystup.getvalue()


def _zalom(text, sirka):
    slova, radky, akt = text.split(), [], ""
    for s in slova:
        if len(akt) + len(s) + 1 > sirka:
            radky.append(akt)
            akt = s
        else:
            akt = f"{akt} {s}".strip()
    if akt:
        radky.append(akt)
    return radky


# ---------------------------------------------------------------------------
# Nacteni souboru
# ---------------------------------------------------------------------------

def nacti_csv(cesta):
    """Nacte CSV do seznamu dictu; sam pozna oddelovac i kodovani.

    Radky zacinajici '#' se preskakuji - vzorovy soubor v nich nese napovedu.

    Returns:
        (radky, oddelovac, kodovani)

    Raises:
        ValueError: pokud soubor nelze precist nebo nema vic nez jeden sloupec
    """
    posledni_chyba = None
    for kodovani in KODOVANI:
        try:
            with open(cesta, encoding=kodovani) as f:
                text = f.read()
        except (UnicodeDecodeError, LookupError) as e:
            posledni_chyba = e
            continue

        cisty = "\n".join(
            r for r in text.splitlines() if not r.lstrip().startswith("#")
        )
        if not cisty.strip():
            raise ValueError("Soubor neobsahuje žádná data.")

        for oddelovac in ODDELOVACE:
            cteni = csv.DictReader(io.StringIO(cisty), delimiter=oddelovac)
            if cteni.fieldnames and len(cteni.fieldnames) > 1:
                radky = [
                    {(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in r.items()}
                    for r in cteni
                ]
                return radky, oddelovac, kodovani

    raise ValueError(
        "Soubor se nepodařilo přečíst - zkontrolujte, že jde o CSV "
        "oddělené středníkem, tabulátorem nebo čárkou."
        + (f" ({posledni_chyba})" if posledni_chyba else "")
    )


# ---------------------------------------------------------------------------
# Kontrola hodnot
# ---------------------------------------------------------------------------

_CISLO = re.compile(r"^-?\d+([.,]\d+)?$")


def preved_hodnotu(hodnota, sloupec):
    """Prevede jednu hodnotu na typ sloupce.

    Returns:
        (hodnota, chyba) - chyba je None, kdyz je vse v poradku
    """
    if hodnota is None:
        hodnota = ""
    text = str(hodnota).strip()

    if text == "":
        if sloupec.povinny and sloupec.vychozi is None:
            return None, "chybí povinná hodnota"
        return (sloupec.vychozi if sloupec.vychozi is not None else None), None

    if sloupec.typ == "text":
        return text, None

    if sloupec.typ == "volba":
        if sloupec.volby and text not in sloupec.volby:
            return None, (
                f"'{text}' není povolená hodnota "
                f"(povoleno: {', '.join(sloupec.volby)})"
            )
        return text, None

    if sloupec.typ in ("cislo", "cele"):
        if not _CISLO.match(text):
            return None, f"'{text}' není číslo"
        cislo = float(text.replace(",", "."))
        if sloupec.typ == "cele":
            if abs(cislo - round(cislo)) > 1e-9:
                return None, f"'{text}' musí být celé číslo"
            cislo = int(round(cislo))
        if sloupec.rozsah:
            dolni, horni = sloupec.rozsah
            if not (dolni <= cislo <= horni):
                return None, (
                    f"hodnota {cislo} je mimo očekávaný rozsah "
                    f"{dolni} až {horni}"
                )
        return cislo, None

    if sloupec.typ == "datum":
        for fmt in FORMATY_DATA:
            try:
                return datetime.datetime.strptime(
                    text, fmt).strftime(FORMAT_DATA_DB), None
            except ValueError:
                continue
        return None, f"'{text}' není datum (očekává se např. 15.04.2024)"

    return text, None


@dataclass
class Vysledek:
    """Vysledek kontroly nebo importu."""

    radky: list = field(default_factory=list)
    chyby: list = field(default_factory=list)
    varovani: list = field(default_factory=list)
    #: Prehled pro potvrzovaci dialog - co se vlastne chysta importovat.
    #: Na rozdil od varovani nejde o nic zavadneho.
    souhrn: list = field(default_factory=list)
    vlozeno: int = 0
    prepsano: int = 0
    preskoceno: int = 0
    slouceno: int = 0

    @property
    def ok(self):
        return not self.chyby


def zkontroluj(radky, klic, znama_id=None):
    """Overi hlavicku a hodnoty proti popisu tabulky.

    Args:
        radky: vysledek nacti_csv
        klic: klic do POPISY
        znama_id: volitelna mnozina jiz existujicich klicu (pro varovani
            o duplicitach uvnitr souboru i proti databazi)

    Returns:
        Vysledek - v `radky` jsou prevedene hodnoty pripravene k zapisu
    """
    popis = POPISY[klic]
    v = Vysledek()

    if not radky:
        v.chyby.append("Soubor neobsahuje žádné datové řádky.")
        return v

    # starší názvy sloupců převést na dnešní (HMCH -> HMWB apod.)
    if popis.aliasy:
        pritomne = set(radky[0].keys())
        prevod = {
            stary: novy for stary, novy in popis.aliasy.items()
            if stary in pritomne and novy not in pritomne
        }
        if prevod:
            radky = [
                {prevod.get(k, k): hodnota for k, hodnota in r.items()}
                for r in radky
            ]
            v.varovani.append(
                "Načteny starší názvy sloupců: "
                + ", ".join(f"{s} → {n}" for s, n in prevod.items())
            )

    nalezene = set(radky[0].keys())
    chybi = [s for s in popis.povinne if s not in nalezene]
    if chybi:
        v.chyby.append(
            f"V souboru chybí povinné sloupce: {', '.join(chybi)}."
        )
        return v

    znama = set(popis.sloupce and [s.nazev for s in popis.sloupce])
    navic = sorted(x for x in nalezene if x and x not in znama)
    if navic:
        v.varovani.append(
            f"Sloupce, kterým aplikace nerozumí a přeskočí je: "
            f"{', '.join(navic)}."
        )

    videne = set()
    for i, radek in enumerate(radky, start=1):
        pripraveny = {}
        chyby_radku = []
        for s in popis.sloupce:
            if s.nazev not in radek:
                continue
            hodnota, chyba = preved_hodnotu(radek.get(s.nazev), s)
            if chyba:
                chyby_radku.append(f"sloupec {s.nazev}: {chyba}")
            else:
                pripraveny[s.nazev] = hodnota
        if not chyby_radku and popis.kontrola_radku is not None:
            chyba = popis.kontrola_radku(pripraveny)
            if chyba:
                chyby_radku.append(chyba)
        if chyby_radku:
            for c in chyby_radku[:3]:
                v.chyby.append(f"řádek {i}: {c}")
            continue

        # U tabulek, kde klic patri cele skupine radku (vzorky), se
        # opakovani klice nehlasi - je to normalni stav, ne chyba. Misto
        # toho se nize sestavi prehled.
        if popis.klicove and not popis.klic_sdileny:
            klic_radku = tuple(pripraveny.get(k) for k in popis.klicove)
            if klic_radku in videne:
                v.varovani.append(
                    f"řádek {i}: klíč {' / '.join(str(x) for x in klic_radku)} "
                    f"je v souboru vícekrát"
                )
            videne.add(klic_radku)
            if znama_id and klic_radku in znama_id:
                v.varovani.append(
                    f"řádek {i}: záznam {' / '.join(str(x) for x in klic_radku)}"
                    f" už v databázi je"
                )

        v.radky.append(pripraveny)

    if popis.souhrn is not None:
        v.souhrn = popis.souhrn(v.radky, znama_id)

    if len(v.chyby) > 20:
        zbytek = len(v.chyby) - 20
        v.chyby = v.chyby[:20] + [f"... a dalších {zbytek} chyb"]
    return v


def sloupce_tabulky(conn, tabulka):
    """Vrati mnozinu sloupcu, ktere tabulka v databazi skutecne ma."""
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({tabulka})")}
    except sqlite3.Error:
        return set()


def _prizpusob_sloupce(zapis, popis, skutecne):
    """Prevede nazvy sloupcu na ty, ktere databaze opravdu ma.

    Databaze, ktera jeste neprosla migraci, ma napriklad `HMCH` misto
    `HMWB`. Import tak funguje na obou verzich schematu. Sloupce, ktere
    tabulka nezna vubec, se vynechaji.
    """
    obraceny = {novy: stary for stary, novy in popis.aliasy.items()}
    vysledek = {}
    for sloupec, hodnota in zapis.items():
        if sloupec in skutecne:
            vysledek[sloupec] = hodnota
        elif obraceny.get(sloupec) in skutecne:
            vysledek[obraceny[sloupec]] = hodnota
    return vysledek


def existujici_klice(conn, klic):
    """Nacte z databaze mnozinu jiz pouzitych klicu dane tabulky."""
    popis = POPISY[klic]
    if not popis.klicove:
        return set()
    tabulka = "samples" if klic == "vzorky" else popis.tabulka
    sloupce = popis.klicove
    if klic == "vzorky":
        sloupce = ("SAMPLE_ID", "TYP", "LOC_ID", "DATE")
    skutecne = sloupce_tabulky(conn, tabulka)
    if not skutecne or any(s not in skutecne for s in sloupce):
        return set()
    try:
        dotaz = f"SELECT {', '.join(sloupce)} FROM {tabulka}"
        return {tuple(r) for r in conn.execute(dotaz)}
    except sqlite3.Error:
        return set()


# ---------------------------------------------------------------------------
# Zapis do databaze
# ---------------------------------------------------------------------------

def importuj(conn, radky, klic, prepsat=False):
    """Zapise zkontrolovane radky do databaze.

    Args:
        conn: sqlite3 spojeni
        radky: `Vysledek.radky` z funkce zkontroluj()
        klic: klic do POPISY
        prepsat: True = existujici zaznamy nahradit, False = preskocit

    Returns:
        Vysledek se statistikou
    """
    popis = POPISY[klic]
    if klic == "vzorky":
        return _importuj_vzorky(conn, radky, prepsat)

    v = Vysledek()
    cas = datetime.datetime.now().strftime(FORMAT_CASU_DB)
    existujici = existujici_klice(conn, klic)
    skutecne = sloupce_tabulky(conn, popis.tabulka)

    for radek in radky:
        klic_radku = tuple(radek.get(k) for k in popis.klicove)
        if klic_radku in existujici:
            if not prepsat:
                v.preskoceno += 1
                continue
            conn.execute(
                f"DELETE FROM {popis.tabulka} WHERE "
                + " AND ".join(f"{k} = ?" for k in popis.klicove),
                klic_radku,
            )
            v.prepsano += 1

        zapis = dict(radek)
        if popis.sloupec_dtch:
            zapis[popis.sloupec_dtch] = cas
        zapis = _prizpusob_sloupce(zapis, popis, skutecne)
        if not zapis:
            v.preskoceno += 1
            continue
        sloupce = list(zapis)
        conn.execute(
            f"INSERT INTO {popis.tabulka} ({', '.join(sloupce)}) "
            f"VALUES ({', '.join('?' * len(sloupce))})",
            [zapis[s] for s in sloupce],
        )
        v.vlozeno += 1
        existujici.add(klic_radku)

    conn.commit()
    return v


def _importuj_vzorky(conn, radky, prepsat):
    """Zapis vzorku - hlavicka do `samples`, hodnoty do `data`.

    Radky se stejnym SAMPLE, NAME, TYP, LOC_ID a DATE se slouci: u chemie
    prumerem, u biologickych slozek souctem.

    U stojatych vod do klice pribyvaji jeste SIT a ZONA - tyz druh ryby
    ulovi bentická i pelagická tenatní sit a metriky CZ-FBI je rozlisuji.
    Bez toho by se ulovek plotice z BT a PT slil do jednoho radku a vetsina
    metrik by se nedala spocitat.

    Puvodni verze mazala stary obsah dotazem
    `DELETE FROM data WHERE sample=? AND typ=? AND loc_id=? AND date=?`,
    jenze tabulka `data` sloupce `typ`, `loc_id` ani `date` nema - mazani
    tise selhalo a pri prepsani vzorku zustaly stare radky vedle novych.
    V databazi je po tomto 5 dvojic (vzorek, taxon) se dvema radky.
    """
    v = Vysledek()
    cas = datetime.datetime.now().strftime(FORMAT_CASU_DB)

    skupiny = {}
    for r in radky:
        k = (r["SAMPLE"], r["NAME"], r["TYP"], r["LOC_ID"], r["DATE"],
             r.get("SIT"), r.get("ZONA"))
        if k in skupiny:
            skupiny[k].append(r)
            v.slouceno += 1
        else:
            skupiny[k] = [r]

    def _slouc(sada, sloupec, prumer=False):
        cisla = [x[sloupec] for x in sada if x.get(sloupec) is not None]
        if not cisla:
            return None
        return sum(cisla) / len(cisla) if prumer else sum(cisla)

    hodnoty = {}
    for k, sada in skupiny.items():
        chemie = k[2] == "CHEM"
        prvni = sada[0]
        zaznam = {
            "val": _slouc(sada, "VAL", prumer=chemie),
            "cf": prvni.get("CF"),
            "juv": prvni.get("JUV"),
            "BIOMASA": _slouc(sada, "BIOMASA"),
            # Pokryvnost druhu je podil plochy, ne pocet - pri opakovanem
            # zaznamu tehoz druhu se prumeruje, necita.
            "POKRYVNOST": _slouc(sada, "POKRYVNOST", prumer=True),
            "SIT": k[5],
            "ZONA": k[6],
        }
        if all(zaznam[x] is None for x in ("val", "BIOMASA", "POKRYVNOST")):
            continue
        hodnoty[k] = zaznam

    # lokality, ktere v databazi nejsou, zalozit prazdne
    znamé_lokality = {r[0] for r in conn.execute("SELECT KOD FROM loc")}
    for k in hodnoty:
        if k[3] and k[3] not in znamé_lokality:
            conn.execute("INSERT INTO loc (KOD, DTCH) VALUES (?, ?)",
                         (k[3], cas))
            znamé_lokality.add(k[3])
            v.varovani.append(f"založena nová lokalita {k[3]}")

    existujici = existujici_klice(conn, "vzorky")
    hlavicky = {(k[0], k[2], k[3], k[4]) for k in hodnoty}

    for sample_id, typ, loc_id, datum in sorted(hlavicky):
        if (sample_id, typ, loc_id, datum) in existujici:
            if not prepsat:
                v.preskoceno += 1
                continue
            conn.execute(
                "DELETE FROM data WHERE sample = ?", (sample_id,)
            )
            conn.execute(
                "DELETE FROM samples WHERE SAMPLE_ID = ? AND TYP = ? "
                "AND LOC_ID = ? AND DATE = ?",
                (sample_id, typ, loc_id, datum),
            )
            v.prepsano += 1

        conn.execute(
            "INSERT INTO samples (SAMPLE_ID, TYP, LOC_ID, DATE, DTCH) "
            "VALUES (?, ?, ?, ?, ?)",
            (sample_id, typ, loc_id, datum, cas),
        )
        v.vlozeno += 1

        # Sloupce pro stojate vody nemusi byt ve stare databazi - zapisou
        # se jen ty, ktere tabulka `data` skutecne ma.
        dostupne = sloupce_tabulky(conn, "data")
        for k, zaznam in hodnoty.items():
            if (k[0], k[2], k[3], k[4]) != (sample_id, typ, loc_id, datum):
                continue
            zapis = {"sample": sample_id, "name": k[1], "DTCH": cas}
            for sloupec, hodnota in zaznam.items():
                if hodnota is not None and sloupec in dostupne:
                    zapis[sloupec] = hodnota
            nazvy = list(zapis)
            conn.execute(
                f"INSERT INTO data ({', '.join(nazvy)}) "
                f"VALUES ({', '.join('?' * len(nazvy))})",
                [zapis[n] for n in nazvy],
            )

    conn.commit()
    return v


# ---------------------------------------------------------------------------
# Prikazova radka
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seznam", action="store_true", help="vypsat tabulky")
    p.add_argument("--sablona", metavar="TABULKA")
    p.add_argument("--kontrola", nargs=2, metavar=("TABULKA", "SOUBOR"))
    p.add_argument("--import", dest="importovat", nargs=2,
                   metavar=("TABULKA", "SOUBOR"))
    p.add_argument("--db", default="dtb/LULAN_dtb_001.db")
    p.add_argument("--prepsat", action="store_true",
                   help="existujici zaznamy nahradit misto preskoceni")
    args = p.parse_args()

    if args.seznam:
        for k, t in POPISY.items():
            print(f"{k:10s} {t.nazev}  ->  tabulka {t.tabulka}")
            print(f"           povinné: {', '.join(t.povinne)}")
        return 0

    if args.sablona:
        if args.sablona not in POPISY:
            print(f"Neznámá tabulka: {args.sablona}", file=sys.stderr)
            return 1
        sys.stdout.write(sablona_csv(args.sablona))
        return 0

    zadani = args.kontrola or args.importovat
    if not zadani:
        p.print_help()
        return 1

    klic, cesta = zadani
    if klic not in POPISY:
        print(f"Neznámá tabulka: {klic}", file=sys.stderr)
        return 1
    if not os.path.exists(cesta):
        print(f"Soubor neexistuje: {cesta}", file=sys.stderr)
        return 1

    radky, oddelovac, kodovani = nacti_csv(cesta)
    print(f"načteno {len(radky)} řádků "
          f"(oddělovač '{oddelovac}', kódování {kodovani})")

    conn = sqlite3.connect(args.db)
    try:
        vysledek = zkontroluj(radky, klic, existujici_klice(conn, klic))
        for c in vysledek.chyby:
            print(f"  CHYBA  {c}")
        for c in vysledek.varovani[:10]:
            print(f"  pozor  {c}")
        if vysledek.souhrn:
            print()
            for c in vysledek.souhrn:
                print(c)
            print()
        if not vysledek.ok:
            print(f"\nKontrola neprošla: {len(vysledek.chyby)} chyb.")
            return 1
        print(f"kontrola v pořádku, připraveno {len(vysledek.radky)} řádků")

        if args.importovat:
            stat = importuj(conn, vysledek.radky, klic, prepsat=args.prepsat)
            print(f"vloženo {stat.vlozeno}, přepsáno {stat.prepsano}, "
                  f"přeskočeno {stat.preskoceno}, sloučeno {stat.slouceno}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
