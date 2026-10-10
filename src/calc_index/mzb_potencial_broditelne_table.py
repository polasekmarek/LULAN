"""
EQR prevodni tabulka - MZB, ekologicky POTENCIAL, broditelne toky.

Zdroj: Opatrilova L. a kol. (2013): Metoda pro hodnoceni ekologickeho
potencialu silne ovlivnenych a umelych vodnich utvaru - kategorie reka.
VUV TGM, Praha. Tabulky 3 (jaro), 4 (podzim), 6 a 7 (vahy), 8 (tridy).
Soubor metodiky/OOV-Metoda_hodnoceni_ekologickeho_potencialu-20140821.pdf

Rozdil proti hodnoceni STAVU:
    * horni meze metrik citlivych na hydromorfologicke zmeny jsou snizene
      tak, aby odpovidaly maximalnimu ekologickemu potencialu, nikoli
      referencnimu (prirozenemu) stavu
    * u B-indexu (MB07) je horni mez snizena z 1,0 na 0,8, tj. o jednu tridu
    * saprobni index (MB01) a diverzita Margalef (MB05) zustavaji vetsinou
      shodne - na hydromorfologii nereaguji
    * vahy metrik jsou shodne s hodnocenim stavu (metodika, kap. 3.2)
    * tridy potencialu jsou ctyri, ne pet (viz common.HRANICE_POTENCIAL)

Klic:  (typ_lokality, sezona, strahler)
Hodnota: {metrika: (dolni_mez, horni_mez, invertovat, vaha)}

Mapovani nazvu metrik z metodiky na kody:
    MB01 Saprobni index      MB09 Epiritral
    MB02 Lital               MB10 Hyporitral
    MB03 RETI                MB11 Pocet taxonu pakomaru
    MB04 EPT Abu             MB12 Pocet celedi
    MB05 Diverzita Margalef  MB13 EPT Tax
    MB06 Metaritral          MB14 Pos Abu (posvatky)
    MB07 B index             MB15 Spasaci
    MB08 Jep Abu (jepice)
"""

# ---------------------------------------------------------------------------
# Vahy metrik - shodne s hodnocenim stavu (metodika Tab. 6 a Tab. 7)
# ---------------------------------------------------------------------------

VAHY = {
    # --- jaro (Tab. 6) ---
    ("2-1", "J"): {"MB01": 1, "MB05": 0.9, "MB04": 0.7, "MB03": 0.5,
                   "MB02": 0.7, "MB06": 0.7, "MB07": 1.1},
    ("3-1", "J"): {"MB01": 1, "MB05": 1, "MB08": 1, "MB03": 0.7,
                   "MB02": 1, "MB09": 0.6, "MB07": 1.3},
    ("1-2", "J"): {"MB01": 1, "MB12": 0.9, "MB04": 0.8, "MB03": 0.5,
                   "MB02": 0.2, "MB10": 0.8, "MB07": 1},
    ("2-2", "J"): {"MB01": 0.9, "MB05": 0.5, "MB04": 0.9, "MB03": 0.9,
                   "MB02": 0.8, "MB06": 1, "MB07": 1.2},
    ("3-2", "J"): {"MB01": 0.9, "MB05": 0.5, "MB08": 0.7, "MB03": 0.7,
                   "MB02": 1, "MB09": 1, "MB07": 1.2},
    # MB10 (hyporitral) se u typu 12-3 pouzije pouze pro tok 7. radu
    ("12-3", "J"): {"MB01": 0.8, "MB12": 0.7, "MB04": 0.6, "MB03": 0.9,
                    "MB02": 1, "MB10": 1, "MB11": 0.5, "MB07": 1.4},

    # --- podzim (Tab. 7) ---
    ("2-1", "P"): {"MB01": 0.9, "MB13": 0.9, "MB08": 0.6, "MB15": 0.7,
                   "MB02": 0.8, "MB06": 0.8, "MB07": 1.2},
    ("3-1", "P"): {"MB01": 0.9, "MB13": 0.9, "MB08": 0.6, "MB15": 0.5,
                   "MB02": 0.8, "MB09": 0.5, "MB07": 1.1},
    ("1-2", "P"): {"MB01": 1, "MB13": 1, "MB04": 0.4, "MB15": 0.6,
                   "MB02": 0.4, "MB10": 0.8, "MB07": 1.1},
    ("2-2", "P"): {"MB01": 1, "MB13": 1, "MB14": 0.8, "MB15": 0.8,
                   "MB02": 0.7, "MB06": 1, "MB07": 1.3},
    ("3-2", "P"): {"MB01": 0.8, "MB13": 0.9, "MB14": 0.6, "MB15": 0.7,
                   "MB02": 0.7, "MB09": 0.7, "MB07": 1.1},
    ("12-3", "P"): {"MB01": 0.8, "MB13": 1.1, "MB11": 0.4, "MB04": 0.9,
                    "MB15": 0.7, "MB02": 0.9, "MB10": 1, "MB07": 1.5},
}

# ---------------------------------------------------------------------------
# Meze metrik (dolni_mez, horni_mez, invertovat)
#
# Zapis {"*": (...)} znamena, ze mez je pro vsechny Strahlerovy rady daneho
# typu shodna; jinak je klicem konkretni rad.
# ---------------------------------------------------------------------------

MEZE = {
    # --- 2-1: toky 1.-3. radu, 200-500 m n.m. (Tab. 3 / Tab. 4) ---
    ("2-1", "J"): {
        "MB01": {"*": (0.65, 3.2, True)},
        "MB02": {"*": (0.0, 46.0, False)},
        "MB03": {"*": (0.03, 0.65, False)},
        "MB04": {"*": (0.0, 56.0, False)},
        "MB05": {"*": (0.4, 7.7, False)},
        "MB06": {"*": (0.0, 33.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("2-1", "P"): {
        "MB01": {"*": (0.9, 3.6, True)},
        "MB13": {"*": (0.0, 22.0, False)},
        "MB08": {"*": (0.0, 39.0, False)},
        "MB15": {"*": (0.0, 34.0, False)},
        "MB06": {"*": (0.0, 28.0, False)},
        "MB02": {"*": (0.0, 45.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },

    # --- 3-1: toky 1.-3. radu, 500-800 m n.m. ---
    ("3-1", "J"): {
        "MB01": {"*": (0.55, 3.2, True)},
        "MB08": {"*": (0.0, 20.0, False)},
        "MB03": {"*": (0.03, 0.69, False)},
        "MB05": {"*": (0.4, 8.4, False)},
        "MB02": {"*": (0.0, 46.0, False)},
        "MB09": {"*": (0.0, 30.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("3-1", "P"): {
        "MB01": {"*": (0.8, 3.6, True)},
        "MB13": {"*": (0.0, 24.0, False)},
        "MB08": {"*": (0.0, 38.0, False)},
        "MB15": {"*": (0.0, 35.0, False)},
        "MB09": {"*": (0.0, 25.0, False)},
        "MB02": {"*": (0.0, 40.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },

    # --- 1-2: toky 4.-6. radu, do 200 m n.m. ---
    ("1-2", "J"): {
        "MB12": {"*": (2.0, 32.0, False)},
        "MB01": {4: (0.9, 3.2, True), 5: (1.1, 3.2, True), 6: (1.3, 3.2, True)},
        "MB04": {4: (0.0, 60.0, False), 5: (0.0, 54.0, False), 6: (0.0, 48.0, False)},
        "MB10": {4: (0.0, 18.0, False), 5: (0.0, 23.0, False), 6: (0.0, 28.0, False)},
        "MB03": {4: (0.03, 0.67, False), 5: (0.03, 0.63, False), 6: (0.03, 0.59, False)},
        "MB02": {"*": (0.0, 42.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("1-2", "P"): {
        "MB01": {4: (1.1, 3.6, True), 5: (1.3, 3.6, True), 6: (1.5, 3.6, True)},
        "MB13": {"*": (0.0, 18.0, False)},
        "MB04": {4: (0.0, 52.0, False), 5: (0.0, 46.0, False), 6: (0.0, 40.0, False)},
        "MB15": {4: (0.0, 38.0, False), 5: (0.0, 35.0, False), 6: (0.0, 33.0, False)},
        "MB10": {"*": (0.0, 20.0, False)},
        "MB02": {"*": (0.0, 33.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },

    # --- 2-2: toky 4.-6. radu, 200-500 m n.m. ---
    ("2-2", "J"): {
        "MB01": {4: (0.75, 3.2, True), 5: (0.95, 3.2, True), 6: (1.2, 3.2, True)},
        "MB02": {"*": (0.0, 46.0, False)},
        "MB03": {4: (0.03, 0.69, False), 5: (0.03, 0.65, False), 6: (0.03, 0.61, False)},
        "MB04": {4: (0.0, 60.0, False), 5: (0.0, 54.0, False), 6: (0.0, 49.0, False)},
        "MB05": {"*": (0.4, 8.9, False)},
        "MB06": {4: (0.0, 36.0, False), 5: (0.0, 32.0, False), 6: (0.0, 26.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("2-2", "P"): {
        "MB01": {4: (1.1, 3.6, True), 5: (1.2, 3.6, True), 6: (1.3, 3.6, True)},
        "MB13": {4: (0.0, 23.0, False), 5: (0.0, 26.0, False), 6: (0.0, 28.0, False)},
        "MB14": {4: (0.0, 14.0, False), 5: (0.0, 12.0, False), 6: (0.0, 10.0, False)},
        "MB15": {4: (0.0, 38.0, False), 5: (0.0, 34.0, False), 6: (0.0, 30.0, False)},
        "MB06": {4: (0.0, 32.0, False), 5: (0.0, 28.0, False), 6: (0.0, 24.0, False)},
        "MB02": {4: (0.0, 44.0, False), 5: (0.0, 40.0, False), 6: (0.0, 36.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },

    # --- 3-2: toky 4.-6. radu, 500-800 m n.m. ---
    ("3-2", "J"): {
        "MB01": {4: (0.6, 3.2, True), 5: (0.7, 3.2, True), 6: (0.95, 3.2, True)},
        "MB03": {"*": (0.03, 0.73, False)},
        "MB02": {"*": (0.0, 48.0, False)},
        "MB08": {"*": (0.0, 19.0, False)},
        "MB05": {"*": (0.4, 8.4, False)},
        "MB09": {4: (0.0, 32.0, False), 5: (0.0, 26.0, False), 6: (0.0, 22.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("3-2", "P"): {
        "MB01": {4: (0.9, 3.6, True), 5: (1.1, 3.6, True), 6: (1.3, 3.6, True)},
        "MB13": {4: (0.0, 25.0, False), 5: (0.0, 27.0, False), 6: (0.0, 30.0, False)},
        "MB14": {4: (0.0, 24.0, False), 5: (0.0, 22.0, False), 6: (0.0, 21.0, False)},
        "MB15": {4: (0.0, 35.0, False), 5: (0.0, 33.0, False), 6: (0.0, 30.0, False)},
        "MB09": {4: (0.0, 24.0, False), 5: (0.0, 22.0, False), 6: (0.0, 21.0, False)},
        "MB02": {4: (0.0, 40.0, False), 5: (0.0, 38.0, False), 6: (0.0, 37.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },

    # --- 12-3: toky 7.-8. radu (broditelne), do 500 m n.m. ---
    # Metodika potencialu resi pouze rady 7 a 8. Rad 9 se zde hodnoti
    # shodne s radem 8 (stejne jako u hodnoceni stavu) - viz OPRAVY.md.
    ("12-3", "J"): {
        "MB11": {7: (2.0, 28.0, False), 8: (2.0, 24.0, False)},
        "MB12": {7: (2.0, 37.0, False), 8: (2.0, 33.0, False)},
        "MB01": {7: (1.4, 3.2, True), 8: (1.7, 3.2, True)},
        "MB10": {7: (0.0, 30.0, False)},          # pro 8. rad se nepouzije
        "MB03": {7: (0.03, 0.56, False), 8: (0.03, 0.45, False)},
        "MB02": {7: (0.0, 44.0, False), 8: (0.0, 36.0, False)},
        "MB04": {7: (0.0, 46.0, False), 8: (0.0, 34.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
    ("12-3", "P"): {
        "MB01": {7: (1.55, 3.6, True), 8: (1.75, 3.6, True)},
        "MB13": {7: (0.0, 24.0, False), 8: (0.0, 22.0, False)},
        "MB11": {7: (2.0, 23.0, False), 8: (2.0, 19.0, False)},
        "MB04": {7: (0.0, 46.0, False), 8: (0.0, 41.0, False)},
        "MB15": {"*": (0.0, 30.0, False)},
        "MB10": {7: (0.0, 22.0, False)},          # pro 8. rad se nepouzije
        "MB02": {7: (0.0, 33.0, False), 8: (0.0, 29.0, False)},
        "MB07": {"*": (0.0, 0.8, False)},
    },
}

#: Strahlerovy rady, pro ktere se jednotlive typy vyhodnocuji.
#: U typu 2-1 a 3-1 se rad nerozlisuje (klic None jako u hodnoceni stavu).
RADY = {
    "2-1": [None], "3-1": [None],
    "1-2": [4, 5, 6], "2-2": [4, 5, 6], "3-2": [4, 5, 6],
    "12-3": [7, 8, 9],
}


def _sestav():
    """Rozvine MEZE a VAHY do plne tabulky {(typ, sezona, strahler): {...}}."""
    tabulka = {}
    for (typ, sezona), meze in MEZE.items():
        vahy = VAHY[(typ, sezona)]
        for rad in RADY[typ]:
            # rad 9 u typu 12-3 pouziva meze radu 8
            hledany = 8 if (typ == "12-3" and rad == 9) else rad
            radek = {}
            for metrika, varianty in meze.items():
                mez = varianty.get("*", varianty.get(hledany))
                if mez is None:
                    continue          # metrika se pro tento rad nepouzije
                vaha = vahy.get(metrika)
                if not vaha:
                    continue
                radek[metrika] = (mez[0], mez[1], mez[2], vaha)
            tabulka[(typ, sezona, rad)] = radek
    return tabulka


EQR_TABLE = _sestav()
