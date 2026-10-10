"""Regresni porovnani puvodniho a noveho vypoctu indexu."""
import sys, os, json, math, importlib, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'qtstub'))

ap = argparse.ArgumentParser()
ap.add_argument('--limit', type=int, default=40)
args = ap.parse_args()

from PyQt6.QtSql import QSqlDatabase

def spust(modul_dir, db_path, sample_ids):
    """Nacte calc_indexes z daneho adresare a spocita vzorky."""
    for m in list(sys.modules):
        if m.startswith('calc_index') or m == 'B_index2':
            del sys.modules[m]
    sys.path = [p for p in sys.path if 'src' not in p and '_archiv' not in p]
    sys.path.insert(0, modul_dir)

    import calc_indexes as ci
    importlib.reload(ci)
    if os.environ.get('KOMPAT') == '1' and 'calc_index.common' in sys.modules:
        c = sys.modules['calc_index.common']
        c.OREZAVAT_EQR = False
        c.CHYBEJICI_METRIKA = 'nula'

    db = QSqlDatabase(db_path)
    out = {}
    for sid in sample_ids:
        try:
            out[sid] = ci.calc_indexes(sid, db)
        except Exception as e:
            out[sid] = {'ERROR': f'{type(e).__name__}: {e}'}
    db.conn.commit()
    db.close()
    return out


import sqlite3
# Stara verze cte sloupec HMCH, nova HMWB. Aby sly obe verze porovnat nad
# stejnymi daty, pridame do testovacich databazi oba sloupce.
for _db in ('/tmp/test_novy.db', '/tmp/test_stary.db'):
    _c = sqlite3.connect(_db)
    _cols = [r[1] for r in _c.execute('PRAGMA table_info(utvary)')]
    if 'HMCH' in _cols and 'HMWB' not in _cols:
        _c.execute('ALTER TABLE utvary ADD COLUMN HMWB TEXT')
        _c.execute('UPDATE utvary SET HMWB = HMCH')
    elif 'HMWB' in _cols and 'HMCH' not in _cols:
        _c.execute('ALTER TABLE utvary ADD COLUMN HMCH TEXT')
        _c.execute('UPDATE utvary SET HMCH = HMWB')
    _c.commit(); _c.close()

c = sqlite3.connect('/tmp/test_novy.db')
sql = """
SELECT s.SAMPLE_ID FROM samples s
JOIN loc l ON s.LOC_ID = l.KOD
JOIN utvary u ON l.VU = u.ID_UTVARU
JOIN (SELECT DISTINCT sample FROM data) d ON d.sample = s.SAMPLE_ID
WHERE s.TYP = ? AND u.VYSYCHAVY = ?
LIMIT ?
"""
vzorky = []
for typ, vys in [('MZB','P'), ('MZB','I'), ('FB','P'), ('FB','I'), ('MF','P')]:
    ids = [r[0] for r in c.execute(sql, (typ, vys, args.limit))]
    print(f"{typ}/{vys}: {len(ids)} vzorku")
    vzorky += ids
c.close()

print(f"\ncelkem {len(vzorky)} vzorku\n")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
stary = spust(os.path.join(ROOT, '_archiv', 'src_orig'), '/tmp/test_stary.db', vzorky)
novy  = spust(os.path.join(ROOT, 'src'), '/tmp/test_novy.db', vzorky)

json.dump({'stary': stary, 'novy': novy}, open('_tools/regrese.json','w'),
          indent=1, ensure_ascii=False, default=str)

# --- porovnani ---
def cel(d):
    if not d: return None
    for k in ('MZB_CELKEM','FB_CELKEM','MF_CELKEM','FP_CELKEM','RYBY_CELKEM'):
        if k in d: return d[k]
    return None

def cls(d):
    if not d: return None
    for k in ('MZB_CLASS','FB_CLASS','MF_CLASS'):
        if k in d: return d[k]
    return None

shoda = rozdil = chyba_stara = chyba_nova = 0
radky = []
for sid in vzorky:
    s, n = stary.get(sid), novy.get(sid)
    cs, cn = cel(s), cel(n)
    ls, ln = cls(s), cls(n)
    if s and 'ERROR' in s: chyba_stara += 1
    if n and 'ERROR' in n: chyba_nova += 1
    stejne = (cs is None and cn is None) or (
        isinstance(cs,(int,float)) and isinstance(cn,(int,float)) and abs(cs-cn) < 1e-9)
    if stejne and ls == ln:
        shoda += 1
    else:
        rozdil += 1
        radky.append((sid, cs, cn, ls, ln))

print(f"shoda:  {shoda}")
print(f"rozdil: {rozdil}")
print(f"chyby ve starem: {chyba_stara}, v novem: {chyba_nova}")
print("\nprvnich 30 rozdilu (sample, stary_EQR, novy_EQR, stara_trida, nova_trida):")
for r in radky[:30]:
    print("  ", r)
