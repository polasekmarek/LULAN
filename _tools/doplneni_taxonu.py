"""
Napojeni taxonu ze vzorku, ktere v taxonomickem seznamu chybi.

Problem
-------
Cast jmen pouzitych v datech vzorku neni v tabulce `taxalist_mzb`. Skoro
vzdy nejde o chybejici taxon, ale o STARSI JMENO taxonu, ktery uz v seznamu
je pod novejsim nazvem:

    Cricotopus bicinctus-Gr.  ->  Cricotopus (Cricotopus) bicinctus-Gr.
    Spirosperma ferrox        ->  Spirosperma ferox
    Nemurella picteti         ->  Nemurella pictetii

Starsi zaloha `taxalist_mzb_zaloha` obsahuje stara jmena i s ID, ktere si
novejsi seznam ponechal - podle ID se tedy da stare jmeno spolehlive navazat
na nove.

Proc nestaci taxon proste pridat
--------------------------------
Pridanim vznikne DUPLICITA: tyz taxon je v seznamu dvakrat pod dvema jmeny.
Adjustacni predpisy v tabulce `adjustace` odkazuji na taxony pres ID, takze
na nove pridany zaznam s jinym ID uz nesednou - taxon se pak neslouci na
rodovou uroven a metriky poctu taxonu (pakomari, celedi, EPT Tax) vychazeji
vyssi, nez maji.

Spravne reseni je zapsat stare jmeno jako SYNONYMUM noveho taxonu. Seznam
znaci synonyma hodnotou 'SYNONYM' ve sloupci SYN a platne jmeno drzi ve
sloupci PARENT - funkce vyres_synonyma() pak vzorek namapuje na spravny
taxon i s jeho traity a adjustacnimi pravidly.

Pouziti:
    python _tools/doplneni_taxonu.py dtb/LULAN_dtb_001.db
    python _tools/doplneni_taxonu.py dtb/LULAN_dtb_001.db --zapsat
    python _tools/doplneni_taxonu.py dtb/LULAN_dtb_001.db --uklidit-duplicity
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

#: Od jakeho cisla se pridelovala ID pri drivejsim (chybnem) doplneni.
#: Zaznamy v tomto rozsahu umi skript uklidit prepinacem --uklidit-duplicity.
DUPLICITNI_ID_OD = 9_500_000_000

#: Hodnota sloupce SYN, kterou seznam znaci synonymum.
PRIZNAK_SYNONYMA = "SYNONYM"


def najdi_nenavazane(conn, tabulka="taxalist_mzb", zaloha="taxalist_mzb_zaloha"):
    """Najde jmena ze vzorku, ktera v seznamu chybi, a dohleda jejich protejsek.

    Returns:
        (synonyma, bez_protejsku) - synonyma je list dictu
        {stare_jmene, nove_jmeno, nove_id, vzorku, jedincu}
    """
    chybejici = [
        (r[0], r[1], r[2]) for r in conn.execute(f"""
            SELECT d.name,
                   COUNT(DISTINCT d.sample),
                   IFNULL(SUM(d.val), 0)
            FROM data d
            JOIN samples s ON s.SAMPLE_ID = d.sample
            WHERE s.TYP = 'MZB'
              AND d.name NOT IN (SELECT NAME FROM {tabulka})
            GROUP BY d.name
        """)
    ]

    zaloha_id = {
        r[0]: r[1] for r in conn.execute(f"SELECT NAME, ID FROM {zaloha}")
    }
    podle_id = {
        r[0]: r[1] for r in conn.execute(
            f"SELECT ID, NAME FROM {tabulka} WHERE ID IS NOT NULL"
        )
    }

    synonyma, bez = [], []
    for jmeno, vzorku, jedincu in chybejici:
        stare_id = zaloha_id.get(jmeno)
        nove_jmeno = podle_id.get(stare_id) if stare_id else None
        zaznam = {
            "stare_jmeno": jmeno, "nove_jmeno": nove_jmeno,
            "nove_id": stare_id, "vzorku": vzorku, "jedincu": jedincu,
        }
        (synonyma if nove_jmeno else bez).append(zaznam)

    synonyma.sort(key=lambda x: -x["jedincu"])
    bez.sort(key=lambda x: -x["jedincu"])
    return synonyma, bez


def uklid_duplicity(conn, tabulka="taxalist_mzb"):
    """Smaze zaznamy vlozene drivejsim (chybnym) doplnenim.

    Returns:
        (smazano, jmena)
    """
    jmena = [
        r[0] for r in conn.execute(
            f"SELECT NAME FROM {tabulka} WHERE ID >= ?", (DUPLICITNI_ID_OD,)
        )
    ]
    conn.execute(f"DELETE FROM {tabulka} WHERE ID >= ?", (DUPLICITNI_ID_OD,))
    conn.commit()
    return len(jmena), jmena


def zapis_synonyma(conn, synonyma, tabulka="taxalist_mzb"):
    """Vlozi stara jmena jako synonyma navazana na platny taxon."""
    sloupce = {r[1] for r in conn.execute(f"PRAGMA table_info({tabulka})")}
    pouzita = {
        r[0] for r in conn.execute(
            f"SELECT ID FROM {tabulka} WHERE ID IS NOT NULL"
        )
    }
    dalsi = DUPLICITNI_ID_OD

    vlozeno = 0
    for s in synonyma:
        while dalsi in pouzita:
            dalsi += 1
        pouzita.add(dalsi)

        data = {
            "ID": dalsi,
            "NAME": s["stare_jmeno"],
            "PARENT": s["nove_jmeno"],
            "PARENT_ID": s["nove_id"],
            "SYN": PRIZNAK_SYNONYMA,
        }
        if "LEVEL" in sloupce:
            data["LEVEL"] = conn.execute(
                f"SELECT LEVEL FROM {tabulka} WHERE ID = ?", (s["nove_id"],)
            ).fetchone()[0]

        conn.execute(
            f"INSERT INTO {tabulka} ({', '.join(f'[{k}]' for k in data)}) "
            f"VALUES ({', '.join('?' * len(data))})",
            list(data.values()),
        )
        vlozeno += 1
        dalsi += 1

    conn.commit()
    return vlozeno


def spust(db_path, zapsat=False, uklidit=False):
    conn = sqlite3.connect(db_path)
    try:
        if uklidit:
            pocet, jmena = uklid_duplicity(conn) if zapsat else (
                len([r for r in conn.execute(
                    "SELECT NAME FROM taxalist_mzb WHERE ID >= ?",
                    (DUPLICITNI_ID_OD,))]), []
            )
            print(f"Duplicitnich zaznamu z drivejsiho doplneni: {pocet}")
            if zapsat:
                print(f"  smazano {pocet}")

        synonyma, bez = najdi_nenavazane(conn)

        print(f"\nJmen ze vzorku, ktera v taxalist_mzb chybi: "
              f"{len(synonyma) + len(bez)}")
        print(f"  z toho jde o starsi nazev existujiciho taxonu: {len(synonyma)}")
        print(f"  bez protejsku v seznamu:                       {len(bez)}")

        if synonyma:
            print(f"\n  {'stare jmeno':40s} -> {'platne jmeno':42s} {'vzorku':>7s}")
            print(f"  {'-'*40}    {'-'*42} {'-'*7}")
            for s in synonyma[:15]:
                print(f"  {s['stare_jmeno'][:40]:40s} -> "
                      f"{s['nove_jmeno'][:42]:42s} {s['vzorku']:7d}")
            if len(synonyma) > 15:
                print(f"  ... a dalsich {len(synonyma) - 15}")

        if bez:
            print("\n  Bez protejsku (nutno resit rucne):")
            for s in bez[:10]:
                print(f"    {s['stare_jmeno'][:44]:46s} "
                      f"{s['vzorku']:4d} vzorku, {s['jedincu']:.0f} jedincu")

        if not zapsat:
            print("\n  (nahled - pro zapis pouzijte --zapsat)")
            return 0

        if synonyma:
            vlozeno = zapis_synonyma(conn, synonyma)
            print(f"\n  Zapsano {vlozeno} synonym.")
        return 0
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("db")
    p.add_argument("--zapsat", action="store_true")
    p.add_argument("--uklidit-duplicity", action="store_true",
                   dest="uklidit",
                   help="smazat zaznamy vlozene drivejsim chybnym doplnenim")
    p.add_argument("--primo", action="store_true")
    args = p.parse_args()

    if not args.zapsat:
        sys.exit(spust(args.db, False, args.uklidit))

    zaloha = f"{args.db}.pred_synonymy_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(args.db, zaloha)
    print(f"Zaloha: {zaloha}")

    if args.primo:
        pracovni = args.db
    else:
        fd, pracovni = tempfile.mkstemp(suffix=".db", prefix="lulan_syn_")
        os.close(fd)
        shutil.copy2(args.db, pracovni)

    try:
        navrat = spust(pracovni, True, args.uklidit)
        if not args.primo and navrat == 0:
            shutil.copy2(pracovni, args.db)
            print(f"Hotovy soubor zkopirovan zpet do {args.db}")
    finally:
        if not args.primo and os.path.exists(pracovni):
            os.remove(pracovni)
    sys.exit(navrat)


if __name__ == "__main__":
    main()
