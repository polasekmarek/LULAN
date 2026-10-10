"""Vytahne EQR prevodni tabulky z puvodniho calc_indexes.py pomoci AST."""
import ast, textwrap, json, sys, re

SRC = 'src/calc_indexes.py'
lines = open(SRC, encoding='utf-8', errors='replace').read().split('\n')

def grab(start, end):
    seg = '\n'.join(lines[start-1:end])
    return textwrap.dedent(seg)

# region KROK 8 MZB perennial broditelne: radky 1500..2374
block = grab(1500, 2374)
tree = ast.parse(block)

def lit(node):
    return ast.literal_eval(node)

def parse_cond(test):
    """vrati (klic, hodnota) z porovnani typu locality_type == "2-1" """
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
        return test.left.id, lit(test.comparators[0])
    raise ValueError(ast.dump(test))

# --- parsovani teles ---
NAN_RE = re.compile(r"metrics\['(MB\d\d)'\] = float\('nan'\)")

def parse_leaf(body):
    """Vrati dict: nan_metrics, eqr (metric -> ast vyraz), weights"""
    nan_metrics, eqr, weights, denom = [], {}, {}, None
    for st in body:
        if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Subscript):
            t = st.targets[0]
            name = t.value.id
            key = lit(t.slice)
            if name == 'metrics':
                nan_metrics.append(key)
            elif name == 'eqr_values':
                eqr[key.replace('_EQR','')] = ast.unparse(st.value)
        elif isinstance(st, ast.If):
            # bud guard 'if metrics[..] ...' nebo 'if eqr_values:'
            sub = parse_leaf(st.body)
            nan_metrics += sub['nan']
            eqr.update(sub['eqr'])
            if sub['weights']:
                weights, denom = sub['weights'], sub['denom']
        elif isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name):
            if st.targets[0].id == 'final_eqr' and isinstance(st.value, ast.BinOp):
                w, d = parse_final(st.value)
                if w: weights, denom = w, d
    return {'nan': nan_metrics, 'eqr': eqr, 'weights': weights, 'denom': denom}

def parse_final(node):
    """final_eqr = (w1*get(M1)+...)/(w1+w2+...)"""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
        return None, None
    num, den = node.left, node.right
    weights = {}
    def walk_num(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            walk_num(n.left); walk_num(n.right)
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            w = lit(n.left)
            call = n.right
            key = lit(call.args[0]).replace('_EQR','')
            weights[key] = weights.get(key, 0) + w   # zachytit duplicity
        else:
            raise ValueError(ast.unparse(n))
    walk_num(num)
    terms = []
    def walk_den(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            walk_den(n.left); walk_den(n.right)
        else:
            terms.append(lit(n))
    walk_den(den)
    return weights, terms

# --- prochazeni if/elif stromu ---
out = {}
def walk(node, ctx):
    while node is not None:
        k, v = parse_cond(node.test)
        vals = v if isinstance(v, list) else [v]
        c = dict(ctx)
        # jsou uvnitr dalsi ify na locality_type/season/strahler?
        inner = [s for s in node.body if isinstance(s, ast.If) and
                 isinstance(s.test, ast.Compare) and isinstance(s.test.left, ast.Name)
                 and s.test.left.id in ('season','strahler','locality_type')]
        for vv in vals:
            c2 = dict(c); c2[k] = vv
            if inner:
                walk(inner[0], c2)
            else:
                out[(c2.get('locality_type'), c2.get('season'), c2.get('strahler'))] = parse_leaf(node.body)
        node = node.orelse[0] if (len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)) else None

top = [s for s in tree.body if isinstance(s, ast.If)]
for t in top:
    walk(t, {})

print(f"nalezeno kombinaci: {len(out)}")
res = {}
for (lt, se, st), d in sorted(out.items(), key=lambda x: (x[0][0] or '', x[0][1] or '', x[0][2] or 0)):
    res[f"{lt}|{se}|{st}"] = {
        'nan': d['nan'],
        'eqr': d['eqr'],
        'weights': d['weights'],
        'denom_terms': d['denom'],
        'denom_sum': round(sum(d['denom']), 6) if d['denom'] else None,
        'weight_sum': round(sum(d['weights'].values()), 6) if d['weights'] else None,
    }
json.dump(res, open('_tools/eqr_raw.json','w'), indent=1, ensure_ascii=False)
for k, v in res.items():
    flag = '' if v['denom_sum'] == v['weight_sum'] else '  <<< NESEDI'
    print(f"{k:16s} metrik={len(v['eqr']):2d} vah={len(v['weights']):2d} denom={v['denom_sum']} sumvah={v['weight_sum']}{flag}")
