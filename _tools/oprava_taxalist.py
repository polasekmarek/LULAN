"""
Oprava taxonomickych seznamu: doplneni ID a PARENT_ID.

Problem
-------
Cast taxonu v tabulce `taxalist_mzb` nema vyplnene ID a jina cast nema
vyplnene PARENT_ID, prestoze jmeno nadrazeneho taxonu ve sloupci PARENT
zname. Dusledkem je pretrzeny taxonomicky rodokmen - metriky zalozene na
prislusnosti ke skupine (EPT Abu, EPT Tax, pocet celedi, pocet taxonu
pakomaru) takove taxony nezapocitaji.

Oba nedostatky spolu souvisi: chybejici PARENT_ID vzdy ukazuje na rodice,
ktery sam nema ID. Skript proto postupuje ve dvou krocich:

  1. taxonum bez ID priradi nove ID z vyhrazeneho rozsahu (NOVE_ID_OD)
  2. iterativne doplni PARENT_ID podle jmena ve sloupci PARENT

Krok 2 se opakuje, dokud se neco doplnuje - rodice muzou tvorit retez
(taxon bez ID je potomkem jineho taxonu bez ID).

Bezpecnost
----------
Skript pred zapisem overi, ze taxony bez ID nejsou pouzite v tabulce `data`
ani jako cil adjustaci; jinak zapis odmitne. Vzdy vytvori zalohu databaze.
Bez prepinace --zapsat pouze vypise, co by udelal.

Pouziti
-------
    python _tools/oprava_taxalist.py dtb/LULAN_dtb_001.db            # nahled
    python _tools/oprava_taxalist.py dtb/LULAN_dtb_001.db --zapsat
    python _tools/oprava_taxalist.py dtb/LULAN_dtb_001.db --tabulka taxalist_fb
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime

#: Rozsah, ze ktereho se prideluji nova ID.
#:
#: Zamerne lezi vysoko nad nejvyssim ID pouzivanym v taxonomickych seznamech
#: (2 002 437 489), aby bylo na prvni pohled poznat, ze jde o lokalne
#: pridelene ID, a aby nekolidovalo s kody prebiranymi z IS ARROW.
NOVE_ID_OD = 9_000_000_000

#: Maximalni pocet iteraci pri doplnovani PARENT_ID (ochrana proti cyklum).
MAX_ITERACI = 20

#: Hodnota PARENT_ID oznacujici korenovy taxon (nema nadrazeny taxon).
KOREN_PARENT_ID = -1

VYCHOZI_TABULKY = ["taxalist_mzb", "taxalist_fb", "taxalist_mf", "taxalist_ryby"]


# ---------------------------------------------------------------------------
# Analyza
# ---------------------------------------------------------------------------

def nacti_stav(conn, tabulka):
    """Nacte taxony a zjisti, co chybi."""
    conn.row_factory = sqlite3.Row
    radky = [
        dict(r)
        for r in conn.execute(
            f"SELECT rowid, ID, NAME, PARENT, PARENT_ID, LEVEL FROM {tabulka}"
        )
    ]
    podle_jmena = {r["NAME"]: r for r in radky}
    return radky, podle_jmena


def zkontroluj_bezpecnost(conn, tabulka, bez_id):
    """Overi, ze taxony bez ID nejsou nikde referencovane.

    Returns:
        list textovych namitek; prazdny seznam znamena, ze zapis je bezpecny
    """
    namitky = []
    jmena = [r["NAME"] for r in bez_id]
    if not jmena:
        return namitky

    # pouziti v datech vzorku
    davka = ",".join("?" for _ in jmena)
    pouzite = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT name FROM data WHERE name IN ({davka})", jmena
        )
    ]
    if pouzite:
        namitky.append(
            f"{len(pouzite)} taxonu bez ID se vyskytuje v tabulce `data`: "
            + ", ".join(pouzite[:5])
        )

    # cil adjustaci nelze zkontrolovat podle jmena (adjustace pracuje s ID),
    # ale taxon bez ID nemuze byt cilem - kontrola je zde pro uplnost
    return namitky


# ---------------------------------------------------------------------------
# Oprava
# ---------------------------------------------------------------------------

def priradit_id(radky, od):
    """Priradi nova ID taxonum, ktere ho nemaji.

    Returns:
        list dvojic (rowid, nove_id, nazev)
    """
    pouzita = {r["ID"] for r in radky if r["ID"] is not None}
    dalsi = od
    prirazeno = []

    for r in sorted(
        (r for r in radky if r["ID"] is None), key=lambda x: x["NAME"] or ""
    ):
        while dalsi in pouzita:
            dalsi += 1
        prirazeno.append((r["rowid"], dalsi, r["NAME"]))
        r["ID"] = dalsi          # promitnout i do pameti pro dalsi krok
        pouzita.add(dalsi)
        dalsi += 1

    return prirazeno


def doplnit_parent_id(radky, podle_jmena):
    """Iterativne doplni PARENT_ID podle jmena ve sloupci PARENT.

    Returns:
        (doplneno, nedoplneno) - doplneno je list (rowid, parent_id, nazev,
        jmeno_rodice), nedoplneno je list (nazev, jmeno_rodice, duvod)
    """
    doplneno = []

    for _ in range(MAX_ITERACI):
        zmena = False
        for r in radky:
            if r["PARENT_ID"] is not None:
                continue
            jmeno_rodice = (r["PARENT"] or "").strip()
            if not jmeno_rodice:
                continue
            rodic = podle_jmena.get(jmeno_rodice)
            if rodic is None or rodic["ID"] is None:
                continue
            if rodic["NAME"] == r["NAME"]:
                continue          # taxon sam sobe rodicem - preskocit
            r["PARENT_ID"] = rodic["ID"]
            doplneno.append((r["rowid"], rodic["ID"], r["NAME"], jmeno_rodice))
            zmena = True
        if not zmena:
            break

    nedoplneno = []
    for r in radky:
        if r["PARENT_ID"] is not None:
            continue
        jmeno_rodice = (r["PARENT"] or "").strip()
        if not jmeno_rodice:
            duvod = "nevyplneny sloupec PARENT (nejspis korenovy taxon)"
        elif jmeno_rodice == r["NAME"]:
            duvod = "taxon je uveden sam sobe jako rodic"
        elif jmeno_rodice not in podle_jmena:
            duvod = (
                f"rodic '{jmeno_rodice}' v seznamu neexistuje "
                f"(korenovy taxon nebo preklep ve jmene)"
            )
        else:
            duvod = f"rodic '{jmeno_rodice}' nema ID ani po pridelovani"
        nedoplneno.append((r["NAME"], jmeno_rodice or "-", r["LEVEL"], duvod))

    return doplneno, nedoplneno


def zkontroluj_cykly(radky, podle_jmena):
    """Najde taxony, jejichz rodokmen tvori cyklus."""
    podle_id = {r["ID"]: r for r in radky if r["ID"] is not None}
    cykly = []
    for r in radky:
        videne, aktualni, hloubka = set(), r, 0
        while aktualni is not None and hloubka < 50:
            if aktualni["NAME"] in videne:
                cykly.append(r["NAME"])
                break
            videne.add(aktualni["NAME"])
            rodic_id = aktualni["PARENT_ID"]
            if rodic_id == KOREN_PARENT_ID:
                break
            aktualni = podle_id.get(rodic_id)
            hloubka += 1
    return cykly


def hloubka_rodokmenu(radky):
    """Vrati nejvetsi hloubku taxonomickeho rodokmenu (pro kontrolu)."""
    podle_id = {r["ID"]: r for r in radky if r["ID"] is not None}
    nejhlubsi = 0
    for r in radky:
        aktualni, hloubka = r, 0
        while aktualni is not None and hloubka < 50:
            rodic_id = aktualni["PARENT_ID"]
            if rodic_id == KOREN_PARENT_ID:
                break
            aktualni = podle_id.get(rodic_id)
            hloubka += 1
        nejhlubsi = max(nejhlubsi, hloubka)
    return nejhlubsi


# ---------------------------------------------------------------------------
# Hlavni beh
# ---------------------------------------------------------------------------

def zapis_report(cesta, tabulka, prirazeno, doplneno, nedoplneno, podle_jmena):
    """Ulozi prehled provedenych zmen do CSV."""
    import csv

    nove = not __import__("os").path.exists(cesta)
    with open(cesta, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if nove:
            w.writerow([
                "TABULKA", "ZMENA", "TAXON", "UROVEN",
                "PUVODNI_HODNOTA", "NOVA_HODNOTA", "POZNAMKA",
            ])
        for _rowid, nove_id, nazev in prirazeno:
            info = podle_jmena.get(nazev, {})
            w.writerow([
                tabulka, "prideleno ID", nazev, info.get("LEVEL", ""),
                "", nove_id, "taxon nemel vyplnene ID",
            ])
        for _rowid, parent_id, nazev, jmeno_rodice in doplneno:
            info = podle_jmena.get(nazev, {})
            w.writerow([
                tabulka, "doplneno PARENT_ID", nazev, info.get("LEVEL", ""),
                "", parent_id, f"rodic dohledan podle jmena: {jmeno_rodice}",
            ])
        for nazev, rodic, uroven, duvod in nedoplneno:
            w.writerow([
                tabulka, "NEDOPLNENO", nazev, uroven, "", "",
                f"rodic '{rodic}': {duvod}",
            ])


def oprav(db_path, tabulka, zapsat=False, od=NOVE_ID_OD, limit_vypisu=100,
          report=None):
    conn = sqlite3.connect(db_path)
    try:
        sloupce = [r[1] for r in conn.execute(f"PRAGMA table_info({tabulka})")]
        if not sloupce:
            print(f"Tabulka {tabulka} v databazi neni - preskoceno.")
            return 0
        for nutny in ("ID", "NAME", "PARENT", "PARENT_ID"):
            if nutny not in sloupce:
                print(f"Tabulka {tabulka} nema sloupec {nutny} - preskoceno.")
                return 0

        radky, podle_jmena = nacti_stav(conn, tabulka)
        bez_id = [r for r in radky if r["ID"] is None]
        bez_pid_pred = [r for r in radky if r["PARENT_ID"] is None]

        print(f"\n{'='*70}")
        print(f"{tabulka}: {len(radky)} taxonu")
        print(f"  bez ID:        {len(bez_id)}")
        print(f"  bez PARENT_ID: {len(bez_pid_pred)}")

        if not bez_id and not bez_pid_pred:
            print("  Neni co doplnovat.")
            return 0

        namitky = zkontroluj_bezpecnost(conn, tabulka, bez_id)
        if namitky:
            print("\n  ZAPIS ODMITNUT - taxony bez ID jsou pouzite:")
            for n in namitky:
                print(f"    {n}")
            return 1

        prirazeno = priradit_id(radky, od)
        doplneno, nedoplneno = doplnit_parent_id(radky, podle_jmena)
        cykly = zkontroluj_cykly(radky, podle_jmena)

        print(f"\n  prideleno novych ID:  {len(prirazeno)}")
        if prirazeno:
            print(f"    rozsah {prirazeno[0][1]} - {prirazeno[-1][1]}")
        print(f"  doplneno PARENT_ID:   {len(doplneno)}")
        print(f"  zustava nedoplneno:   {len(nedoplneno)}")
        print(f"  nejhlubsi rodokmen:   {hloubka_rodokmenu(radky)} urovni")
        if cykly:
            print(f"  POZOR - cyklicky rodokmen u {len(cykly)} taxonu: "
                  f"{', '.join(cykly[:5])}")

        if nedoplneno:
            print(f"\n  TAXONY BEZ PARENT_ID PO OPRAVE:")
            print(f"  {'taxon':45s} {'uroven':8s} {'rodic':35s} duvod")
            print(f"  {'-'*45} {'-'*8} {'-'*35} {'-'*40}")
            for nazev, rodic, uroven, duvod in nedoplneno[:limit_vypisu]:
                print(f"  {str(nazev)[:45]:45s} {str(uroven)[:8]:8s} "
                      f"{str(rodic)[:35]:35s} {duvod}")
            if len(nedoplneno) > limit_vypisu:
                print(f"  ... a dalsich {len(nedoplneno) - limit_vypisu}")
        else:
            print("\n  Vsechny taxony maji po oprave vyplnene PARENT_ID.")

        if report:
            zapis_report(report, tabulka, prirazeno, doplneno, nedoplneno,
                         podle_jmena)
            print(f"  Prehled zmen zapsan do {report}")

        if not zapsat:
            print("\n  (nahled - pro zapis pouzijte --zapsat)")
            return 0

        for rowid, nove_id, _ in prirazeno:
            conn.execute(
                f"UPDATE {tabulka} SET ID = ? WHERE rowid = ?", (nove_id, rowid)
            )
        for rowid, parent_id, _, _ in doplneno:
            conn.execute(
                f"UPDATE {tabulka} SET PARENT_ID = ? WHERE rowid = ?",
                (parent_id, rowid),
            )
        conn.commit()
        print(f"\n  Zapsano do databaze.")
        return 0

    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="cesta k databazi")
    p.add_argument("--tabulka", action="append",
                   help="ktery taxalist opravit (lze opakovat); vychozi: vsechny")
    p.add_argument("--zapsat", action="store_true",
                   help="skutecne zapsat zmeny (jinak jen nahled)")
    p.add_argument("--od", type=int, default=NOVE_ID_OD,
                   help=f"od jakeho cisla pridelovat ID (vychozi {NOVE_ID_OD})")
    p.add_argument("--vypis", type=int, default=100,
                   help="kolik nedoplnenych taxonu vypsat")
    p.add_argument("--primo", action="store_true",
                   help="zapisovat primo do databaze misto pres docasnou kopii")
    p.add_argument("--report", help="ulozit prehled zmen do CSV souboru")
    args = p.parse_args()

    tabulky = args.tabulka or VYCHOZI_TABULKY

    if not args.zapsat:
        navrat = 0
        for tabulka in tabulky:
            navrat |= oprav(args.db, tabulka, False, args.od, args.vypis,
                            args.report)
        print()
        sys.exit(navrat)

    zaloha = f"{args.db}.pred_opravou_taxalistu_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(args.db, zaloha)
    print(f"Zaloha: {zaloha}")

    # SQLite si na sitovych a FUSE discich (OneDrive, ownCloud, sitove disky)
    # neporadi se zamky a journalem - zapis skonci chybou "disk I/O error"
    # a v adresari zustane rozpracovany soubor -journal. Upravy proto delame
    # na docasne kopii v lokalnim adresari a hotovy soubor pak zkopirujeme
    # zpatky jednim tahem.
    import os
    import tempfile

    if args.primo:
        pracovni = args.db
    else:
        popisovac, pracovni = tempfile.mkstemp(suffix=".db", prefix="lulan_oprava_")
        os.close(popisovac)
        shutil.copy2(args.db, pracovni)
        print(f"Pracovni kopie: {pracovni}")

    navrat = 0
    try:
        for tabulka in tabulky:
            navrat |= oprav(pracovni, tabulka, True, args.od, args.vypis,
                            args.report)

        if not args.primo:
            if navrat == 0:
                shutil.copy2(pracovni, args.db)
                print(f"\nHotovy soubor zkopirovan zpet do {args.db}")
            else:
                print("\nKvuli namitkam nebylo nic zapsano zpet.")
    finally:
        if not args.primo and os.path.exists(pracovni):
            os.remove(pracovni)

    print()
    sys.exit(navrat)


if __name__ == "__main__":
    main()
