"""Prevede EQR vyrazy na kanonicky tvar (lo, hi, invert) a overi ekvivalenci."""
import json, ast, random, math

raw = json.load(open('_tools/eqr_raw.json'))

SUSPECT = []

def canon(expr, metric, key=''):
    """vrati (lo, hi, invert, lo_num) - lo_num je posun skutecne pouzity v citateli"""
    t = ast.parse(expr, mode='eval').body
    invert = False
    if isinstance(t, ast.BinOp) and isinstance(t.op, ast.Sub) and isinstance(t.left, ast.Constant):
        assert t.left.value == 1, expr
        invert = True
        t = t.right
    assert isinstance(t, ast.BinOp) and isinstance(t.op, ast.Div), expr
    num, den = t.left, t.right
    # citatel
    def strip(n):
        if isinstance(n, ast.BoolOp):   # (m or 0)
            return strip(n.values[0])
        return n
    num = strip(num)
    lo = 0.0
    if isinstance(num, ast.BinOp) and isinstance(num.op, ast.Sub):
        lo = ast.literal_eval(num.right)
        inner = strip(num.left)
        assert isinstance(inner, ast.Subscript), expr
    else:
        assert isinstance(num, ast.Subscript), expr
    # jmenovatel
    if isinstance(den, ast.BinOp) and isinstance(den.op, ast.Sub):
        hi_, lo_ = ast.literal_eval(den.left), ast.literal_eval(den.right)
        if abs(lo_ - lo) > 1e-9:
            SUSPECT.append(f"{key} {metric}: citatel posunut o {lo}, jmenovatel o {lo_}  ->  {expr}")
        hi = hi_
        lo_den = lo_
    else:
        hi = ast.literal_eval(den)
        lo_den = 0.0
        if lo != 0.0:
            SUSPECT.append(f"{key} {metric}: citatel posunut o {lo}, jmenovatel bez posunu -> {expr}")
    return float(lo), float(hi), invert, float(lo_den)

out, problems = {}, []
for key, blk in raw.items():
    tab = {}
    for m, expr in blk['eqr'].items():
        if expr == "float('nan')":
            SUSPECT.append(f"{key} {m}: EQR primo nastaveno na NaN -> {expr}")
            continue
        lo, hi, inv, lo_den = canon(expr, m, key)
        # kontrola ekvivalence numericky proti PUVODNIMU vyrazu
        for _ in range(50):
            v = random.uniform(-5, 100)
            old = eval(expr, {}, {'metrics': {m: v}})
            new = (v - lo)/(hi - lo_den)
            if inv: new = 1 - new
            assert abs(old - new) < 1e-9, (key, m, expr, old, new)
        tab[m] = {'lo': lo, 'hi': hi, 'invert': inv, 'w': blk['weights'].get(m),
                  'lo_den': lo_den, 'expr': expr}
    # kontrola vah
    extra = set(blk['weights']) - set(blk['eqr'])
    if extra:
        problems.append(f"{key}: vahy pro nepocitane metriky {sorted(extra)}")
    ws = round(sum(t['w'] for t in tab.values() if t['w'] is not None), 6)
    if blk['denom_sum'] is not None and abs(ws - blk['denom_sum']) > 1e-9:
        problems.append(f"{key}: suma vah {ws} != jmenovatel {blk['denom_sum']}")
    for m, t in tab.items():
        if t['w'] is None:
            problems.append(f"{key}: metrika {m} pocitana, ale bez vahy")
    out[key] = {'nan': blk['nan'], 'metrics': tab, 'denom_orig': blk['denom_sum']}

json.dump(out, open('_tools/eqr_canon.json','w'), indent=1, ensure_ascii=False)
print(f"OK: {len(out)} kombinaci, vsechny vyrazy numericky ekvivalentni kanonickemu tvaru")
print("\nPODEZRELE VZORCE:")
for p in SUSPECT: print(" -", p)
print("\nPROBLEMY S VAHAMI:")
for p in problems: print(" -", p)
