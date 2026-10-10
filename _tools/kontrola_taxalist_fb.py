"""
Kontrola `taxalist_FB` proti zaloze `taxalist_fb_zaloha`.

Ve vychozim stavu skript NIC NEMENI - jen vypisuje rozdily. Zarazeni
taxonu a jeho autekologicke hodnoty jsou odborny udaj, ne technikalie.

Prepinac `--srovnat` prepise MSZS a MSZG zivneho taxalistu hodnotami ze
zalohy, a to jen u taxonu, ktere se skutecne vyskytuji ve vzorcich.
Ostatnich rozdilu se nedotkne.

Proc na tom zalezi
------------------
Saprobni index se pocita jako

    I = sum(h * w * S) / sum(h * w)

kde S je MSZS a w je MSZG. Kdyz taxalist prisoudi hodnoty taxonu, ktery
je oficialne nema (nebo naopak nema hodnoty u taxonu, ktery je ma), index
se posune, aniz by na to vypocet jakkoli upozornil - vzorec je porad
spravny, jen dostane jina vstupni data.

Konkretne: pri porovnani 409 vzorku s IS ARROW se index rozchazel
u 66 vzorku. Vsechny odchylky slo bez zbytku vysvetlit osmi taxony:

    sedm taxonu ma v zivem taxalistu MSZS/MSZG, ale v zaloze (a v ARROW)
    ne, takze je LULAN skoroval navic:

        Surirella lacrimula        Stauridium tetras
        Fragilaria recapitellata   Lepocinclis acus
        Nitzschia kuetzingii       Gyrosigma scalproides
                                   Eunotia arcus

    a jeden taxon v zivem taxalistu vubec neni, prestoze ho zaloha vede
    se saprobnim indexem 0,6 a vahou 4:

        Pinnularia neomaior

Po srovnani se zalohou sedi index i EQR u vsech 409 vzorku presne.

Pouziti:
    python _tools/kontrola_taxalist_fb.py            # jen kontrola
    python _tools/kontrola_taxalist_fb.py --srovnat  # zapise hodnoty ze zalohy
    python _tools/kontrola_taxalist_fb.py --vse      # vypise i taxony mimo vzorky
"""

import argparse
import os
import sqlite3
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")

TABULKA = "taxalist_FB"
ZALOHA = "taxalist_fb_zaloha"

#: Sloupce, ktere vstupuji do saprobniho indexu.
TRAITY = ("MSZS", "MSZG")


def nacti(conn, tabulka):
    """Vrati {NAME: {sloupec: hodnota}} pro sledovane traity."""
    sl = ", ".join(TRAITY)
    return {
        r[0]: dict(zip(TRAITY, r[1:]))
        for r in conn.execute(f"SELECT NAME, {sl} FROM {tabulka}")
    }


def skoruje(hodnoty):
    """Ma taxon obe hodnoty potrebne pro saprobni index?"""
    return hodnoty is not None and all(
        hodnoty.get(s) is not None for s in TRAITY
    )


def rozdily(conn, jen_ve_vzorcich=True):
    """Porovna zivy taxalist se zalohou.

    Returns:
        list dictu {taxon, nyni, zaloha, vzorku, druh}
    """
    ziva, zal = nacti(conn, TABULKA), nacti(conn, ZALOHA)
    vyskyt = {
        r[0]: r[1] for r in conn.execute(
            "SELECT d.name, COUNT(DISTINCT d.sample) FROM data d "
            "JOIN samples s ON d.sample = s.SAMPLE_ID AND s.TYP = 'FB' "
            "GROUP BY d.name"
        )
    }

    nalez = []
    for jmeno in set(ziva) | set(zal):
        a, b = ziva.get(jmeno), zal.get(jmeno)
        if skoruje(a) == skoruje(b) and (a or {}) == (b or {}):
            continue
        if skoruje(a) and not skoruje(b):
            druh = "LULAN skóruje navíc"
        elif skoruje(b) and not skoruje(a):
            druh = "LULAN neskóruje, záloha ano"
        elif skoruje(a) and skoruje(b):
            druh = "odlišné hodnoty"
        else:
            continue
        n = vyskyt.get(jmeno, 0)
        if jen_ve_vzorcich and not n:
            continue
        nalez.append({"taxon": jmeno, "nyni": a, "zaloha": b,
                      "vzorku": n, "druh": druh})
    return sorted(nalez, key=lambda x: (-x["vzorku"], x["taxon"]))


def _sloupce(conn, tabulka):
    """Nazvy sloupcu tabulky."""
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabulka})")]


def _sjednot_parent(conn, jmeno):
    """Prevede PARENT prevzaty ze zalohy na konvenci ziveho taxalistu.

    Zaloha odkazuje na nadrazeny taxon ciselnym ID, zivy taxalist jmenem
    ("Pinnularia sp."). Neprevedeny odkaz by vypocet hlasil jako
    nedohledatelny nadrazeny taxon.
    """
    r = conn.execute(
        f"SELECT PARENT FROM {TABULKA} WHERE NAME = ?", (jmeno,)).fetchone()
    if r is None:
        return
    if conn.execute(f"SELECT 1 FROM {TABULKA} WHERE NAME = ?",
                    (str(r[0]),)).fetchone():
        return

    # Zkusi se rod odvozeny z prvniho slova jmena; pokud ani ten
    # v taxalistu neni, PARENT se nechava byt - je to jen odkaz.
    rod = f"{jmeno.split()[0]} sp."
    if conn.execute(f"SELECT 1 FROM {TABULKA} WHERE NAME = ?",
                    (rod,)).fetchone():
        conn.execute(f"UPDATE {TABULKA} SET PARENT = ? WHERE NAME = ?",
                     (rod, jmeno))


def srovnej(conn, nalez):
    """Prepise MSZS a MSZG hodnotami ze zalohy; vraci pocet zmen."""
    zmen = 0
    for r in nalez:
        z = r["zaloha"]
        if z is None:
            # Taxon v zaloze vubec neni - hodnoty se nuluji, aby do
            # vypoctu nevstupoval. Radek se nemaze, muze mit potomky.
            z = {s: None for s in TRAITY}
        if r["nyni"] is None:
            # Cely radek se prebira ze zalohy - jinak by chybely povinne
            # sloupce (PARENT, LEVEL) a vlozeni by neproslo.
            spolecne = [s for s in _sloupce(conn, TABULKA)
                        if s in _sloupce(conn, ZALOHA) and s != "ID"]
            conn.execute(
                f"INSERT INTO {TABULKA} ({', '.join(spolecne)}) "
                f"SELECT {', '.join(spolecne)} FROM {ZALOHA} WHERE NAME = ?",
                (r["taxon"],))
            _sjednot_parent(conn, r["taxon"])
        else:
            conn.execute(
                f"UPDATE {TABULKA} SET "
                + ", ".join(f"{s} = ?" for s in TRAITY)
                + " WHERE NAME = ?",
                [z[s] for s in TRAITY] + [r["taxon"]])
        zmen += 1
    conn.commit()
    return zmen


def zapis(h):
    if h is None:
        return "chybí v tabulce"
    return ", ".join(
        f"{s}={'—' if h.get(s) is None else h[s]}" for s in TRAITY)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--srovnat", action="store_true",
                   help="přepsat MSZS/MSZG hodnotami ze zálohy")
    p.add_argument("--vse", action="store_true",
                   help="vypsat i taxony, které se ve vzorcích nevyskytují")
    args = p.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"Databáze nenalezena: {args.db}")

    conn = sqlite3.connect(args.db)
    tabulky = {r[0].lower() for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if ZALOHA.lower() not in tabulky:
        raise SystemExit(f"Záloha {ZALOHA} v databázi není")

    nalez = rozdily(conn, jen_ve_vzorcich=not args.vse)
    if not nalez:
        print("Taxalist se zálohou souhlasí — žádný rozdíl v MSZS ani MSZG.")
        return 0

    print(f"Rozdílů proti záloze: {len(nalez)}"
          f"{'' if args.vse else ' (jen taxony vyskytující se ve vzorcích)'}\n")
    for r in nalez:
        print(f"  {r['taxon']}  —  {r['druh']}, {r['vzorku']} vzorků")
        print(f"      taxalist: {zapis(r['nyni'])}")
        print(f"      záloha:   {zapis(r['zaloha'])}")

    if args.srovnat:
        # Zapisuji se jen taxony ve vzorcich - u ostatnich by zasah do
        # taxalistu nemel na vysledky zadny vliv.
        k_zapisu = [r for r in nalez if r["vzorku"]]
        print(f"\nZapisuji hodnoty ze zálohy u {len(k_zapisu)} taxonů…")
        print(f"Hotovo: {srovnej(conn, k_zapisu)} řádků. "
              "Spusťte přepočet: python _tools/prepocet.py --spustit")
    else:
        print("\nNic se nezměnilo. Zápis hodnot ze zálohy: přepínač --srovnat")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
