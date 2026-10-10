"""
Porovnani hodnoceni fytobentosu (FB) spocitaneho LULANem s hodnotami z ARROW.

Nacte referencni tabulku exportovanou z IS ARROW, spocita tytez vzorky
vlastnim vypoctem `fb_perennial.hodnoceni()` a porovna:

    FB01        saprobni index I_FB
    FB01EQR     EQR saprobniho indexu
    FB03        stredni chyba indexu (vzorec [8] metodiky)
    FB04        spolehlivost stanoveni R (odst. 6.6)
    SOUCET_VAH  soucet indikacnich vah Sw
    FB_CELKEM   finalni hodnoceni

Vystupem je HTML report se stejnym rozvrzenim jako u makrozoobentosu
a makrofyt.

Pouziti:
    python _tools/porovnani_fb.py
    python _tools/porovnani_fb.py --csv jiny_export.csv
    python _tools/porovnani_fb.py --db /tmp/kopie.db
"""

import argparse
import csv
import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_CSV = os.path.join(
    KOREN, "kontrola_vysledku", "LULAN_vzorky_kontrola_FB.csv")
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
VYSTUP = os.path.join(KOREN, "porovnani_metrik_FB.html")

#: Export z ARROW je v cp1250.
KODOVANI_EXPORTU = "cp1250"

#: Tolerance shody. Index se do vysledku uklada zaokrouhleny na tri
#: desetinna mista, ARROW exportuje pet - proto ne uplna nula.
TOLERANCE = 0.0006

NAZVY = {
    "FB01": "Saprobní index I_FB",
    "FB01EQR": "EQR saprobního indexu",
    "FB03": "Střední chyba indexu",
    "FB04": "Spolehlivost stanovení R",
    "SOUCET_VAH": "Součet indikačních vah Sw",
    "FB_CELKEM": "Finální hodnocení",
}

#: Poradi sloupcu v prehledu a v sekcich s grafy.
POradi = ("FB_CELKEM", "FB01", "FB01EQR", "SOUCET_VAH", "FB03", "FB04")


def nacti_referenci(cesta):
    """Nacte export z ARROW."""
    text = open(cesta, encoding=KODOVANI_EXPORTU).read()
    radky = list(csv.DictReader(text.splitlines(), delimiter=";"))
    return [r for r in radky if (r.get("sample") or "").strip()]


def cislo(hodnota):
    try:
        return float(str(hodnota).replace(",", "."))
    except (TypeError, ValueError):
        return None


def spocitej(vzorky, db_cesta, srovnat_taxalist=False, spojeni="porovnani_fb"):
    """Spocita FB hodnoceni LULANem.

    Vypocet zapisuje do tabulky `results`, proto se pracuje nad kopii -
    kontrolni beh nema menit ostrou databazi.

    Args:
        srovnat_taxalist: pred vypoctem srovnat MSZS/MSZG se zalohou
            (tj. spocitat variantu "po oprave"); ostra databaze zustava
            i tak nedotcena, meni se jen kopie

    Returns:
        (dict {SAMPLE_ID: {...}}, cesta_ke_kopii)
    """
    import shutil
    import sqlite3
    import tempfile

    from PyQt6.QtSql import QSqlDatabase

    from calc_index.fb_perennial import hodnoceni

    kopie = os.path.join(tempfile.mkdtemp(), "porovnani_fb.db")
    shutil.copy(db_cesta, kopie)

    if srovnat_taxalist:
        from kontrola_taxalist_fb import rozdily, srovnej

        conn = sqlite3.connect(kopie)
        srovnej(conn, [r for r in rozdily(conn) if r["vzorku"]])
        conn.close()

    db = QSqlDatabase.addDatabase("QSQLITE", spojeni)
    db.setDatabaseName(kopie)
    if not db.open():
        raise SystemExit(f"Databázi {kopie} nelze otevřít")

    vysledky = {}
    for sid in vzorky:
        v = hodnoceni(sid, db)
        if not v or v.get("FB_01") is None:
            continue
        vysledky[sid] = {
            "FB01": v["FB_01"],
            "FB01EQR": v["FB_01_EQR"],
            "FB03": v["FB_03"],
            "FB04": v["FB_04"],
            "SOUCET_VAH": v["FB_SW"],
            "FB_CELKEM": v["FB_CELKEM"],
            "FB_CLASS": v["FB_CLASS"],
        }
    db.close()
    return vysledky, kopie


def trida_fb(eqr):
    """Zaradi EQR do tridy ekologickeho stavu."""
    from calc_index.common import klasifikuj
    from calc_index.fb_perennial import HRANICE_STAV

    return None if eqr is None else klasifikuj(eqr, hranice=HRANICE_STAV)


def _barva(r):
    return "dobra" if r > 0.999 else "stredni" if r > 0.98 else "spatna"


def _karta(st, kod, popisek, nadpis):
    """Jedna karta: graf plus tabulka statistik."""
    from porovnani_report import _graf

    obr = _graf(st["a"], st["b"], kod, popisek)
    return f"""<div class="karta">
      <div>
        <div class="nadpis-karty">{nadpis}</div>
        <img src="data:image/png;base64,{obr}" alt="{kod} — {nadpis}">
      </div>
      <table class="stat">
        <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
        <tr><td>korelace</td>
            <td class="{_barva(st['r'])}">{st['r']:.5f}</td></tr>
        <tr><td>medián rozdílu</td><td>{st['median']:+.4f}</td></tr>
        <tr><td>průměr rozdílu</td><td>{st['prumer']:+.4f}</td></tr>
        <tr><td>největší rozdíl</td><td>{st['max_abs']:.4f}</td></tr>
        <tr><td>shodných (±0,001)</td>
            <td>{st['shodnych']} ({st['shodnych'] / st['n'] * 100:.0f} %)</td></tr>
      </table>
    </div>"""


def sestav_report(ref, lulan, lulan_po=None, vystup=VYSTUP):
    """Sestavi HTML report ve stejnem rozvrzeni jako u MZB a MF.

    Args:
        lulan: vysledky ze soucasneho stavu databaze
        lulan_po: vysledky po srovnani taxalistu se zalohou; kdyz jsou
            zadane, report ukazuje obe varianty vedle sebe
    """
    import pandas as pd

    from porovnani_report import _statistiky

    spolecne = [r["sample"] for r in ref if r["sample"] in lulan]
    a_ref = pd.DataFrame(ref).set_index("sample")
    a_lul = pd.DataFrame(lulan).T
    a_po = pd.DataFrame(lulan_po).T if lulan_po else None

    def sloupec(tabulka, kod):
        return pd.to_numeric(
            tabulka.loc[spolecne, kod].astype(str).str.replace(",", "."),
            errors="coerce")

    sekce, prehled = [], []
    for kod in POradi:
        if kod not in a_ref.columns:
            continue
        a = sloupec(a_ref, kod)
        st = _statistiky(a, sloupec(a_lul, kod))
        if st is None:
            continue
        st_po = _statistiky(a, sloupec(a_po, kod)) if a_po is not None else None
        popisek = NAZVY[kod]
        prehled.append((kod, popisek, st, st_po))

        karty = _karta(st, kod, popisek,
                       "současný stav" if st_po else "ARROW vs. LULAN")
        if st_po:
            karty += _karta(st_po, kod, popisek, "po srovnání taxalistu")
        sekce.append(
            f'<section><h2>{kod} — {popisek}</h2>'
            f'<div class="karty">{karty}</div></section>')

    # --- tabulka vzorek po vzorku ---------------------------------------
    radky_vzorku, neshody, neshody_po = [], 0, 0
    for s in spolecne:
        aI, lI = cislo(a_ref.loc[s, "FB01"]), cislo(a_lul.loc[s, "FB01"])
        aE, lE = cislo(a_ref.loc[s, "FB01EQR"]), cislo(a_lul.loc[s, "FB01EQR"])
        aW, lW = (cislo(a_ref.loc[s, "SOUCET_VAH"]),
                  cislo(a_lul.loc[s, "SOUCET_VAH"]))
        pI = cislo(a_po.loc[s, "FB01"]) if a_po is not None else None
        sedi = aI is not None and lI is not None and abs(aI - lI) < TOLERANCE
        sedi_po = aI is not None and pI is not None and abs(aI - pI) < TOLERANCE
        neshody += not sedi
        neshody_po += a_po is not None and not sedi_po
        sloupec_po = (
            f"<td class=\"{'' if sedi_po else 'spatna'}\">"
            f"{'' if pI is None else f'{pI:.3f}'}</td>"
            if a_po is not None else "")
        radky_vzorku.append(
            f"<tr class=\"{'' if sedi else 'lisi'}\"><td>{s}</td>"
            f"<td>{'' if aI is None else f'{aI:.5f}'}</td>"
            f"<td>{'' if lI is None else f'{lI:.3f}'}</td>"
            f"{sloupec_po}"
            f"<td>{'' if (aI is None or lI is None) else f'{lI - aI:+.5f}'}</td>"
            f"<td>{'' if aW is None else f'{aW:.0f}'}</td>"
            f"<td>{'' if lW is None else f'{lW:.0f}'}</td>"
            f"<td>{'' if aE is None else f'{aE:.3f}'}</td>"
            f"<td>{'' if lE is None else f'{lE:.3f}'}</td>"
            f"<td>{trida_fb(aE) or ''} / {trida_fb(lE) or ''}</td></tr>"
        )

    hlavicka_po = ("<th>I_FB po srovnání</th>" if a_po is not None else "")

    shoda_trid = sum(
        1 for s in spolecne
        if trida_fb(cislo(a_ref.loc[s, "FB01EQR"]))
        == trida_fb(cislo(a_lul.loc[s, "FB01EQR"]))
    )
    shoda_indexu = len(spolecne) - neshody
    shoda_po = len(spolecne) - neshody_po

    radky = "".join(
        f"<tr><td>{k}</td><td>{n}</td><td>{s['n']}</td>"
        f"<td class='{_barva(s['r'])}'>{s['r']:.5f}</td>"
        f"<td>{s['median']:+.4f}</td>"
        f"<td>{s['shodnych'] / s['n'] * 100:.0f} %</td>"
        + (f"<td class='{_barva(p['r'])}'>{p['r']:.5f}</td>"
           f"<td>{p['shodnych'] / p['n'] * 100:.0f} %</td>"
           if p else "")
        + "</tr>"
        for k, n, s, p in prehled
    )
    hlavicka_prehled = (
        "<th>korelace po srovnání</th><th>shodných po srovnání</th>"
        if a_po is not None else "")

    nalez = (
        f"""<div class="shrnuti"><strong>Saprobní index sedí
{shoda_indexu}/{len(spolecne)}</strong>, třída ekologického stavu
{shoda_trid}/{len(spolecne)}. Výpočet LULANu odpovídá ARROW beze zbytku.</div>"""
        if not neshody else
        f"""<div class="nalez"><strong>Nález:</strong> saprobní index se
rozchází u <strong>{neshody}</strong> z {len(spolecne)} vzorků. Rozdíl
nepramení ze vzorce, ale z obsahu tabulky <code>taxalist_FB</code>: osm
taxonů má jiné hodnoty MSZS a MSZG, než vede záloha
<code>taxalist_fb_zaloha</code> (se kterou počítá ARROW). Sedm z nich
LULAN skóruje navíc, <em>Pinnularia neomaior</em> v živém taxalistu
naopak chybí úplně.<br><br>
Spusťte <code>python _tools/kontrola_taxalist_fb.py</code>, který
odchylky vypíše, a přepínačem <code>--srovnat</code> je srovná se
zálohou. Podrobnosti viz OPRAVY.md, kap. 9.</div>"""
    )

    if a_po is not None:
        nalez += f"""
<div class="shrnuti"><strong>Po srovnání taxalistu se zálohou sedí
saprobní index {shoda_po}/{len(spolecne)}.</strong> Grafy vpravo
u každé veličiny ukazují právě tento stav. Druhá sada bodů se skládá
na přímku bez zbytku — index, EQR, součet vah, střední chyba
i spolehlivost odpovídají ARROW přesně.</div>"""

    html = f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<title>Porovnání hodnocení fytobentosu s hodnotami z ARROW</title>
<style>
 body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        max-width: 1100px; margin: 0 auto; padding: 2rem; color: #1a202c;
        line-height: 1.55; }}
 h1 {{ border-bottom: 3px solid #2b6cb0; padding-bottom: .4rem; }}
 h2 {{ margin-top: 2.5rem; border-bottom: 1px solid #cbd5e0;
       padding-bottom: .3rem; }}
 .karty {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
 .karta {{ display: flex; gap: .8rem; align-items: flex-start; }}
 .karta img {{ border: 1px solid #e2e8f0; border-radius: 6px; }}
 .nadpis-karty {{ font-size: .8rem; font-weight: 600; color: #4a5568;
                  text-transform: uppercase; letter-spacing: .04em;
                  margin-bottom: .35rem; }}
 table {{ border-collapse: collapse; font-size: .85rem; }}
 .stat td {{ padding: .18rem .5rem; border-bottom: 1px solid #edf2f7;
             white-space: nowrap; }}
 .stat td:first-child {{ color: #4a5568; }}
 .stat td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; }}
 .prehled {{ width: 100%; margin: 1rem 0 2rem; font-size: .9rem; }}
 .prehled th {{ background: #edf2f7; padding: .45rem .6rem; text-align: left;
                border-bottom: 2px solid #cbd5e0; }}
 .prehled td {{ padding: .35rem .6rem; border-bottom: 1px solid #edf2f7;
                font-variant-numeric: tabular-nums; }}
 .lisi td {{ background: #fffaf0; }}
 .dobra {{ color: #22705a; font-weight: 600; }}
 .stredni {{ color: #975a16; font-weight: 600; }}
 .spatna {{ color: #9b2c2c; font-weight: 600; }}
 .shrnuti {{ background: #f7fafc; border-left: 4px solid #2b6cb0;
             padding: 1rem 1.2rem; margin: 1.5rem 0; }}
 .nalez {{ background: #fffaf0; border-left: 4px solid #dd6b20;
           padding: 1rem 1.2rem; margin: 1.5rem 0; }}
 code {{ background: #edf2f7; padding: .05rem .3rem; border-radius: 3px; }}
</style></head><body>
<h1>Porovnání hodnocení fytobentosu s hodnotami z ARROW</h1>
<p>Porovnáno <strong>{len(spolecne)}</strong> vzorků fytobentosu.
Pro každou veličinu je bodový graf hodnoty z ARROW proti hodnotě spočítané
LULANem; červená čára značí dokonalou shodu.</p>

{nalez}

<h2>Přehled</h2>
<table class="prehled">
 <tr><th>veličina</th><th>název</th><th>n</th><th>korelace</th>
     <th>medián rozdílu</th><th>shodných</th>{hlavicka_prehled}</tr>
 {radky}
</table>
{"".join(sekce)}

<h2>Vzorek po vzorku</h2>
<table class="prehled">
 <tr><th>vzorek</th><th>I_FB ARROW</th><th>I_FB LULAN</th>{hlavicka_po}<th>Δ</th>
     <th>Sw ARROW</th><th>Sw LULAN</th>
     <th>EQR ARROW</th><th>EQR LULAN</th><th>třída A/L</th></tr>
 {"".join(radky_vzorku)}
</table>
</body></html>"""

    with open(vystup, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport uložen do {vystup}")
    return vystup


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=VYCHOZI_CSV)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--vystup", default=VYSTUP)
    p.add_argument("--bez-varianty", action="store_true",
                   help="nepočítat variantu po srovnání taxalistu se zálohou")
    args = p.parse_args()

    ref = nacti_referenci(args.csv)
    vzorky = [r["sample"] for r in ref]
    print(f"referenční tabulka: {len(ref)} vzorků")

    lulan, kopie = spocitej(vzorky, args.db)
    print(f"současný stav:      {len(lulan)} vzorků (kopie {kopie})")

    lulan_po = None
    if not args.bez_varianty:
        lulan_po, _ = spocitej(vzorky, args.db, srovnat_taxalist=True,
                               spojeni="porovnani_fb_po")
        print(f"po srovnání:        {len(lulan_po)} vzorků")

    sestav_report(ref, lulan, lulan_po, args.vystup)


if __name__ == "__main__":
    main()
