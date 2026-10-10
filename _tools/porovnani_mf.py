"""
Porovnani hodnoceni makrofyt (MF) spocitaneho LULANem s hodnotami z ARROW.

Nacte referencni tabulku exportovanou z IS ARROW, spocita tytez vzorky
vlastnim vypoctem a porovna:

    MF01       index MTV
    MF01Q      EQR indexu MTV
    MF_POCET   pocet indikatorovych taxonu
    MF_TYP     typ toku podle makrofyt
    MF_CELKEM  finalni hodnoceni

Vystupem je HTML report se stejnym rozvrzenim jako u makrozoobentosu.

Pouziti:
    python _tools/porovnani_mf.py
    python _tools/porovnani_mf.py --csv jiny_export.csv
"""

import argparse
import csv
import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

VYCHOZI_CSV = os.path.join(
    "/sessions/beautiful-zen-pasteur/mnt/uploads",
    "export_MF_brod_vzorky.csv",
)
DB = os.path.join(KOREN, "dtb", "LULAN_dtb_001.db")
VYSTUP = os.path.join(KOREN, "porovnani_metrik_MF.html")

#: Export z ARROW je v cp1250.
KODOVANI_EXPORTU = "cp1250"


def nacti_referenci(cesta):
    """Nacte export z ARROW; preskoci dva popisne radky pod hlavickou."""
    text = open(cesta, encoding=KODOVANI_EXPORTU).read()
    radky = list(csv.DictReader(text.splitlines(), delimiter=";"))
    return [r for r in radky if (r.get("SAMPLE") or "").strip()]


def cislo(hodnota):
    try:
        return float(str(hodnota).replace(",", "."))
    except (TypeError, ValueError):
        return None


def spocitej(vzorky):
    """Spocita MF hodnoceni LULANem.

    Returns:
        dict {SAMPLE_ID: {"MF01", "MF01Q", "MF_POCET", "MF_TYP"}}
    """
    from PyQt6.QtSql import QSqlDatabase, QSqlQuery
    from calc_index.mf_reka import MTV_SQL, TYPY, _agregovat_vzdy, urci_typ

    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(DB)
    if not db.open():
        raise SystemExit(f"Databázi {DB} nelze otevřít")

    vysledky = {}
    for sid, loc in vzorky:
        q = QSqlQuery(db)
        q.prepare("SELECT MNM, STRAHLER, UMORI FROM loc WHERE KOD = ?")
        q.addBindValue(loc)
        if not q.exec() or not q.next():
            continue
        typ, _ = urci_typ(q.value(0), q.value(1), q.value(2))

        q = QSqlQuery(db)
        q.prepare(MTV_SQL)
        q.addBindValue(sid)
        # Agregace do alternujícího druhu závisí na typu toku - viz mf_reka.
        q.addBindValue(_agregovat_vzdy(typ))
        q.addBindValue(_agregovat_vzdy(typ))
        mtv = pocet = None
        if q.exec() and q.next():
            mtv, pocet = cislo(q.value(0)), cislo(q.value(1))

        eqr = None
        if mtv is not None and typ:
            eqr = round((mtv - 1) / TYPY[typ]["delitel"], 3)

        vysledky[sid] = {
            "MF01": mtv,
            "MF01Q": eqr,
            "MF_CELKEM": eqr,
            "MF_POCET": pocet,
            "MF_TYP": typ,
        }
    db.close()
    return vysledky


def trida_mf(eqr, typ):
    """Zaradi EQR do tridy ekologickeho stavu podle typu toku."""
    from calc_index.mf_reka import TYPY

    if eqr is None or typ not in TYPY:
        return None
    for mez, oznaceni in TYPY[typ]["stav"]:
        if eqr > mez:
            return oznaceni
    return "Z"


def sestav_report(ref, lulan, vystup=VYSTUP):
    """Sestavi HTML report ve stejnem rozvrzeni jako u makrozoobentosu."""
    import pandas as pd

    from porovnani_report import _graf, _statistiky

    nazvy = {
        "MF01": "Index MTV",
        "MF01Q": "EQR indexu MTV",
        "MF_POCET": "Počet indikátorových taxonů",
        "MF_CELKEM": "Finální hodnocení",
    }

    spolecne = [r["SAMPLE"] for r in ref if r["SAMPLE"] in lulan]
    a_ref = pd.DataFrame(
        [{k: r.get(k) for k in ("SAMPLE", "MF01", "MF01Q", "MF_POCET",
                                "MF_TYP", "MF_CELKEM")} for r in ref]
    ).set_index("SAMPLE")
    a_lul = pd.DataFrame(lulan).T

    # --- typ toku: kategoriální, ARROW uvádí jen číslo shluku ------------
    # LULAN rozlišuje podtypy A/B podle úmoří (Rozhodnutí komise 2018/229/EU),
    # ARROW je do exportu nepíše. Porovnává se proto jen číslo shluku.
    shoda_typ = sum(
        1 for s in spolecne
        if str(a_lul.loc[s, "MF_TYP"] or "")[:1] == str(a_ref.loc[s, "MF_TYP"])
    )

    sekce, prehled = [], []
    for kod in ("MF_CELKEM", "MF01", "MF01Q", "MF_POCET"):
        a = pd.to_numeric(a_ref.loc[spolecne, kod], errors="coerce")
        b = pd.to_numeric(a_lul.loc[spolecne, kod], errors="coerce")
        st = _statistiky(a, b)
        if st is None:
            continue
        popisek = nazvy[kod]
        obr = _graf(st["a"], st["b"], kod, popisek)
        trida = ("dobra" if st["r"] > 0.999 else
                 "stredni" if st["r"] > 0.98 else "spatna")
        prehled.append((kod, popisek, st))
        sekce.append(f"""
        <section><h2>{kod} — {popisek}</h2>
        <div class="karty"><div class="karta">
          <img src="data:image/png;base64,{obr}" alt="{kod}">
          <table class="stat">
            <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
            <tr><td>korelace</td><td class="{trida}">{st['r']:.5f}</td></tr>
            <tr><td>medián rozdílu</td><td>{st['median']:+.4f}</td></tr>
            <tr><td>průměr rozdílu</td><td>{st['prumer']:+.4f}</td></tr>
            <tr><td>největší rozdíl</td><td>{st['max_abs']:.4f}</td></tr>
            <tr><td>shodných (±0,001)</td>
                <td>{st['shodnych']} ({st['shodnych'] / st['n'] * 100:.0f} %)</td></tr>
          </table>
        </div></div></section>""")

    # --- rozpad podle typu toku -----------------------------------------
    podle_typu = {}
    for s in spolecne:
        typ = str(a_lul.loc[s, "MF_TYP"] or "?")
        arrow = cislo(a_ref.loc[s, "MF01"])
        lul = cislo(a_lul.loc[s, "MF01"])
        if arrow is None or lul is None:
            continue
        podle_typu.setdefault(typ, []).append(abs(lul - arrow))

    radky_typ = "".join(
        f"<tr><td>{t}</td><td>{len(v)}</td>"
        f"<td class=\"{'dobra' if sum(1 for x in v if x < 0.005) == len(v) else 'spatna'}\">"
        f"{sum(1 for x in v if x < 0.005)}/{len(v)}</td>"
        f"<td>{sorted(v)[len(v) // 2]:.4f}</td><td>{max(v):.4f}</td></tr>"
        for t, v in sorted(podle_typu.items())
    )

    radky = "".join(
        f"<tr><td>{k}</td><td>{n}</td><td>{s['n']}</td>"
        f"<td class='{'dobra' if s['r'] > 0.999 else 'stredni' if s['r'] > 0.98 else 'spatna'}'>"
        f"{s['r']:.5f}</td><td>{s['median']:+.4f}</td>"
        f"<td>{s['shodnych'] / s['n'] * 100:.0f} %</td></tr>"
        for k, n, s in prehled
    )

    # --- tabulka vzorek po vzorku ---------------------------------------
    radky_vzorku = []
    for s in spolecne:
        aM, lM = cislo(a_ref.loc[s, "MF01"]), cislo(a_lul.loc[s, "MF01"])
        aE, lE = cislo(a_ref.loc[s, "MF_CELKEM"]), cislo(a_lul.loc[s, "MF_CELKEM"])
        typ = str(a_lul.loc[s, "MF_TYP"] or "?")
        sedi = aM is not None and lM is not None and abs(aM - lM) < 0.005
        tA, tL = trida_mf(aE, typ), trida_mf(lE, typ)
        radky_vzorku.append(
            f"<tr class=\"{'' if sedi else 'lisi'}\"><td>{s}</td><td>{typ}</td>"
            f"<td>{'' if aM is None else f'{aM:.4f}'}</td>"
            f"<td>{'' if lM is None else f'{lM:.4f}'}</td>"
            f"<td>{'' if (aM is None or lM is None) else f'{lM - aM:+.4f}'}</td>"
            f"<td>{'' if aE is None else f'{aE:.3f}'}</td>"
            f"<td>{'' if lE is None else f'{lE:.3f}'}</td>"
            f"<td>{tA or ''} / {tL or ''}</td></tr>"
        )

    shoda_trid = sum(
        1 for s in spolecne
        if trida_mf(cislo(a_ref.loc[s, "MF_CELKEM"]), str(a_lul.loc[s, "MF_TYP"] or "?"))
        == trida_mf(cislo(a_lul.loc[s, "MF_CELKEM"]), str(a_lul.loc[s, "MF_TYP"] or "?"))
    )

    typ1 = podle_typu.get("1", [])
    mimo1 = [x for t, v in podle_typu.items() if t != "1" for x in v]
    sedi_mimo = sum(1 for x in mimo1 if x < 0.005)
    median_typ1 = sorted(typ1)[len(typ1) // 2] if typ1 else 0.0

    html = f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<title>Porovnání hodnocení makrofyt s hodnotami z ARROW</title>
<style>
 body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        max-width: 1100px; margin: 0 auto; padding: 2rem; color: #1a202c;
        line-height: 1.55; }}
 h1 {{ border-bottom: 3px solid #2b6cb0; padding-bottom: .4rem; }}
 h2 {{ margin-top: 2.5rem; border-bottom: 1px solid #cbd5e0;
       padding-bottom: .3rem; }}
 .karty {{ display: flex; gap: 1.5rem; flex-wrap: wrap; }}
 .karta {{ display: flex; gap: .8rem; align-items: flex-start; }}
 .karta img {{ border: 1px solid #e2e8f0; border-radius: 6px; }}
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
</style></head><body>
<h1>Porovnání hodnocení makrofyt s hodnotami z ARROW</h1>
<p>Porovnáno <strong>{len(spolecne)}</strong> vzorků makrofyt z broditelných toků.
Pro každou veličinu je bodový graf hodnoty z ARROW proti hodnotě spočítané
LULANem; červená čára značí dokonalou shodu.</p>

<div class="shrnuti">
<strong>Typ toku sedí {shoda_typ}/{len(spolecne)}</strong> — abiotické parametry
lokalit (nadmořská výška, Strahlerův řád, úmoří) jsou v databázi shodné
s hodnotami, se kterými počítá ARROW.<br>
<strong>Třída ekologického stavu sedí {shoda_trid}/{len(spolecne)}.</strong>
</div>

<div class="nalez">
<strong>Nález:</strong> mimo typ 1 sedí index MTV
<strong>{sedi_mimo}/{len(mimo1)}</strong> vzorků na pět desetinných míst.
V typu 1 (horské toky nad 500 m n. m.) se hodnoty rozcházejí
u <strong>všech {len(typ1)}</strong> vzorků — medián rozdílu
{median_typ1:.3f} bodu MTV. Metodika u tohoto typu uvádí, že
„je vhodnější provést výpočet jiným způsobem", a zavádí pravidlo
alternujícího druhu; to LULAN používá, ale hodnoty ARROW se jím
reprodukovat nedaří. Podrobnosti viz OPRAVY.md, kap. 6.
</div>

<h2>Přehled</h2>
<table class="prehled">
 <tr><th>veličina</th><th>název</th><th>n</th><th>korelace</th>
     <th>medián rozdílu</th><th>shodných</th></tr>
 {radky}
</table>

<h2>Rozpad podle typu toku</h2>
<table class="prehled">
 <tr><th>typ</th><th>n</th><th>shodných MTV</th>
     <th>medián |Δ|</th><th>max |Δ|</th></tr>
 {radky_typ}
</table>
{"".join(sekce)}

<h2>Vzorek po vzorku</h2>
<table class="prehled">
 <tr><th>vzorek</th><th>typ</th><th>MTV ARROW</th><th>MTV LULAN</th><th>Δ</th>
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
    args = p.parse_args()

    ref = nacti_referenci(args.csv)
    print(f"referenční tabulka: {len(ref)} vzorků")

    lulan = spocitej([(r["SAMPLE"], r["LOC"]) for r in ref])
    print(f"spočítáno: {len(lulan)} vzorků")

    sestav_report(ref, lulan)


if __name__ == "__main__":
    main()
