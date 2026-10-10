"""Sestaveni HTML reportu z porovnani metrik."""

import base64
import io
import os

import numpy as np
import pandas as pd

NAZVY = {
    "MB01": "Saprobní index", "MB02": "Litál", "MB03": "RETI",
    "MB04": "EPT Abu", "MB05": "Diverzita Margalef", "MB06": "Metaritrál",
    "MB07": "Index B", "MB08": "Jep Abu", "MB09": "Epiritrál",
    "MB10": "Hyporitrál", "MB11": "Počet taxonů pakomárů",
    "MB12": "Počet čeledí", "MB13": "EPT Tax", "MB14": "Pos Abu",
    "MB15": "Spásači", "MB16": "Epipotamál", "MB17": "SPEAR organic",
    "MB18": "(neurčeno)",
}


#: Sezony, ktere se podle metodiky hodnoti. Letni vzorky (kampan "L")
#: metodika k hodnoceni ekologickeho stavu nepouziva a v referencni sade
#: u nich navic chybi cast taxonu, takze by report jen zasumnily.
HODNOCENE_SEZONY = ("_J_", "_P_")


def _graf(a, b, nazev, popisek):
    """Vytvori bodovy graf a vrati ho jako base64 PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=110)
    ax.scatter(a, b, s=12, alpha=0.45, edgecolors="none", color="#2b6cb0")

    lo = float(min(a.min(), b.min()))
    hi = float(max(a.max(), b.max()))
    okraj = (hi - lo) * 0.05 or 1
    ax.plot([lo, hi], [lo, hi], "-", color="#e53e3e", lw=1.2, label="shoda 1:1")
    ax.set_xlim(lo - okraj, hi + okraj)
    ax.set_ylim(lo - okraj, hi + okraj)
    ax.set_xlabel("ARROW")
    ax.set_ylabel("LULAN")
    ax.set_title(f"{nazev} — {popisek}", fontsize=10)
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _trida(hodnota):
    """Zaradi multimetriku do tridy ekologickeho stavu."""
    for mez, oznaceni in ((0.8, "VD"), (0.6, "D"), (0.4, "S"), (0.2, "P")):
        if hodnota >= mez:
            return oznaceni
    return "Z"


def _shoda_trid(a, b):
    """Podil vzorku, ktere spadnou do stejne tridy ekologickeho stavu [%]."""
    if len(a) == 0:
        return 0.0
    shoda = sum(_trida(x) == _trida(y) for x, y in zip(a, b))
    return shoda / len(a) * 100


def _statistiky(a, b):
    ok = a.notna() & b.notna()
    if ok.sum() < 3:
        return None
    a, b = a[ok], b[ok]
    d = b - a
    r = np.corrcoef(a, b)[0, 1] if a.std() > 0 and b.std() > 0 else float("nan")
    return {
        "n": int(ok.sum()),
        "r": r,
        "median": d.median(),
        "prumer": d.mean(),
        "max_abs": d.abs().max(),
        "shodnych": int((d.abs() < 0.001).sum()),
        "a": a, "b": b,
    }


def sestav_report(ref, lulan, vystup=None, jen_hodnocene_sezony=True):
    ref = ref.set_index("SAMPLE_ID") if "SAMPLE_ID" in ref.columns else ref
    lulan = lulan.set_index("SAMPLE_ID") if "SAMPLE_ID" in lulan.columns else lulan
    spolecne = ref.index.intersection(lulan.index)

    vsech = len(spolecne)
    if jen_hodnocene_sezony:
        spolecne = spolecne[[
            any(s in str(sid) for s in HODNOCENE_SEZONY) for sid in spolecne
        ]]
    vynechano = vsech - len(spolecne)

    if vystup is None:
        vystup = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "porovnani_metrik_MZB.html",
        )

    sekce = []
    prehled = []

    # --- finalni hodnoceni ---
    if "MB_CELKEM" in ref.columns and "MB_CELKEM" in lulan.columns:
        a = pd.to_numeric(ref.loc[spolecne, "MB_CELKEM"], errors="coerce")
        b = pd.to_numeric(lulan.loc[spolecne, "MB_CELKEM"], errors="coerce")
        st = _statistiky(a, b)
        if st:
            obr = _graf(st["a"], st["b"], "MB_CELKEM", "multimetrický index")
            trida = ("dobra" if st["r"] > 0.999 else
                     "stredni" if st["r"] > 0.98 else "spatna")
            v_tride = _shoda_trid(st["a"], st["b"])
            sekce.append(f"""
            <section><h2>MB_CELKEM — finální hodnocení</h2>
            <div class="karty"><div class="karta">
              <img src="data:image/png;base64,{obr}" alt="MB_CELKEM">
              <table class="stat">
                <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
                <tr><td>korelace</td><td class="{trida}">{st['r']:.5f}</td></tr>
                <tr><td>medián rozdílu</td><td>{st['median']:+.4f}</td></tr>
                <tr><td>průměr rozdílu</td><td>{st['prumer']:+.4f}</td></tr>
                <tr><td>největší rozdíl</td><td>{st['max_abs']:.4f}</td></tr>
                <tr><td>shodných (±0,01)</td>
                    <td>{int((st['b']-st['a']).abs().lt(0.01).sum())}</td></tr>
                <tr><td>shodná třída</td><td>{v_tride:.0f} %</td></tr>
              </table>
            </div></div></section>""")
            prehled.append(("MB_CELKEM", "finální hodnocení", st))

    for i in list(range(1, 19)):
        m = f"MB{i:02d}"
        q = m + "Q"
        karty = []

        for sloupec, popisek in ((m, "hodnota metriky"), (q, "EQR")):
            if sloupec not in ref.columns or sloupec not in lulan.columns:
                continue
            a = pd.to_numeric(ref.loc[spolecne, sloupec], errors="coerce")
            b = pd.to_numeric(lulan.loc[spolecne, sloupec], errors="coerce")
            st = _statistiky(a, b)
            if st is None:
                continue
            obr = _graf(st["a"], st["b"], m, popisek)
            karty.append((popisek, st, obr))
            if sloupec == m:
                prehled.append((m, NAZVY.get(m, ""), st))

        if not karty:
            sekce.append(
                f"<section><h2>{m} — {NAZVY.get(m,'')}</h2>"
                f"<p class='chybi'>Nelze porovnat — hodnoty nejsou "
                f"k dispozici v referenční tabulce ani ve výpočtu.</p></section>"
            )
            continue

        h = [f"<section><h2>{m} — {NAZVY.get(m,'')}</h2><div class='karty'>"]
        for popisek, st, obr in karty:
            trida = ("dobra" if st["r"] > 0.999 else
                     "stredni" if st["r"] > 0.98 else "spatna")
            h.append(f"""
            <div class="karta">
              <img src="data:image/png;base64,{obr}" alt="{m} {popisek}">
              <table class="stat">
                <tr><td>počet hodnot</td><td>{st['n']}</td></tr>
                <tr><td>korelace</td><td class="{trida}">{st['r']:.5f}</td></tr>
                <tr><td>medián rozdílu</td><td>{st['median']:+.4f}</td></tr>
                <tr><td>průměr rozdílu</td><td>{st['prumer']:+.4f}</td></tr>
                <tr><td>největší rozdíl</td><td>{st['max_abs']:.4f}</td></tr>
                <tr><td>shodných (±0,001)</td>
                    <td>{st['shodnych']} ({st['shodnych']/st['n']*100:.0f} %)</td></tr>
              </table>
            </div>""")
        h.append("</div></section>")
        sekce.append("".join(h))

    radky = "".join(
        f"<tr><td>{m}</td><td>{nz}</td><td>{s['n']}</td>"
        f"<td class='{'dobra' if s['r']>0.999 else 'stredni' if s['r']>0.98 else 'spatna'}'>"
        f"{s['r']:.5f}</td><td>{s['median']:+.4f}</td>"
        f"<td>{s['shodnych']/s['n']*100:.0f} %</td></tr>"
        for m, nz, s in prehled
    )

    vysvetlivka = (
        f"""<div class="shrnuti">Zahrnuty jsou pouze <strong>jarní a podzimní</strong>
    vzorky. Letní kampaň ({vynechano} vzorků) metodika k hodnocení ekologického
    stavu nepoužívá a v datech u ní chybí část taxonů, takže by srovnání jen
    zašuměla.</div>"""
        if jen_hodnocene_sezony and vynechano else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<title>Porovnání metrik MZB s hodnotami z ARROW</title>
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
 .prehled td {{ padding: .35rem .6rem; border-bottom: 1px solid #edf2f7; }}
 .dobra {{ color: #22705a; font-weight: 600; }}
 .stredni {{ color: #975a16; font-weight: 600; }}
 .spatna {{ color: #9b2c2c; font-weight: 600; }}
 .chybi {{ color: #718096; font-style: italic; }}
 .shrnuti {{ background: #f7fafc; border-left: 4px solid #2b6cb0;
             padding: 1rem 1.2rem; margin: 1.5rem 0; }}
</style></head><body>
<h1>Porovnání metrik MZB s hodnotami z ARROW</h1>
<p>Porovnáno <strong>{len(spolecne)}</strong> vzorků makrozoobentosu.
Pro každou metriku je bodový graf hodnoty z ARROW proti hodnotě
spočítané LULANem; červená čára značí dokonalou shodu.</p>
{vysvetlivka}

<h2>Přehled</h2>
<table class="prehled">
 <tr><th>metrika</th><th>název</th><th>n</th><th>korelace</th>
     <th>medián rozdílu</th><th>shodných</th></tr>
 {radky}
</table>
{"".join(sekce)}
</body></html>"""

    with open(vystup, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport ulozen do {vystup}")
    return vystup
