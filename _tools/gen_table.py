"""Vygeneruje modul s EQR tabulkou pro MZB perennial broditelne."""
import json

canon = json.load(open('_tools/eqr_canon.json'))

# --- OPRAVY (viz OPRAVY.md) ---
FIXES = {
    # 3-1 jaro: MB08 mel v citateli vahu 1.0 + 0.8 (duplicita), MB06 vahu 0.7 ale
    # neni vubec pocitana. Jmenovatel 6.6 odpovida vaham 1+1+0.7+1+1.3+1+0.6.
    # Potvrzeno metodikou Opatrilova a kol. (2013), Tab. 6: Jep Abu = 1.0.
    ('3-1', 'J', None): {'drop': ['MB06'], 'w': {'MB08': 1.0}},

    # 12-3, Strahler 8 a 9: puvodni kod dal B-indexu (MB07) vahu 0.
    #
    # Tato tabulka plati POUZE pro broditelne toky - vyjmenovane utvary
    # velkych nebroditelnych rek maji vlastni metodiku (mzb_velke_reky.py),
    # ktera B-index nepouziva vubec. V praxi jsou v CR vsechny toky 8. a
    # 9. radu nebroditelne, takze vaha 0 odpovidala realite; formalne ale
    # Tab. 3 a 4 metodiky potencialu uvadeji radky "8 (broditelne)" a Tab. 6
    # a 7 pro ne vahu B-indexu 1.4 (jaro) a 1.5 (podzim).
    #
    # Pro broditelny tok 8. nebo 9. radu se proto B-index pouzije; pokud by
    # takovy tok mel patrit mezi velke reky, odchyti ho drive kontrola
    # v registry.vyber_funkci_pro_vzorek().
    # 2-2 podzim, Strahler 6: horni mez MB14 byla v puvodnim kodu 182 misto 12.
    # Rada pro Strahlery 4/5/6 je 18 / 15 / 12; hodnotu 12 potvrzuji i oficialni
    # predpocitane EQR (MB14/EQR vychazi presne 12,0 u vsech vzorku).
    ('2-2', 'P', 6): {'meze': {'MB14': (0.0, 12.0)}},

    ('12-3', 'J', 8): {'w': {'MB07': 1.4}},
    ('12-3', 'J', 9): {'w': {'MB07': 1.4}},
    ('12-3', 'P', 8): {'w': {'MB07': 1.5}},
    ('12-3', 'P', 9): {'w': {'MB07': 1.5}},
}
# MB03 v 12-3 jaro: citatel bez posunu o 0.03, jmenovatel s posunem
MB03_LO_FIX = [('12-3', 'J', 7), ('12-3', 'J', 8), ('12-3', 'J', 9)]

TYP_POPIS = {
    '2-1': '200-500 m n.m., Strahler 1-3',
    '3-1': '500-800 m n.m., Strahler 1-3',
    '1-2': '0-200 m n.m., Strahler 4-6',
    '2-2': '200-500 m n.m., Strahler 4-6',
    '3-2': '500-800 m n.m., Strahler 4-6',
    '12-3': '0-500 m n.m., Strahler 7-9',
}

rows = {}
zmeny = []
for key, blk in canon.items():
    lt, se, st = key.split('|')
    st = None if st == 'None' else int(st)
    k = (lt, se, st)
    fix = FIXES.get(k, {})
    tab = {}
    for m, t in sorted(blk['metrics'].items()):
        if m in fix.get('drop', []):
            zmeny.append(f"{lt}/{se}/{st}: metrika {m} vyrazena (mела vahu, ale nebyla pocitana)")
            continue
        w = fix.get('w', {}).get(m, t['w'])
        if w != t['w']:
            zmeny.append(f"{lt}/{se}/{st}: vaha {m} {t['w']} -> {w}")
        if w in (None, 0):
            zmeny.append(f"{lt}/{se}/{st}: metrika {m} ma vahu {w} -> vyrazena z multimetriky")
            continue
        lo, hi = t['lo'], t['hi']
        if m in fix.get('meze', {}):
            nove = fix['meze'][m]
            zmeny.append(f"{lt}/{se}/{st}: meze {m} ({lo}, {hi}) -> {nove}")
            lo, hi = nove
        if m == 'MB03' and k in MB03_LO_FIX and t['lo'] != t['lo_den']:
            lo = t['lo_den']
            zmeny.append(f"{lt}/{se}/{st}: MB03 dolni mez v citateli {t['lo']} -> {lo} (sjednoceno se jmenovatelem)")
        tab[m] = (lo, hi, t['invert'], w)
    rows[k] = tab
# vyhodit vahy pro metriky bez EQR
for key, blk in canon.items():
    lt, se, st = key.split('|'); st = None if st=='None' else int(st)
    extra = set(blk['metrics']) - set(rows[(lt,se,st)])
    
lines = []
lines.append('"""')
lines.append('EQR prevodni tabulka - MZB, perennial (staletekouci), broditelne toky.')
lines.append('')
lines.append('Klic:  (typ_lokality, sezona, strahler)')
lines.append('  typ_lokality podle nadmorske vysky a Strahlerova radu:')
for t, p in TYP_POPIS.items():
    lines.append(f'    {t:5s} = {p}')
lines.append('  sezona: "J" = jaro (1.1.-31.8.), "P" = podzim (1.9.-31.12.)')
lines.append('  strahler: None = pro dany typ se Strahleruv rad nerozlisuje')
lines.append('')
lines.append('Hodnota: {metrika: (dolni_mez, horni_mez, invertovat, vaha)}')
lines.append('  EQR = (hodnota - dolni_mez) / (horni_mez - dolni_mez)')
lines.append('  invertovat=True  ->  EQR = 1 - vyse uvedene (metrika roste se znecistenim)')
lines.append('  vaha            ->  vaha metriky ve vazenem prumeru multimetriky')
lines.append('')
lines.append('Tabulka byla strojove vytazena z puvodniho stromu if/elif v calc_indexes.py')
lines.append('a numericky overena proti nemu. Provedene opravy viz OPRAVY.md.')
lines.append('"""')
lines.append('')
lines.append('EQR_TABLE = {')
order = ['2-1','3-1','1-2','2-2','3-2','12-3']
for lt in order:
    lines.append(f'    # --- {lt}: {TYP_POPIS[lt]} ---')
    for se in ('J','P'):
        for k in sorted([k for k in rows if k[0]==lt and k[1]==se], key=lambda x: (x[2] or 0)):
            tab = rows[k]
            sez = 'jaro' if se=='J' else 'podzim'
            st_txt = f'Strahler {k[2]}' if k[2] else 'vsechny Strahlery'
            lines.append(f'    {k!r}: {{   # {sez}, {st_txt}')
            for m, (lo, hi, inv, w) in tab.items():
                lines.append(f'        {m!r}: ({lo!r}, {hi!r}, {inv!r}, {w!r}),')
            lines.append('    },')
    lines.append('')
lines.append('}')
lines.append('')
lines.append('# Metriky, ktere se pro danou kombinaci vubec nepouzivaji, se jednoduse')
lines.append('# v EQR_TABLE nevyskytuji - neni potreba je nikde nastavovat na NaN.')
lines.append('')
open('src/calc_index/mzb_perennial_broditelne_table.py','w').write('\n'.join(lines))
print("zapsano src/calc_index/mzb_perennial_broditelne_table.py")
print(f"kombinaci: {len(rows)}")
print("\nZMENY OPROTI ORIGINALU:")
for z in dict.fromkeys(zmeny): print(" -", z)
