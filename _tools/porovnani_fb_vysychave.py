"""
Porovnani hodnoceni fytobentosu vysychavych toku s kontrolnimi daty.

Sesit `LULAN_kontrola_FB_vysychave.xlsx` obsahuje predpocitane hodnoty
tri metrik a vysledne EQR. Skript spocita tytez vzorky LULANem a porovna:

    FI01  saprobni index (MSZS vazene MSZG)   <- sap
    FI02  salinita (SAL)                      <- SAL
    FI03  naroky na kyslik (O2)               <- O2
    FB_CELKEM  multimetrika                   <- EQR

Hodnoti se jen jarni vzorky (brezen az kveten) - referencni EQR je
vyplnene prave a jen u nich.

Jak je sesit poskladany
-----------------------
Pouzitelny je jen list `orig`; listy `data` a `vysledky` jsou proti
sobe posunute. List `vysledky` jsou dokonce dva bloky slepene vedle
sebe:

    vzorek, SAL_EQR, O2_EQR, SI_sla_EQR, EQR   120 radku = jarni vzorky
                                               v poradi listu `orig`
    SAL, O2, sap                               228 radku zarovnanych
                                               s radky listu `orig`

Radek listu `vysledky` tedy nedava dohromady jeden vzorek. Skript proto
bere hodnoty metrik z `orig` a EQR z leveho bloku, sparovane podle
poradi jarnich vzorku.

Pouziti:
    python _tools/porovnani_fb_vysychave.py
    python _tools/porovnani_fb_vysychave.py --db /tmp/kopie.db
"""

import argparse
import math
import os
import shutil
import statistics
import sys
import tempfile
from datetime import datetime

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools"))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

from import_fb_vysychave import (  # noqa: E402
    META, O_DATUM, O_O2, O_SAL, O_SAP, O_VZOREK, PREFIX, je_jarni,
    nacti_sesit,
)

VYCHOZI_XLSX = os.path.join(
    KOREN, "kontrola_vysledku", "LULAN_kontrola_FB_vysychave.xlsx")
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
VYSTUP = os.path.join(KOREN, "porovnani_metrik_FB_vysychave.html")

#: (kod v LULANu, popis, index sloupce na listu `orig`)
METRIKY = (
    ("FI01", "Saprobní index", O_SAP),
    ("FI02", "Salinita (SAL)", O_SAL),
    ("FI03", "Nároky na kyslík (O2)", O_O2),
)

#: Sloupce leveho bloku listu `vysledky`.
V_VZOREK, V_SAL_EQR, V_O2_EQR, V_SI_EQR = 0, 1, 2, 3
V_EQR = 7


def nacti_referenci(cesta):
    """Sparuje hodnoty metrik z `orig` s EQR z leveho bloku `vysledky`.

    Returns:
        list dictu {vzorek, sap, SAL, O2, EQR, SAL_EQR, O2_EQR, SI_EQR}
    """
    import openpyxl

    sesit = nacti_sesit(cesta)
    jarni = [r for r in sesit["radky"] if je_jarni(r)]

    wb = openpyxl.load_workbook(cesta, data_only=True, read_only=True)
    it = wb["vysledky"].iter_rows(values_only=True)
    next(it)
    vysledky = [list(r) for r in it]

    # Levy blok ma tolik radku, kolik je jarnich vzorku, a je ve stejnem
    # poradi. Kontrola nize overi, ze to sedi i podle jmen.
    pojmenovane = [r for r in vysledky if r[V_VZOREK]]
    if [str(r[V_VZOREK]) for r in pojmenovane] != [
            str(r[O_VZOREK]) for r in jarni]:
        raise SystemExit(
            "Levý blok listu `vysledky` neodpovídá jarním vzorkům "
            "z listu `orig` — sešit má jinou strukturu, než skript čeká.")

    return [
        {
            "vzorek": str(o[O_VZOREK]),
            "datum": o[O_DATUM],
            "sap": o[O_SAP], "SAL": o[O_SAL], "O2": o[O_O2],
            "EQR": v[V_EQR],
            "SAL_EQR": v[V_SAL_EQR], "O2_EQR": v[V_O2_EQR],
            "SI_EQR": v[V_SI_EQR],
        }
        for o, v in zip(jarni, pojmenovane)
    ]


def spocitej(db_cesta, xlsx, vzorky):
    """Naimportuje data do kopie databaze a spocita metriky."""
    from PyQt6.QtSql import QSqlDatabase

    from calc_index.fb_intermittent import hodnoceni
    from import_fb_vysychave import nacti_sesit as nacti, zapis

    kopie = os.path.join(tempfile.mkdtemp(), "fb_vysychave.db")
    shutil.copy(db_cesta, kopie)
    zapis(nacti(xlsx), kopie)

    db = QSqlDatabase.addDatabase("QSQLITE", "fb_vys")
    db.setDatabaseName(kopie)
    if not db.open():
        raise SystemExit(f"Databázi {kopie} nelze otevřít")
    vysledky = {v: hodnoceni(PREFIX + v, db) or {} for v in vzorky}
    db.close()
    return vysledky, kopie


def cislo(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def statistiky(dvojice, tolerance=0.0015):
    dvojice = [(a, b) for a, b in dvojice
               if a is not None and b is not None
               and not math.isnan(a) and not math.isnan(b)]
    if len(dvojice) < 3:
        return None
    a = [x for x, _ in dvojice]
    b = [y for _, y in dvojice]
    rozdily = [y - x for x, y in dvojice]
    return {
        "a": a, "b": b, "n": len(dvojice),
        "r": statistics.correlation(a, b) if len(set(a)) > 1 else 1.0,
        "median": statistics.median(rozdily),
        "median_abs": statistics.median(abs(x) for x in rozdily),
        "max_abs": max(abs(x) for x in rozdily),
        "shodnych": sum(1 for x in rozdily if abs(x) < tolerance),
    }


def _graf(a, b, popisek):
    """Bodovy graf reference proti LULANu; vraci PNG v base64."""
    import base64
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.4, 3.4), dpi=110)
    ax.scatter(a, b, s=14, alpha=0.6, edgecolors="none", color="#2b6cb0")
    lo, hi = min(min(a), min(b)), max(max(a), max(b))
    okraj = (hi - lo) * 0.05 or 0.5
    ax.plot([lo - okraj, hi + okraj], [lo - okraj, hi + okraj],
            color="#c53030", lw=1, zorder=0)
    ax.set_xlabel("kontrolní data")
    ax.set_ylabel("LULAN")
    ax.set_title(popisek, fontsize=9)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _barva(r):
    return "dobra" if r > 0.99 else "stredni" if r > 0.9 else "spatna"


STYL = """
 body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        max-width: 1100px; margin: 0 auto; padding: 2rem; color: #1a202c;
        line-height: 1.55; }
 h1 { border-bottom: 3px solid #2b6cb0; padding-bottom: .4rem; }
 h2 { margin-top: 2.5rem; border-bottom: 1px solid #cbd5e0;
      padding-bottom: .3rem; }
 .karty { display: flex; gap: 2rem; flex-wrap: wrap; }
 .karta { display: flex; gap: .8rem; align-items: flex-start; }
 .karta img { border: 1px solid #e2e8f0; border-radius: 6px; }
 table { border-collapse: collapse; font-size: .85rem; }
 .stat td { padding: .18rem .5rem; border-bottom: 1px solid #edf2f7;
            white-space: nowrap; }
 .stat td:first-child { color: #4a5568; }
 .stat td:last-child { text-align: right;
                       font-variant-numeric: tabular-nums; }
 .prehled { width: 100%; margin: 1rem 0 2rem; font-size: .9rem; }
 .prehled th { background: #edf2f7; padding: .45rem .6rem; text-align: left;
               border-bottom: 2px solid #cbd5e0; }
 .prehled td { padding: .35rem .6rem; border-bottom: 1px solid #edf2f7;
               font-variant-numeric: tabular-nums; }
 .lisi td { background: #fffaf0; }
 .dobra { color: #22705a; font-weight: 600; }
 .stredni { color: #975a16; font-weight: 600; }
 .spatna { color: #9b2c2c; font-weight: 600; }
 .shrnuti { background: #f7fafc; border-left: 4px solid #2b6cb0;
            padding: 1rem 1.2rem; margin: 1.5rem 0; }
 .nalez { background: #fffaf0; border-left: 4px solid #dd6b20;
          padding: 1rem 1.2rem; margin: 1.5rem 0; }
 code { background: #edf2f7; padding: .05rem .3rem; border-radius: 3px; }
"""


def sestav_report(ref, lulan, vystup):
    """Slozi HTML report."""
    sekce, prehled = [], []
    polozky = list(METRIKY) + [("FB_CELKEM", "Multimetrika (EQR)", None)]

    for kod, popisek, idx in polozky:
        if idx is None:
            dvojice = [(cislo(r["EQR"]), lulan[r["vzorek"]].get(kod))
                       for r in ref]
        else:
            klic = {O_SAP: "sap", O_SAL: "SAL", O_O2: "O2"}[idx]
            dvojice = [(cislo(r[klic]), lulan[r["vzorek"]].get(kod))
                       for r in ref]
        st = statistiky(dvojice)
        if st is None:
            continue
        prehled.append((kod, popisek, st))
        sekce.append(f"""
        <section><h2>{kod} — {popisek}</h2>
        <div class="karty"><div class="karta">
          <img src="data:image/png;base64,{_graf(st['a'], st['b'], popisek)}"
               alt="{kod}">
          <table class="stat">
            <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
            <tr><td>korelace</td>
                <td class="{_barva(st['r'])}">{st['r']:+.5f}</td></tr>
            <tr><td>medián rozdílu</td><td>{st['median']:+.4f}</td></tr>
            <tr><td>medián |rozdílu|</td><td>{st['median_abs']:.4f}</td></tr>
            <tr><td>největší rozdíl</td><td>{st['max_abs']:.4f}</td></tr>
            <tr><td>shodných</td>
                <td>{st['shodnych']} ({st['shodnych'] / st['n'] * 100:.0f} %)</td></tr>
          </table>
        </div></div></section>""")

    radky = "".join(
        f"<tr><td>{k}</td><td>{p}</td><td>{s['n']}</td>"
        f"<td class='{_barva(s['r'])}'>{s['r']:+.5f}</td>"
        f"<td>{s['median']:+.4f}</td><td>{s['median_abs']:.4f}</td>"
        f"<td>{s['shodnych'] / s['n'] * 100:.0f} %</td></tr>"
        for k, p, s in prehled)

    radky_vzorku = []
    for r in ref:
        v = lulan[r["vzorek"]]
        bunky = []
        for kod, _, idx in METRIKY:
            klic = {O_SAP: "sap", O_SAL: "SAL", O_O2: "O2"}[idx]
            a, b = cislo(r[klic]), v.get(kod)
            sedi = a is not None and b is not None and abs(b - a) < 0.0015
            bunky.append(
                f"<td>{'' if a is None else f'{a:.4f}'}</td>"
                f"<td class=\"{'' if sedi else 'spatna'}\">"
                f"{'' if b is None else f'{b:.4f}'}</td>")
        a, b = cislo(r["EQR"]), v.get("FB_CELKEM")
        bunky.append(
            f"<td>{'' if a is None else f'{a:.4f}'}</td>"
            f"<td>{'' if b is None else f'{b:.4f}'}</td>")
        radky_vzorku.append(
            f"<tr><td>{r['vzorek']}</td>"
            f"<td>{r['datum']:%d.%m.%Y}</td>{''.join(bunky)}</tr>")

    hlavicky = "".join(f"<th colspan=2>{k}</th>"
                       for k, _, _ in list(METRIKY) + [("EQR", "", None)])
    podhlavicky = "".join("<th>ref.</th><th>LULAN</th>"
                          for _ in range(len(METRIKY) + 1))

    html = f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<title>Fytobentos vysychavých toků — porovnání s kontrolními daty</title>
<style>{STYL}</style></head><body>
<h1>Fytobentos vysychavých toků — porovnání s kontrolními daty</h1>
<p>Porovnáno <strong>{len(ref)}</strong> jarních vzorků (březen–květen)
z vysychavých lokalit. Podzimní vzorky se nehodnotí a referenční EQR
u nich není vyplněné. U každé veličiny je bodový graf kontrolní hodnoty
proti hodnotě spočítané LULANem; červená čára značí dokonalou shodu.</p>

<div class="nalez">
<strong>Co je sloupec <code>sap</code>:</strong> není to Sládečkové
saprobní index. Hodnoty v sešitu jsou zlomky se společným jmenovatelem
a celočíselnými čitateli, takže za nimi stojí celočíselná trait hodnota —
zatímco MSZS je desetinné. <code>sap</code> se navíc počítá přes tutéž
množinu taxonů jako SAL a O2 (stejný jmenovatel na každém řádku), takže
jde o třetí trait z téže zdrojové tabulky. Taxonomický seznam LULANu
tento sloupec nemá; FI01 proto počítá skutečný saprobní index z MSZS
a s <code>sap</code> se shodovat nemůže.
</div>

<h2>Přehled</h2>
<table class="prehled">
 <tr><th>kód</th><th>metrika</th><th>n</th><th>korelace</th>
     <th>medián Δ</th><th>medián |Δ|</th><th>shodných</th></tr>
 {radky}
</table>
{"".join(sekce)}

<h2>Vzorek po vzorku</h2>
<table class="prehled">
 <tr><th rowspan=2>vzorek</th><th rowspan=2>datum</th>{hlavicky}</tr>
 <tr>{podhlavicky}</tr>
 {"".join(radky_vzorku)}
</table>
</body></html>"""

    with open(vystup, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport uložen do {vystup}")
    return prehled


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", default=VYCHOZI_XLSX)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--vystup", default=VYSTUP)
    args = p.parse_args()

    ref = nacti_referenci(args.xlsx)
    print(f"jarních vzorků s referenčním EQR: {len(ref)}")

    lulan, kopie = spocitej(args.db, args.xlsx, [r["vzorek"] for r in ref])
    print(f"spočítáno nad kopií {kopie}")

    for kod, _, st in sestav_report(ref, lulan, args.vystup):
        print(f"   {kod:11s} r={st['r']:+.5f}  medián |Δ| {st['median_abs']:.4f}"
              f"  shodných {st['shodnych']}/{st['n']}")


if __name__ == "__main__":
    main()
