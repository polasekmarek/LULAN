"""
Zmensi databazi na ukazkovou sadu vzorku.

Databaze dodavana s programem nema byt archivem dat - staci, kdyz na ni
jde vyzkouset, ze vypocet funguje. Skript proto vybere z kazde slozky
nekolik vzorku a zbytek smaze.

Jak se vybira
-------------
Cilem je, aby ukazkova sada pokryla co nejvic ruznych vetvi metodiky,
ne aby byla nahodna. Kandidati se proto bodujou:

* Vzorek musi mit taxonomicka data a jeho lokalita musi patrit k utvaru,
  ktery databaze zna - jinak by se nevyhodnotil a v ukazce by byl k nicemu.
* Prednost ma vzorek z utvaru se zvlastni metodikou (vysychavy tok,
  nebroditelna velka reka, silne ovlivneny utvar). Techto vzorku je
  v databazi malo a prave na nich se pozna, ze vyber metodiky funguje.
* Prednost ma profil, kde je vic slozek najednou - na takovem utvaru je
  videt i slouceni slozek do celkoveho hodnoceni.
* Kazdy profil se v ramci slozky pouzije nejvyse jednou, aby sada
  ukazala ruzna mista, ne jedno misto v deseti terminech.
* U slozek s obema sezonami se bere pulka z jara a pulka z podzimu.

Nakonec se smazou i lokality, na kterych nezustal zadny vzorek. Prazdne
profily by v ukazkove databazi jen prekazely - vlastni si uzivatel
naimportuje nebo zalozi. Seznam utvaru a taxalisty zustavaji: utvary
jsou referencni cislenik, taxalist je vstup vypoctu.

Pouziti:
    python _tools/odlehci_databazi.py               # jen navrh
    python _tools/odlehci_databazi.py --spustit     # provede mazani
    python _tools/odlehci_databazi.py --spustit --db /cesta/k.db
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

#: Kolik vzorku nechat z kazde slozky.
POCET = 10

#: Mesice, ktere se pocitaji jako jarni a jako podzimni odber.
JARO = ("03", "04", "05")
PODZIM = ("09", "10", "11")

#: Slozky, ktere maji jen jednu sezonu - u nich se na pulku nedeli.
JEDNA_SEZONA = ("MF", "RYBY")

DOTAZ_KANDIDATU = """
SELECT s.SAMPLE_ID, s.TYP, s.LOC_ID, s.DATE,
       substr(s.DATE, 4, 2)         AS mesic,
       l.TOK, l.PROFIL, l.VU,
       u.HMWB, u.VYSYCHAVY, u.BROD,
       (SELECT count(*) FROM data d WHERE d.sample = s.SAMPLE_ID) AS taxonu
FROM samples s
JOIN loc l    ON l.KOD = s.LOC_ID
JOIN utvary u ON u.ID_UTVARU = l.VU
WHERE s.TYP = ?
ORDER BY s.SAMPLE_ID
"""


def _zvlastnosti(radek):
    """Vetve metodiky, ktere tenhle vzorek pokryva."""
    zvl = []
    if radek["VYSYCHAVY"] == "I":
        zvl.append("vysychavý")
    if radek["BROD"] == "NEBROD":
        zvl.append("nebroditelný")
    if radek["HMWB"] == "S":
        zvl.append("silně ovlivněný")
    if radek["HMWB"] == "U":
        zvl.append("umělý")
    return zvl


def nacti_kandidaty(conn, typ):
    conn.row_factory = sqlite3.Row
    radky = [dict(r) for r in conn.execute(DOTAZ_KANDIDATU, (typ,))]
    return [r for r in radky if r["taxonu"] > 0]


def _vyber_ze_sady(kandidati, kolik, pouzite_profily, slozek_na_profilu):
    """Vybere `kolik` vzorku, kazdy z jineho profilu.

    Poradi rozhoduji tri veci, v tomto poradi:
      1. kolik vetvi metodiky vzorek pokryva (vic = lip)
      2. na kolika slozkach profil figuruje (vic = lip)
      3. pocet taxonu (vic = lip, aby ukazka nebyla prazdna)
    """
    serazeni = sorted(
        kandidati,
        key=lambda r: (len(_zvlastnosti(r)),
                       slozek_na_profilu.get(r["LOC_ID"], 0),
                       r["taxonu"]),
        reverse=True,
    )
    vybrane = []
    for r in serazeni:
        if len(vybrane) >= kolik:
            break
        if r["LOC_ID"] in pouzite_profily:
            continue
        vybrane.append(r)
        pouzite_profily.add(r["LOC_ID"])
    return vybrane


def vyber(conn, typ, kolik=POCET):
    """Vybere ukazkove vzorky jedne slozky."""
    kandidati = nacti_kandidaty(conn, typ)
    if not kandidati:
        return []

    # Na kolika slozkach ten ktery profil figuruje.
    slozek = {}
    for loc, n in conn.execute(
            "SELECT LOC_ID, count(DISTINCT TYP) FROM samples GROUP BY LOC_ID"):
        slozek[loc] = n

    pouzite = set()
    if typ in JEDNA_SEZONA:
        return _vyber_ze_sady(kandidati, kolik, pouzite, slozek)

    jaro = [r for r in kandidati if r["mesic"] in JARO]
    podzim = [r for r in kandidati if r["mesic"] in PODZIM]

    vybrane = _vyber_ze_sady(jaro, kolik // 2, pouzite, slozek)
    vybrane += _vyber_ze_sady(podzim, kolik - len(vybrane), pouzite, slozek)

    # Kdyby jedna sezona nestacila, dorovna se cimkoli zbylym.
    if len(vybrane) < kolik:
        zbytek = [r for r in kandidati
                  if r["SAMPLE_ID"] not in {v["SAMPLE_ID"] for v in vybrane}]
        vybrane += _vyber_ze_sady(zbytek, kolik - len(vybrane), pouzite, slozek)
    return vybrane


def sezona(radek):
    if radek["mesic"] in JARO:
        return "jaro"
    if radek["mesic"] in PODZIM:
        return "podzim"
    return "léto"


def vypis_navrh(vyber_podle_slozky):
    for typ, radky in vyber_podle_slozky.items():
        print(f"\n### {typ} — {len(radky)} vzorků")
        if not radky:
            print("   (žádný vhodný vzorek)")
            continue
        print(f"   {'vzorek':<22} {'sezóna':<7} {'datum':<11} "
              f"{'taxonů':>6}  {'útvar':<10} profil")
        for r in sorted(radky, key=lambda x: (sezona(x), x["SAMPLE_ID"])):
            zvl = _zvlastnosti(r)
            popis = f"{r['TOK'] or '?'} – {r['PROFIL'] or r['LOC_ID']}"
            if zvl:
                popis += f"  [{', '.join(zvl)}]"
            print(f"   {r['SAMPLE_ID']:<22} {sezona(r):<7} {r['DATE']:<11} "
                  f"{r['taxonu']:>6}  {r['VU'] or '?':<10} {popis}")


#: Tabulky navazane na vzorek a nazev sloupce s jeho kodem. Poradi je
#: zamerne: nejdriv navazana data, az nakonec same vzorky.
TABULKY_VZORKU = (
    ("data", "sample"),             # taxony a jejich abundance
    ("adjust_table", "sample"),     # abundance po taxonomickych upravach
    ("predict_taxa", "sample_id"),  # predikce B-indexu
    ("results", "SAMPLE_ID"),       # vysledky metrik
    ("results_class", "sample"),    # zatrideni
    ("samples", "SAMPLE_ID"),       # hlavicky vzorku
)


def _existuje(conn, tabulka):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
        "AND lower(name) = lower(?)", (tabulka,)).fetchone() is not None


def zjisti_dopady(conn, ponechat):
    """Kolik ceho se smaze."""
    otazniky = ", ".join("?" * len(ponechat))
    dopady = {}
    for tabulka, sloupec in TABULKY_VZORKU:
        if not _existuje(conn, tabulka):
            continue
        dopady[tabulka] = conn.execute(
            f"SELECT count(*) FROM {tabulka} "
            f"WHERE {sloupec} NOT IN ({otazniky})", ponechat).fetchone()[0]

    dopady["loc (bez vzorků)"] = conn.execute(
        f"SELECT count(*) FROM loc WHERE KOD NOT IN "
        f"(SELECT LOC_ID FROM samples WHERE SAMPLE_ID IN ({otazniky}))",
        ponechat).fetchone()[0]
    dopady["results_year"] = conn.execute(
        "SELECT count(*) FROM results_year").fetchone()[0]
    return dopady


def smaz(conn, ponechat):
    """Smaze vse, co k ponechanym vzorkum nepatri.

    Maze se i seznam lokalit - zustanou jen ty, kde nejaky ponechany
    vzorek je. Prazdne profily by v ukazkove databazi jen prekazely;
    uzivatel si vlastni stejne naimportuje nebo zalozi.

    Utvary a taxalisty zustavaji. Seznam utvaru je referencni cislenik
    vsech vodnich utvaru CR, ktery si uzivatel doplnovat nema, a taxalist
    je vstup vypoctu - bez nej by program nefungoval vubec.
    """
    otazniky = ", ".join("?" * len(ponechat))
    for tabulka, sloupec in TABULKY_VZORKU:
        if not _existuje(conn, tabulka):
            continue
        conn.execute(
            f"DELETE FROM {tabulka} WHERE {sloupec} NOT IN ({otazniky})",
            ponechat)

    # Az po smazani vzorku: lokalita je "obsazena", kdyz na ni zbyl vzorek.
    conn.execute(
        "DELETE FROM loc WHERE KOD NOT IN (SELECT LOC_ID FROM samples)")

    # Rocni souhrny se pocitaji z vysledku, ktere uz nejsou - at nezustanou
    # viset cisla, ke kterym nesedi zadna data.
    conn.execute("DELETE FROM results_year")
    conn.commit()


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--pocet", type=int, default=POCET,
                   help=f"kolik vzorku nechat z kazde slozky (vychozi {POCET})")
    p.add_argument("--spustit", action="store_true",
                   help="opravdu mazat; bez teto volby se jen vypise navrh")
    p.add_argument("--bez-zalohy", action="store_true",
                   help="nevyrabet zalohu (uz ji mam jinde)")
    args = p.parse_args()

    if not os.path.exists(args.db):
        print(f"Databáze neexistuje: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        vyber_podle_slozky = {
            typ: vyber(conn, typ, args.pocet)
            for typ in ("MZB", "FB", "MF", "RYBY")
        }
        vypis_navrh(vyber_podle_slozky)

        # Kolik profilu nese vic slozek najednou - na nich je videt
        # slouceni slozek do celkoveho hodnoceni utvaru.
        profily = {}
        for typ, radky in vyber_podle_slozky.items():
            for r in radky:
                profily.setdefault(r["LOC_ID"], []).append(typ)
        vicenasobne = {k: v for k, v in profily.items() if len(v) > 1}
        print(f"\n### Profily s více složkami — {len(vicenasobne)} "
              f"z {len(profily)}")
        for loc, typy in sorted(vicenasobne.items(),
                                key=lambda x: (-len(x[1]), x[0])):
            popis = conn.execute(
                "SELECT TOK, PROFIL FROM loc WHERE KOD = ?", (loc,)).fetchone()
            print(f"   {loc:<10} {', '.join(sorted(typy)):<22} "
                  f"{popis[0] or '?'} – {popis[1] or ''}")

        ponechat = [r["SAMPLE_ID"]
                    for radky in vyber_podle_slozky.values() for r in radky]
        if not ponechat:
            print("\nNic k ponechání — mazat nebudu.", file=sys.stderr)
            return 1

        dopady = zjisti_dopady(conn, ponechat)
        print("\n### Co se smaže")
        for tabulka, n in dopady.items():
            print(f"   {tabulka:<16} {n:>7} řádků")
        print(f"\n   ponechá se {len(ponechat)} vzorků")

        if not args.spustit:
            print("\nZatím se nic nesmazalo. Provedete příkazem:")
            print("   python _tools/odlehci_databazi.py --spustit")
            return 0

        if not args.bez_zalohy:
            zaloha = args.db + ".pred_odlehcenim"
            shutil.copy2(args.db, zaloha)
            print(f"\nZáloha: {zaloha}")

        smaz(conn, ponechat)
        pred = os.path.getsize(args.db)
        conn.execute("VACUUM")
        conn.close()
        po = os.path.getsize(args.db)
        print(f"Hotovo. Velikost {pred // 1024 // 1024} MB "
              f"→ {po // 1024 // 1024} MB")
        return 0
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


if __name__ == "__main__":
    sys.exit(main())
