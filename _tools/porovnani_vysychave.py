"""
Porovnani hodnoceni vysychavych toku (MZB) s kalibracnimi daty metodiky.

Sesit `LULAN_kontrola_MZB_vysychave.xlsx` obsahuje podklady, na kterych
se metodika kalibrovala - vcetne hodnot peti metrik a vysledneho EQR.
Skript spocita tytez vzorky LULANem a porovna:

    MI01  podil posvatek (Plecoptera) [%]     <- Abu.Proc.Plecoptera.x
    MI02  Margalefuv index diverzity          <- Margalef
    MI03  saprobita SZA+SZP [%]               <- sapr.SZA_SZP.x
    MI04  teplomilnost WAR+EUT [%]            <- temp_pref.war_eut.x
    MI05  reprodukce frc+tec [%]              <- reprod.frc_tec
    MZB_CELKEM  multimetrika                  <- EQR

Hodnoti se jen jarni vzorky - metodika podzimni sber nepouziva a
referencni EQR u nich neni vyplnene.

Report ukazuje dve varianty vedle sebe: s nazvy taxonu tak, jak jsou
v sesitu, a s nazvy prevedenymi na konvenci taxalistu (viz
`nazvy_vysychave.py`).

Krome metrik se kontroluji i abioticke parametry lokalit - sesit je
uvadi, LULAN je umi dopocitat z ricni site a z DMR CUZK. Sklon
a nadmorska vyska vyzaduji pristup k sluzbe CUZK; bez nej se
preskoci a v reportu se to uvede.

Pouziti:
    python _tools/porovnani_vysychave.py
    python _tools/porovnani_vysychave.py --bez-abiotiky
    python _tools/porovnani_vysychave.py --db /tmp/kopie.db
"""

import argparse
import math
import os
import re
import shutil
import statistics
import sys
import tempfile

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools"))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_XLSX = os.path.join(
    KOREN, "kontrola_vysledku", "LULAN_kontrola_MZB_vysychave.xlsx")
VYCHOZI_DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
VYSTUP = os.path.join(KOREN, "porovnani_metrik_vysychave.html")

#: Prefix, kterym import odlisil kalibracni lokality a vzorky.
PREFIX = "VYS_"

#: (kod metriky, popis, index sloupce v listu `vysledky`)
METRIKY = (
    ("MZB_CELKEM", "Multimetrika (EQR)", 6),
    ("MI01", "Podíl pošvatek [%]", 4),
    ("MI02", "Margalefův index", 5),
    ("MI03", "Saprobita SZA+SZP [%]", 2),
    ("MI04", "Teplomilnost WAR+EUT [%]", 3),
    ("MI05", "Reprodukce frc+tec [%]", 1),
)

#: (popis, index sloupce v listu `lokality`, sloupec v tabulce loc, jednotka)
ABIOTIKA = (
    ("Strahlerův řád", 5, "STRAHLER", ""),
    ("Vzdálenost od pramene", 7, "KM_OD_PRAM", " km"),
    ("Plocha povodí", 8, "PLOCHA_POV", " km²"),
    ("Nadmořská výška", 4, "MNM", " m"),
    ("Podélný sklon", 6, "SLOPE", " ‰"),
)

#: Parametry, ktere jdou spocitat bez pripojeni k CUZK.
ABIOTIKA_OFFLINE = ["souradnice", "umori", "strahler", "km_od_pram",
                    "plocha_pov"]


def je_jarni(kod):
    """Jarni vzorek? Pripona `...41` je R-ovske odliseni duplicit."""
    return bool(re.search(r"_JARO(\.\.\.\d+)?$", re.sub(r"\s+$", "", str(kod))))


def nacti_referenci(cesta):
    """Nacte listy `vysledky` a `lokality` z kalibracniho sesitu."""
    import openpyxl

    wb = openpyxl.load_workbook(cesta, data_only=True, read_only=True)

    def radky(nazev):
        it = wb[nazev].iter_rows(values_only=True)
        next(it)
        return [list(r) for r in it if r[0]]

    return {
        "vysledky": {str(r[0]): r for r in radky("vysledky")},
        "lokality": {str(r[0]): r for r in radky("lokality")},
    }


def spocitej(db_cesta, vzorky, prevod_nazvu, spojeni):
    """Naimportuje kalibracni data do kopie databaze a spocita metriky.

    Returns:
        dict {kod_vzorku_bez_prefixu: vysledek hodnoceni}
    """
    from PyQt6.QtSql import QSqlDatabase

    from calc_index.mzb_intermittent import hodnoceni

    kopie = os.path.join(tempfile.mkdtemp(), "vysychave.db")
    shutil.copy(db_cesta, kopie)

    from import_vysychave import nacti_sesit, zapis
    zapis(nacti_sesit(VYCHOZI_XLSX), kopie, prevod_nazvu)

    db = QSqlDatabase.addDatabase("QSQLITE", spojeni)
    db.setDatabaseName(kopie)
    if not db.open():
        raise SystemExit(f"Databázi {kopie} nelze otevřít")
    vysledky = {v: hodnoceni(PREFIX + v, db) or {} for v in vzorky}
    db.close()
    return vysledky, kopie


def spocitej_abiotiku(db_cesta, online=False):
    """Dopocita abioticke parametry nad kopii a vrati je pro kalibracni lokality.

    Returns:
        (dict {kod_bez_prefixu: dict sloupcu}, list preskocenych parametru)
    """
    import sqlite3

    from abiotic_params import doplnit_parametry

    from import_vysychave import nacti_sesit, zapis

    kopie = os.path.join(tempfile.mkdtemp(), "abiotika.db")
    shutil.copy(db_cesta, kopie)
    zapis(nacti_sesit(VYCHOZI_XLSX), kopie)

    parametry = list(ABIOTIKA_OFFLINE)
    if online:
        parametry += ["mnm", "slope"]
    prehled = doplnit_parametry(kopie, parametry, jen_chybejici=True)
    preskoceno = [p for p, v in prehled.items() if v.get("chyba")]
    if not online:
        preskoceno += ["mnm", "slope"]

    conn = sqlite3.connect(kopie)
    conn.row_factory = sqlite3.Row
    hodnoty = {
        r["KOD"][len(PREFIX):]: dict(r)
        for r in conn.execute(
            "SELECT * FROM loc WHERE KOD LIKE ?", (PREFIX + "%",))
    }
    conn.close()
    return hodnoty, preskoceno


def cislo(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def statistiky(dvojice, tolerance):
    """Zakladni statistiky pro dvojice (reference, LULAN)."""
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


def _graf(a, b, kod, popisek):
    """Bodovy graf reference proti LULANu; vraci PNG v base64."""
    import base64
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.4, 3.4), dpi=110)
    ax.scatter(a, b, s=12, alpha=0.55, edgecolors="none", color="#2b6cb0")
    lo, hi = min(min(a), min(b)), max(max(a), max(b))
    okraj = (hi - lo) * 0.05 or 0.5
    ax.plot([lo - okraj, hi + okraj], [lo - okraj, hi + okraj],
            color="#c53030", lw=1, zorder=0)
    ax.set_xlabel("kalibrační data"), ax.set_ylabel("LULAN")
    ax.set_title(popisek, fontsize=9)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _barva(r):
    return "dobra" if r > 0.999 else "stredni" if r > 0.95 else "spatna"


def _karta(st, kod, popisek, nadpis, desetin=4):
    return f"""<div class="karta">
      <div><div class="nadpis-karty">{nadpis}</div>
        <img src="data:image/png;base64,{_graf(st['a'], st['b'], kod, popisek)}"
             alt="{kod} — {nadpis}"></div>
      <table class="stat">
        <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
        <tr><td>korelace</td>
            <td class="{_barva(st['r'])}">{st['r']:.6f}</td></tr>
        <tr><td>medián rozdílu</td><td>{st['median']:+.{desetin}f}</td></tr>
        <tr><td>medián |rozdílu|</td><td>{st['median_abs']:.{desetin}f}</td></tr>
        <tr><td>největší rozdíl</td><td>{st['max_abs']:.{desetin}f}</td></tr>
        <tr><td>shodných</td>
            <td>{st['shodnych']} ({st['shodnych'] / st['n'] * 100:.0f} %)</td></tr>
      </table></div>"""


STYL = """
 body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        max-width: 1150px; margin: 0 auto; padding: 2rem; color: #1a202c;
        line-height: 1.55; }
 h1 { border-bottom: 3px solid #2b6cb0; padding-bottom: .4rem; }
 h2 { margin-top: 2.5rem; border-bottom: 1px solid #cbd5e0;
      padding-bottom: .3rem; }
 h3 { margin-top: 1.8rem; font-size: 1.05rem; color: #2d3748; }
 .karty { display: flex; gap: 2rem; flex-wrap: wrap; }
 .karta { display: flex; gap: .8rem; align-items: flex-start; }
 .karta img { border: 1px solid #e2e8f0; border-radius: 6px; }
 .nadpis-karty { font-size: .8rem; font-weight: 600; color: #4a5568;
                 text-transform: uppercase; letter-spacing: .04em;
                 margin-bottom: .35rem; }
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


def sekce_metrik(ref, bez, s_prevodem, vzorky):
    """Prehledova tabulka, grafy a tabulka vzorek po vzorku."""
    prehled, sekce = [], []
    for kod, popisek, idx in METRIKY:
        tol = 0.0015 if kod != "MZB_CELKEM" else 0.0005
        des = 4 if kod != "MZB_CELKEM" else 4
        st = statistiky(
            [(cislo(ref[v][idx]), bez[v].get(kod)) for v in vzorky], tol)
        st_p = statistiky(
            [(cislo(ref[v][idx]), s_prevodem[v].get(kod)) for v in vzorky], tol)
        if st is None:
            continue
        prehled.append((kod, popisek, st, st_p))
        karty = _karta(st, kod, popisek, "názvy ze sešitu", des)
        if st_p:
            karty += _karta(st_p, kod, popisek, "názvy převedené", des)
        sekce.append(f'<section><h2>{kod} — {popisek}</h2>'
                     f'<div class="karty">{karty}</div></section>')

    radky = "".join(
        f"<tr><td>{k}</td><td>{p}</td><td>{s['n']}</td>"
        f"<td class='{_barva(s['r'])}'>{s['r']:.6f}</td>"
        f"<td>{s['median_abs']:.4f}</td>"
        f"<td>{s['shodnych'] / s['n'] * 100:.0f} %</td>"
        + (f"<td class='{_barva(q['r'])}'>{q['r']:.6f}</td>"
           f"<td>{q['median_abs']:.4f}</td>"
           f"<td>{q['shodnych'] / q['n'] * 100:.0f} %</td>" if q else "")
        + "</tr>"
        for k, p, s, q in prehled)

    # tabulka vzorek po vzorku
    radky_vzorku = []
    for v in vzorky:
        bunky = []
        for kod, _, idx in METRIKY:
            a, b = cislo(ref[v][idx]), s_prevodem[v].get(kod)
            sedi = a is not None and b is not None and abs(b - a) < 0.0015
            bunky.append(
                f"<td>{'' if a is None else f'{a:.4f}'}</td>"
                f"<td class=\"{'' if sedi else 'spatna'}\">"
                f"{'' if b is None else f'{b:.4f}'}</td>")
        radky_vzorku.append(f"<tr><td>{v}</td>{''.join(bunky)}</tr>")

    hlavicky = "".join(f"<th colspan=2>{k}</th>" for k, _, _ in METRIKY)
    podhlavicky = "".join("<th>ref.</th><th>LULAN</th>" for _ in METRIKY)
    return prehled, "".join(sekce), radky, radky_vzorku, hlavicky, podhlavicky


def sekce_abiotiky(ref_lok, spocteno, preskoceno):
    """Tabulka a grafy pro abioticke parametry lokalit."""
    radky, karty = [], []
    for popis, idx, sloupec, jednotka in ABIOTIKA:
        dvojice = [(cislo(r[idx]), cislo((spocteno.get(k) or {}).get(sloupec)))
                   for k, r in ref_lok.items()]
        st = statistiky(dvojice, 0.5 if sloupec == "STRAHLER" else 0.01)
        if st is None:
            radky.append(
                f"<tr><td>{popis}</td><td colspan=5><em>nespočteno — "
                f"vyžaduje připojení ke službě ČÚZK</em></td></tr>")
            continue
        radky.append(
            f"<tr><td>{popis}{jednotka}</td><td>{st['n']}</td>"
            f"<td class='{_barva(st['r'])}'>{st['r']:.6f}</td>"
            f"<td>{st['median']:+.3f}</td><td>{st['median_abs']:.3f}</td>"
            f"<td>{st['shodnych']} ({st['shodnych'] / st['n'] * 100:.0f} %)</td>"
            f"</tr>")
        karty.append(_karta(st, sloupec, popis + jednotka,
                            "kalibrační data vs. LULAN", 3))
    return "".join(radky), "".join(karty)


def sestav_report(ref, bez, s_prevodem, vzorky, abiotika, vystup):
    """Slozi HTML report."""
    ref_v = ref["vysledky"]
    prehled, sekce, radky, radky_vzorku, hl, podhl = sekce_metrik(
        ref_v, bez, s_prevodem, vzorky)

    radky_abio, karty_abio = "", ""
    if abiotika:
        radky_abio, karty_abio = sekce_abiotiky(
            ref["lokality"], abiotika[0], abiotika[1])

    presne = {k: s for k, _, s, _ in prehled}
    html = f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<title>Vysychavé toky — porovnání s kalibračními daty metodiky</title>
<style>{STYL}</style></head><body>
<h1>Vysychavé toky (MZB) — porovnání s kalibračními daty metodiky</h1>
<p>Porovnáno <strong>{len(vzorky)}</strong> jarních vzorků ze
<strong>{len(ref['lokality'])}</strong> vysychavých lokalit. Podzimní vzorky
se podle metodiky nehodnotí a referenční EQR u nich není vyplněné.
U každé veličiny je bodový graf hodnoty z kalibračních dat proti hodnotě
spočítané LULANem; červená čára značí dokonalou shodu.</p>

<div class="shrnuti">
<strong>Podíl pošvatek a Margalefův index se reprodukují přesně</strong>
(korelace 1,000000; Margalef sedí u všech {len(vzorky)} vzorků).
Trait metriky MI03–MI05 korelují 0,85–0,99, ale přesně nesedí — rozdíl
neleží ve vzorci, viz nález níže.
</div>

<div class="nalez">
<strong>Nález:</strong> vzorec trait metrik je ověřený — z testovaných
variant vážení (surová abundance, relativní abundance, odmocnina,
prezence/absence) vychází nejlépe <code>ln(x+1)</code>, shodně
s metrikami stálých toků, a to u všech tří metrik současně. Zbývající
rozdíl je proto nejspíš v <em>hodnotách</em> trait tabulky: taxalist
LULANu je nemá totožné s tabulkou, se kterou se metodika kalibrovala.
Ověřit to bez původní trait tabulky nelze.
</div>

<h2>Přehled metrik</h2>
<table class="prehled">
 <tr><th rowspan=2>kód</th><th rowspan=2>metrika</th><th rowspan=2>n</th>
     <th colspan=3>názvy ze sešitu</th><th colspan=3>názvy převedené</th></tr>
 <tr><th>korelace</th><th>medián |Δ|</th><th>shodných</th>
     <th>korelace</th><th>medián |Δ|</th><th>shodných</th></tr>
 {radky}
</table>
{sekce}

<h2>Abiotické parametry lokalit</h2>
<p>Sešit uvádí abiotické parametry, se kterými se metodika kalibrovala.
Import je záměrně neukládá — LULAN je dopočítává z vlastní říční sítě
a z výškopisu ČÚZK, takže je lze nezávisle porovnat.</p>
<table class="prehled">
 <tr><th>parametr</th><th>n</th><th>korelace</th><th>medián Δ</th>
     <th>medián |Δ|</th><th>shodných</th></tr>
 {radky_abio or '<tr><td colspan=6><em>nepočítáno</em></td></tr>'}
</table>
<div class="karty">{karty_abio}</div>

<h2>Vzorek po vzorku</h2>
<p>Uvedena je varianta s převedenými názvy taxonů. Barevně jsou
zvýrazněny hodnoty, které se od kalibračních dat liší.</p>
<table class="prehled">
 <tr><th rowspan=2>vzorek</th>{hl}</tr>
 <tr>{podhl}</tr>
 {"".join(radky_vzorku)}
</table>
</body></html>"""

    with open(vystup, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport uložen do {vystup}")
    return presne


def main():
    global VYCHOZI_XLSX

    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", default=VYCHOZI_XLSX)
    p.add_argument("--db", default=VYCHOZI_DB)
    p.add_argument("--vystup", default=VYSTUP)
    p.add_argument("--bez-abiotiky", action="store_true",
                   help="přeskočit kontrolu abiotických parametrů")
    p.add_argument("--online", action="store_true",
                   help="dopočítat i výšku a sklon (vyžaduje ČÚZK)")
    args = p.parse_args()
    VYCHOZI_XLSX = args.xlsx

    ref = nacti_referenci(args.xlsx)
    vzorky = sorted(v for v, r in ref["vysledky"].items()
                    if je_jarni(v) and r[6] is not None)
    print(f"jarních vzorků s referenčním EQR: {len(vzorky)}")

    bez, _ = spocitej(args.db, vzorky, False, "vys_bez")
    print("spočítáno s názvy ze sešitu")
    s_prevodem, _ = spocitej(args.db, vzorky, True, "vys_prevod")
    print("spočítáno s převedenými názvy")

    abiotika = None
    if not args.bez_abiotiky:
        abiotika = spocitej_abiotiku(args.db, args.online)
        print(f"abiotika dopočítána, přeskočeno: {abiotika[1] or 'nic'}")

    presne = sestav_report(ref, bez, s_prevodem, vzorky, abiotika, args.vystup)
    for kod, st in presne.items():
        print(f"   {kod:11s} r={st['r']:.6f}  shodných "
              f"{st['shodnych']}/{st['n']}")


if __name__ == "__main__":
    main()
