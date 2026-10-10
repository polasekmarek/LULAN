"""
Kontrola `taxalist_ryby` proti Tabulce 4 metodiky a proti datum vzorku.

Ve vychozim stavu skript NIC NEMENI - jen vypisuje, co je potreba doplnit.
Zarazeni taxonu je odborne rozhodnuti, ne technikalie.

Prepinac `--doplnit` zapise priznaky z tabulky DOPLNIT nize. Ta obsahuje
jen to, co odsouhlasil zadavatel; neni to nahrada za aktualizaci taxalistu.

Hleda tri veci:

  1. **taxony vzorku bez priznaku** - po vyreseni synonym nemaji ani jeden
     z priznaku R / EL / I, takze do zadne metriky nevstoupi;
  2. **taxony z Tab. 4, ktere v taxalistu chybi** nebo tam jsou bez priznaku;
  3. **taxony s priznakem, ktere Tab. 4 nezna** - obvykle legitimni rozpis
     souhrnnych taxonu (Gobio sp. -> jednotlive druhy), ale stoji za pohled.

Proc na tom zalezi
------------------
Taxon bez priznaku do metrik nevstoupi, ale do celkove abundance ano.
U metrik ND1 a ND2 to skore TISE ZVYSUJE: vzorek slozeny vyhradne
z neskorovaneho druhu vypada jako "zadne nezadouci taxony" a obe metriky
dostanou plny pocet bodu. Vzorky RV_082 a RV_220 tak vychazely na CZI 0,25
misto 0.

Vypocet na to nove upozorni v poznamce vysledku - viz
`ryby_metriky.bez_priznaku()`.

Pouziti:
    python _tools/oprava_taxalist_ryby.py              # jen kontrola
    python _tools/oprava_taxalist_ryby.py --doplnit    # zapise priznaky
    python _tools/oprava_taxalist_ryby.py --db jina.db
"""

import argparse
import collections
import os
import re
import sqlite3
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
METODIKA = os.path.join(KOREN, "metodiky", "OOV_hodnoceni_ryby_20191231.pdf")

#: Strany PDF (od nuly), na kterych je Tabulka 4.
STRANY_TAB4 = (13, 14)

#: Priznaky, ktere se maji doplnit prepinacem --doplnit.
#: {vedecke_jmeno: (cesky_nazev, {sloupec: hodnota}, zduvodneni)}
#:
#: Tab. 4 metodiky (Janac a kol. 2019) tyto druhy nevede. Doplneni je proto
#: rozhodnuti nad ramec metodiky a musi ho odsouhlasit zadavatel.
DOPLNIT = {
    "Carassius auratus": (
        "karas zlatý",
        {"EL": 1, "I": 1},
        "nepůvodní invazní druh; Tab. 4 vede jen karase stříbřitého "
        "(Carassius gibelio), karas zlatý je ale samostatný platný druh "
        "se stejným ekologickým zařazením",
    ),
}

#: Radek Tab. 4: cesky nazev, vedecky nazev, pak krizky ve sloupcich
#: R / EL / I / A-G.
VZOR_TAB4 = re.compile(
    r"^(.+?)\s+([A-Z][a-z]+(?:\s+(?:sp\.|[a-z]+))(?:/[A-Za-z. ]+)?)\s+"
    r"((?:X\s*)+(?:[A-G]\s*)*)$"
)


def nacti_tabulku4():
    """Vytezi seznam skorujicich taxonu z metodiky.

    Returns:
        dict {vedecke_jmeno: [priznaky]}; prazdny dict, kdyz PDF neni
    """
    if not os.path.exists(METODIKA):
        return {}
    try:
        import pdfplumber
    except ImportError:
        print("(pdfplumber není nainstalován, kontrola proti Tab. 4 se "
              "přeskočí)")
        return {}

    tab = {}
    with pdfplumber.open(METODIKA) as pdf:
        for i in STRANY_TAB4:
            for radek in (pdf.pages[i].extract_text() or "").split("\n"):
                m = VZOR_TAB4.match(radek.strip())
                if m:
                    tab[m.group(2).strip()] = m.group(3).split()
    return tab


def taxony_bez_priznaku(db_path):
    """Taxony vzorku ryb, ktere po vyreseni synonym nemaji priznak.

    Returns:
        dict {jmeno: {"vzorku": n, "jedincu": x, "priklady": [...]}}
    """
    from PyQt6.QtSql import QSqlDatabase

    from calc_index.common import nacti_taxalist, vyres_synonyma
    from calc_index.ryby_metriky import TRAIT_SLOUPCE, nositel_priznaku

    db = QSqlDatabase.addDatabase("QSQLITE", "kontrola_ryby")
    db.setDatabaseName(db_path)
    if not db.open():
        raise SystemExit(f"Databázi {db_path} nelze otevřít")
    taxalist = nacti_taxalist(db, "taxalist_ryby", TRAIT_SLOUPCE)
    by_name, by_id = taxalist["by_name"], taxalist["by_id"]
    db.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    nalez = collections.defaultdict(
        lambda: {"vzorku": 0, "jedincu": 0.0, "priklady": []})

    for r in conn.execute(
            "SELECT d.name, d.val, d.sample FROM data d "
            "JOIN samples s ON d.sample = s.SAMPLE_ID AND s.TYP = 'RYBY'"):
        data = vyres_synonyma(
            [{"taxon_name": r["name"], "abundance": r["val"] or 0}], by_name)
        if not data:
            klic = f"{r['name']} (v taxalistu vůbec není)"
            zaznam = nalez[klic]
            zaznam["vzorku"] += 1
            zaznam["jedincu"] += r["val"] or 0
            if len(zaznam["priklady"]) < 3:
                zaznam["priklady"].append(r["sample"])
            continue
        for taxon_id, abundance in data.items():
            if any(nositel_priznaku(taxon_id, s, by_id)
                   for s in ("R", "EL", "I")):
                continue
            info = by_id.get(taxon_id) or {}
            zaznam = nalez[info.get("name", str(taxon_id))]
            zaznam["vzorku"] += 1
            zaznam["jedincu"] += abundance or 0
            if len(zaznam["priklady"]) < 3:
                zaznam["priklady"].append(r["sample"])
    conn.close()
    return nalez


def porovnej_s_tabulkou4(db_path, tab4):
    """Porovna taxalist s Tabulkou 4 metodiky."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tl = {r["NAME"]: r for r in conn.execute("SELECT * FROM taxalist_RYBY")}
    conn.close()

    s_priznakem = {n for n, r in tl.items()
                   if any(r[k] for k in ("R", "EL", "I"))}
    return {
        "chybi": sorted(n for n in tab4 if n not in tl),
        "bez_priznaku": sorted(n for n in tab4
                               if n in tl and n not in s_priznakem),
        "navic": sorted(s_priznakem - set(tab4)),
        "pocet_tab4": len(tab4),
        "pocet_priznak": len(s_priznakem),
    }


def doplnit_priznaky(db_path, jen_kontrola=False):
    """Zapise priznaky z tabulky DOPLNIT; vraci seznam popisu zmen."""
    conn = sqlite3.connect(db_path)
    zmeny = []
    try:
        for jmeno, (cesky, priznaky, duvod) in DOPLNIT.items():
            r = conn.execute(
                "SELECT " + ", ".join(priznaky) +
                " FROM taxalist_RYBY WHERE NAME = ?", (jmeno,)).fetchone()
            if r is None:
                zmeny.append(f"CHYBA: {jmeno} v taxalistu není")
                continue
            if all(v for v in r):
                continue
            popis = ", ".join(f"{k} = {v}" for k, v in priznaky.items())
            zmeny.append(f"{jmeno} ({cesky}): {popis}\n      {duvod}")
            if not jen_kontrola:
                conn.execute(
                    "UPDATE taxalist_RYBY SET "
                    + ", ".join(f"{k} = ?" for k in priznaky)
                    + " WHERE NAME = ?",
                    list(priznaky.values()) + [jmeno])
        if not jen_kontrola:
            conn.commit()
    finally:
        conn.close()
    return zmeny


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--doplnit", action="store_true",
                   help="zapsat příznaky z tabulky DOPLNIT do taxalistu")
    args = p.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"Databáze nenalezena: {args.db}")

    zmeny = doplnit_priznaky(args.db, jen_kontrola=not args.doplnit)
    if zmeny:
        print("=== 0. Doplnění příznaků ===")
        print("    Zapsáno:" if args.doplnit
              else "    Chybí (zapíše přepínač --doplnit):")
        for z in zmeny:
            print(f"    {z}")
        print()

    print("=== 1. Taxony ve vzorcích ryb bez příznaku R / EL / I ===")
    print("    (do metrik nevstupují, ale do celkové abundance ano —")
    print("     u ND1 a ND2 tím tiše zvyšují skóre)\n")
    nalez = taxony_bez_priznaku(args.db)
    if not nalez:
        print("    žádné — všechny taxony vzorků mají příznak")
    for jmeno, z in sorted(nalez.items(), key=lambda x: -x[1]["vzorku"]):
        print(f"    {jmeno:34s} {z['vzorku']:4d}× ve vzorcích, "
              f"{z['jedincu']:.0f} jedinců   např. {', '.join(z['priklady'])}")

    tab4 = nacti_tabulku4()
    if not tab4:
        return 0

    print(f"\n=== 2. Taxalist proti Tabulce 4 metodiky ===")
    v = porovnej_s_tabulkou4(args.db, tab4)
    print(f"    Tab. 4 metodiky:            {v['pocet_tab4']} taxonů")
    print(f"    taxalist s příznakem R/EL/I: {v['pocet_priznak']} taxonů\n")
    print(f"    v Tab. 4, ale v taxalistu chybí: "
          f"{', '.join(v['chybi']) if v['chybi'] else 'žádný'}")
    print(f"    v Tab. 4, ale bez příznaku:      "
          f"{', '.join(v['bez_priznaku']) if v['bez_priznaku'] else 'žádný'}")
    print(f"\n    s příznakem, ale nejsou v Tab. 4 ({len(v['navic'])}) —")
    print(f"    obvykle rozpis souhrnných taxonů (Gobio sp. → druhy):")
    for n in v["navic"]:
        print(f"       {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
