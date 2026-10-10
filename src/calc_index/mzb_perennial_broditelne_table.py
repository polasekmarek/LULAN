"""
EQR prevodni tabulka - MZB, perennial (staletekouci), broditelne toky.

Klic:  (typ_lokality, sezona, strahler)
  typ_lokality podle nadmorske vysky a Strahlerova radu:
    2-1   = 200-500 m n.m., Strahler 1-3
    3-1   = 500-800 m n.m., Strahler 1-3
    1-2   = 0-200 m n.m., Strahler 4-6
    2-2   = 200-500 m n.m., Strahler 4-6
    3-2   = 500-800 m n.m., Strahler 4-6
    12-3  = 0-500 m n.m., Strahler 7-9
  sezona: "J" = jaro (1.1.-31.8.), "P" = podzim (1.9.-31.12.)
  strahler: None = pro dany typ se Strahleruv rad nerozlisuje

Hodnota: {metrika: (dolni_mez, horni_mez, invertovat, vaha)}
  EQR = (hodnota - dolni_mez) / (horni_mez - dolni_mez)
  invertovat=True  ->  EQR = 1 - vyse uvedene (metrika roste se znecistenim)
  vaha            ->  vaha metriky ve vazenem prumeru multimetriky

Tabulka byla strojove vytazena z puvodniho stromu if/elif v calc_indexes.py
a numericky overena proti nemu. Provedene opravy viz OPRAVY.md.
"""

EQR_TABLE = {
    # --- 2-1: 200-500 m n.m., Strahler 1-3 ---
    ('2-1', 'J', None): {   # jaro, vsechny Strahlery
        'MB01': (0.65, 3.2, True, 1),
        'MB02': (0.0, 58.0, False, 0.7),
        'MB03': (0.03, 0.81, False, 0.5),
        'MB04': (0.0, 70.0, False, 0.7),
        'MB05': (0.4, 7.7, False, 0.9),
        'MB06': (0.0, 41.0, False, 0.7),
        'MB07': (0.0, 1.0, False, 1.1),
    },
    ('2-1', 'P', None): {   # podzim, vsechny Strahlery
        'MB01': (0.9, 3.6, True, 0.9),
        'MB02': (0.0, 56.0, False, 0.8),
        'MB06': (0.0, 35.0, False, 0.8),
        'MB07': (0.0, 1.0, False, 1.2),
        'MB08': (0.0, 49.0, False, 0.6),
        'MB13': (0.0, 28.0, False, 0.9),
        'MB15': (0.0, 42.0, False, 0.7),
    },

    # --- 3-1: 500-800 m n.m., Strahler 1-3 ---
    ('3-1', 'J', None): {   # jaro, vsechny Strahlery
        'MB01': (0.55, 3.2, True, 1),
        'MB02': (0.0, 58.0, False, 1),
        'MB03': (0.03, 0.86, False, 0.7),
        'MB05': (0.4, 8.4, False, 1),
        'MB07': (0.0, 1.0, False, 1.3),
        'MB08': (0.0, 25.0, False, 1.0),
        'MB09': (0.0, 38.0, False, 0.6),
    },
    ('3-1', 'P', None): {   # podzim, vsechny Strahlery
        'MB01': (0.8, 3.6, True, 0.9),
        'MB02': (0.0, 50.0, False, 0.8),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB08': (0.0, 48.0, False, 0.6),
        'MB09': (0.0, 31.0, False, 0.5),
        'MB13': (0.0, 30.0, False, 0.9),
        'MB15': (0.0, 44.0, False, 0.5),
    },

    # --- 1-2: 0-200 m n.m., Strahler 4-6 ---
    ('1-2', 'J', 4): {   # jaro, Strahler 4
        'MB01': (0.9, 3.2, True, 1),
        'MB02': (0.0, 52.0, False, 0.2),
        'MB03': (0.03, 0.83, False, 0.5),
        'MB04': (0.0, 75.0, False, 0.8),
        'MB07': (0.0, 1.0, False, 1),
        'MB10': (0.0, 23.0, False, 0.8),
        'MB12': (2.0, 32.0, False, 0.9),
    },
    ('1-2', 'J', 5): {   # jaro, Strahler 5
        'MB01': (1.1, 3.2, True, 1),
        'MB02': (0.0, 52.0, False, 0.2),
        'MB03': (0.03, 0.78, False, 0.5),
        'MB04': (0.0, 68.0, False, 0.8),
        'MB07': (0.0, 1.0, False, 1),
        'MB10': (0.0, 29.0, False, 0.8),
        'MB12': (2.0, 32.0, False, 0.9),
    },
    ('1-2', 'J', 6): {   # jaro, Strahler 6
        'MB01': (1.3, 3.2, True, 1),
        'MB02': (0.0, 52.0, False, 0.2),
        'MB03': (0.03, 0.73, False, 0.5),
        'MB04': (0.0, 60.0, False, 0.8),
        'MB07': (0.0, 1.0, False, 1),
        'MB10': (0.0, 35.0, False, 0.8),
        'MB12': (2.0, 32.0, False, 0.9),
    },
    ('1-2', 'P', 4): {   # podzim, Strahler 4
        'MB01': (1.1, 3.6, True, 1),
        'MB02': (0.0, 41.0, False, 0.4),
        'MB04': (0.0, 65.0, False, 0.4),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB10': (0.0, 25.0, False, 0.8),
        'MB13': (0.0, 23.0, False, 1),
        'MB15': (0.0, 47.0, False, 0.6),
    },
    ('1-2', 'P', 5): {   # podzim, Strahler 5
        'MB01': (1.3, 3.6, True, 1),
        'MB02': (0.0, 41.0, False, 0.4),
        'MB04': (0.0, 58.0, False, 0.4),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB10': (0.0, 25.0, False, 0.8),
        'MB13': (0.0, 23.0, False, 1),
        'MB15': (0.0, 44.0, False, 0.6),
    },
    ('1-2', 'P', 6): {   # podzim, Strahler 6
        'MB01': (1.5, 3.6, True, 1),
        'MB02': (0.0, 41.0, False, 0.4),
        'MB04': (0.0, 50.0, False, 0.4),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB10': (0.0, 25.0, False, 0.8),
        'MB13': (0.0, 23.0, False, 1),
        'MB15': (0.0, 41.0, False, 0.6),
    },

    # --- 2-2: 200-500 m n.m., Strahler 4-6 ---
    ('2-2', 'J', 4): {   # jaro, Strahler 4
        'MB01': (0.75, 3.2, True, 0.9),
        'MB02': (0.0, 57.0, False, 0.8),
        'MB03': (0.03, 0.85, False, 0.9),
        'MB04': (0.0, 75.0, False, 0.9),
        'MB05': (0.4, 8.9, False, 0.5),
        'MB06': (0.0, 45.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.2),
    },
    ('2-2', 'J', 5): {   # jaro, Strahler 5
        'MB01': (0.95, 3.2, True, 0.9),
        'MB02': (0.0, 57.0, False, 0.8),
        'MB03': (0.03, 0.81, False, 0.9),
        'MB04': (0.0, 68.0, False, 0.9),
        'MB05': (0.4, 8.9, False, 0.5),
        'MB06': (0.0, 40.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.2),
    },
    ('2-2', 'J', 6): {   # jaro, Strahler 6
        'MB01': (1.2, 3.2, True, 0.9),
        'MB02': (0.0, 57.0, False, 0.8),
        'MB03': (0.03, 0.76, False, 0.9),
        'MB04': (0.0, 60.0, False, 0.9),
        'MB05': (0.4, 8.9, False, 0.5),
        'MB06': (0.0, 33.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.2),
    },
    ('2-2', 'P', 4): {   # podzim, Strahler 4
        'MB01': (1.1, 3.6, True, 1),
        'MB02': (0.0, 55.0, False, 0.7),
        'MB06': (0.0, 40.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.3),
        'MB13': (0.0, 29.0, False, 1),
        'MB14': (0.0, 18.0, False, 0.8),
        'MB15': (0.0, 47.0, False, 0.8),
    },
    ('2-2', 'P', 5): {   # podzim, Strahler 5
        'MB01': (1.2, 3.6, True, 1),
        'MB02': (0.0, 50.0, False, 0.7),
        'MB06': (0.0, 35.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.3),
        'MB13': (0.0, 32.0, False, 1),
        'MB14': (0.0, 15.0, False, 0.8),
        'MB15': (0.0, 42.0, False, 0.8),
    },
    ('2-2', 'P', 6): {   # podzim, Strahler 6
        'MB01': (1.3, 3.6, True, 1),
        'MB02': (0.0, 45.0, False, 0.7),
        'MB06': (0.0, 30.0, False, 1),
        'MB07': (0.0, 1.0, False, 1.3),
        'MB13': (0.0, 35.0, False, 1),
        'MB14': (0.0, 12.0, False, 0.8),
        'MB15': (0.0, 37.0, False, 0.8),
    },

    # --- 3-2: 500-800 m n.m., Strahler 4-6 ---
    ('3-2', 'J', 4): {   # jaro, Strahler 4
        'MB01': (0.6, 3.2, True, 0.9),
        'MB02': (0.0, 60.0, False, 1),
        'MB03': (0.03, 0.9, False, 0.7),
        'MB05': (0.4, 8.4, False, 0.5),
        'MB07': (0.0, 1.0, False, 1.2),
        'MB08': (0.0, 24.0, False, 0.7),
        'MB09': (0.0, 40.0, False, 1),
    },
    ('3-2', 'J', 5): {   # jaro, Strahler 5
        'MB01': (0.7, 3.2, True, 0.9),
        'MB02': (0.0, 60.0, False, 1),
        'MB03': (0.03, 0.9, False, 0.7),
        'MB05': (0.4, 8.4, False, 0.5),
        'MB07': (0.0, 1.0, False, 1.2),
        'MB08': (0.0, 24.0, False, 0.7),
        'MB09': (0.0, 33.0, False, 1),
    },
    ('3-2', 'J', 6): {   # jaro, Strahler 6
        'MB01': (0.95, 3.2, True, 0.9),
        'MB02': (0.0, 60.0, False, 1),
        'MB03': (0.03, 0.9, False, 0.7),
        'MB05': (0.4, 8.4, False, 0.5),
        'MB07': (0.0, 1.0, False, 1.2),
        'MB08': (0.0, 24.0, False, 0.7),
        'MB09': (0.0, 27.0, False, 1),
    },
    ('3-2', 'P', 4): {   # podzim, Strahler 4
        'MB01': (0.9, 3.6, True, 0.8),
        'MB02': (0.0, 50.0, False, 0.7),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB09': (0.0, 30.0, False, 0.7),
        'MB13': (0.0, 31.0, False, 0.9),
        'MB14': (0.0, 30.0, False, 0.6),
        'MB15': (0.0, 44.0, False, 0.7),
    },
    ('3-2', 'P', 5): {   # podzim, Strahler 5
        'MB01': (1.1, 3.6, True, 0.8),
        'MB02': (0.0, 48.0, False, 0.7),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB09': (0.0, 28.0, False, 0.7),
        'MB13': (0.0, 34.0, False, 0.9),
        'MB14': (0.0, 28.0, False, 0.6),
        'MB15': (0.0, 41.0, False, 0.7),
    },
    ('3-2', 'P', 6): {   # podzim, Strahler 6
        'MB01': (1.3, 3.6, True, 0.8),
        'MB02': (0.0, 46.0, False, 0.7),
        'MB07': (0.0, 1.0, False, 1.1),
        'MB09': (0.0, 26.0, False, 0.7),
        'MB13': (0.0, 37.0, False, 0.9),
        'MB14': (0.0, 26.0, False, 0.6),
        'MB15': (0.0, 38.0, False, 0.7),
    },

    # --- 12-3: 0-500 m n.m., Strahler 7-9 ---
    ('12-3', 'J', 7): {   # jaro, Strahler 7
        'MB01': (1.4, 3.2, True, 0.8),
        'MB02': (0.0, 55.0, False, 1),
        'MB03': (0.03, 0.69, False, 0.9),
        'MB04': (0.0, 58.0, False, 0.6),
        'MB07': (0.0, 1.0, False, 1.4),
        'MB10': (0.0, 38.0, False, 1),
        'MB11': (2.0, 28.0, False, 0.5),
        'MB12': (2.0, 37.0, False, 0.7),
    },
    ('12-3', 'J', 8): {   # jaro, Strahler 8
        'MB01': (1.7, 3.2, True, 0.8),
        'MB02': (0.0, 45.0, False, 1),
        'MB03': (0.03, 0.56, False, 0.9),
        'MB04': (0.0, 43.0, False, 0.6),
        'MB07': (0.0, 1.0, False, 1.4),
        'MB11': (2.0, 24.0, False, 0.5),
        'MB12': (2.0, 33.0, False, 0.7),
    },
    ('12-3', 'J', 9): {   # jaro, Strahler 9
        'MB01': (1.7, 3.2, True, 0.8),
        'MB02': (0.0, 45.0, False, 1),
        'MB03': (0.03, 0.56, False, 0.9),
        'MB04': (0.0, 43.0, False, 0.6),
        'MB07': (0.0, 1.0, False, 1.4),
        'MB11': (2.0, 24.0, False, 0.5),
        'MB12': (2.0, 33.0, False, 0.7),
    },
    ('12-3', 'P', 7): {   # podzim, Strahler 7
        'MB01': (1.55, 3.6, True, 0.8),
        'MB02': (0.0, 41.0, False, 0.9),
        'MB04': (0.0, 58.0, False, 0.9),
        'MB07': (0.0, 1.0, False, 1.5),
        'MB10': (0.0, 27.0, False, 1),
        'MB11': (2.0, 23.0, False, 0.4),
        'MB13': (0.0, 30.0, False, 1.1),
        'MB15': (0.0, 37.0, False, 0.7),
    },
    ('12-3', 'P', 8): {   # podzim, Strahler 8
        'MB01': (1.75, 3.6, True, 0.8),
        'MB02': (0.0, 36.0, False, 0.9),
        'MB04': (0.0, 51.0, False, 0.9),
        'MB07': (0.0, 1.0, False, 1.5),
        'MB11': (2.0, 19.0, False, 0.4),
        'MB13': (0.0, 28.0, False, 1.1),
        'MB15': (0.0, 37.0, False, 0.7),
    },
    ('12-3', 'P', 9): {   # podzim, Strahler 9
        'MB01': (1.75, 3.6, True, 0.8),
        'MB02': (0.0, 36.0, False, 0.9),
        'MB04': (0.0, 51.0, False, 0.9),
        'MB07': (0.0, 1.0, False, 1.5),
        'MB11': (2.0, 19.0, False, 0.4),
        'MB13': (0.0, 28.0, False, 1.1),
        'MB15': (0.0, 37.0, False, 0.7),
    },

}

# Metriky, ktere se pro danou kombinaci vubec nepouzivaji, se jednoduse
# v EQR_TABLE nevyskytuji - neni potreba je nikde nastavovat na NaN.
