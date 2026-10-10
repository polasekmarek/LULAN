"""
Vymezene utvary stojatych vod (Priloha 1 metodiky).

Zdroj:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, Priloha 1.

77 utvaru: 55 nadrzi + 18 rybniku (silne ovlivnene, HMWB) a 4 tezebni jamy
(umele, AWB).

Slouzi ke trem vecem:

  1. predvyplneni abiotickych parametru lokality, kdyz uzivatel zada
     profil na nekterem z vymezenych utvaru
  2. rozpoznani rybniku - podle ryb se nehodnoti (kap. 3)
  3. kontrola vlastni typologie proti hodnotam z metodiky

POZOR: kod v `kod_metodika` je opsany z Prilohy 1 vcetne peti mist, kde
neodpovida vlastnim pravidlum z Tabulky 1 - viz `ROZPORY` a OPRAVY.md,
kap. 3.1. Pro vypocet se vzdy pouziva typ odvozeny z parametru, ne tento
kod.
"""

from __future__ import annotations

#: Utvary z Prilohy 1.
#: (ID_UTVARU, typ, urceni, mnm, zmax, plocha_km2, zprum, TRT, kod z metodiky)
UTVARY = (
    ("BER_0165_J", "nádrž", "HMWB", 354.1, 28.5, 3.642, 9.3, 0.14, "2BC21F22"),
    ("BER_0285_J", "nádrž", "HMWB", 313.6, 7.0, 1.06, 2.7, 0.02, "2BC11F11"),
    ("BER_0325_J", "nádrž", "HMWB", 521.6, 31.6, 1.358, 12.5, 0.37, "2BC21F22"),
    ("BER_0585_J", "nádrž", "HMWB", 507.1, 22.2, 1.388, 8.2, 0.29, "2BC21F22"),
    ("BER_2015_J", "nádrž", "HMWB", 533.0, 20.0, 0.624, 6.2, 0.13, "2BC21F23"),
    ("DVL_0015_J", "nádrž", "HMWB", 351.2, 67.6, 14.058, 26.5, 0.25, "2BC11F12"),
    ("DVL_0095_J", "nádrž", "HMWB", 270.6, 58.0, 12.748, 23.2, 0.1, "2BC21F22"),
    ("DVL_0125_J", "rybník", "HMWB", 615.3, 9.0, 1.955, 4.3, 0.97, "2BC11F13"),
    ("DVL_0495_J", "nádrž", "HMWB", 377.0, 53.9, 13.843, 18.6, 1.22, "2BC21F23"),
    ("DYJ_0045_J", "nádrž", "HMWB", 554.6, 18.1, 0.45, 5.6, 0.77, "2BC21F23"),
    ("DYJ_0155_J", "nádrž", "HMWB", 348.5, 41.7, 6.464, 20.0, 0.42, "2BC21F22"),
    ("DYJ_0185_J", "rybník", "HMWB", 195.0, 3.0, 1.818, 1.5, 0.27, "1BC12F12"),
    ("DYJ_0295_J", "nádrž", "HMWB", 171.4, 3.9, 6.532, 2.2, 0.03, "1BC11F11"),
    ("DYJ_0345_J", "nádrž", "HMWB", 464.5, 63.0, 1.871, 24.7, 0.42, "2BC21F22"),
    ("DYJ_0485_J", "nádrž", "HMWB", 229.1, 18.1, 1.973, 7.4, 0.06, "2BC21F21"),
    ("DYJ_0525_J", "nádrž", "HMWB", 360.1, 26.3, 0.978, 10.1, 0.52, "2BC22F23"),
    ("DYJ_0565_J", "nádrž", "HMWB", 430.0, 36.0, 0.505, 12.6, 0.63, "2BC21F23"),
    ("DYJ_0845_J", "nádrž", "HMWB", 522.1, 17.5, 0.485, 5.9, 0.73, "2BC21F23"),
    ("DYJ_0935_J", "nádrž", "HMWB", 380.5, 84.5, 4.648, 26.4, 0.61, "2BC21F23"),
    ("DYJ_0945_J", "nádrž", "HMWB", 303.2, 34.7, 0.749, 14.5, 0.08, "2BC21F21"),
    ("DYJ_1005_J", "nádrž", "HMWB", 476.9, 29.3, 0.878, 12.1, 0.24, "2BC22F22"),
    ("DYJ_1175_J", "rybník", "HMWB", 175.0, 2.0, 1.582, 1.0, 0.27, "1BC12F12"),
    ("DYJ_1185_J", "rybník", "HMWB", 186.0, 3.0, 1.275, 1.5, 0.27, "1BC12F12"),
    ("DYJ_1186_J", "rybník", "HMWB", 183.0, 3.0, 1.549, 1.5, 0.27, "1BC12F12"),
    ("DYJ_1195_J", "nádrž", "HMWB", 170.4, 3.8, 9.322, 2.3, 0.02, "1BC11F11"),
    ("DYJ_1205_J", "nádrž", "HMWB", 170.4, 6.8, 14.746, 4.5, 0.06, "1BC11F11"),
    ("DYJ_1255_J", "rybník", "HMWB", 170.0, 2.0, 2.477, 1.0, 0.27, "1BC12F12"),
    ("HOD_0365_J", "nádrž", "HMWB", 496.0, 60.5, 8.284, 26.6, 1.1, "2BC21F23"),
    ("HOD_0385_J", "nádrž", "HMWB", 428.5, 28.9, 2.381, 13.0, 0.16, "2BC21F22"),
    ("HOD_0475_J", "nádrž", "HMWB", 501.6, 57.0, 2.335, 17.9, 0.44, "2BC22F22"),
    ("HOD_0535_J", "nádrž", "HMWB", 506.8, 25.3, 0.492, 11.0, 0.11, "2BC22F22"),
    ("HOD_0585_J", "nádrž", "HMWB", 303.1, 12.5, 0.71, 4.7, 0.21, "2BC12F12"),
    ("HOD_0625_J", "nádrž", "HMWB", 291.1, 23.5, 2.169, 9.4, 1.15, "2BC22F23"),
    ("HOD_0815_J", "nádrž", "HMWB", 275.6, 24.0, 2.361, 9.7, 0.56, "2BC22F23"),
    ("HSL_0185_J", "nádrž", "HMWB", 315.6, 13.6, 0.841, 5.4, 0.01, "2BC21F21"),
    ("HSL_0405_J", "nádrž", "HMWB", 280.5, 13.5, 9.881, 6.9, 4.52, "2BC22F23"),
    ("HSL_0475_J", "nádrž", "HMWB", 468.6, 26.6, 0.929, 10.4, 0.07, "2BC21F21"),
    ("HSL_0735_J", "nádrž", "HMWB", 420.4, 5.4, 0.996, 2.2, 0.08, "2BC12F11"),
    ("HSL_0955_J", "nádrž", "HMWB", 597.9, 8.6, 0.776, 3.2, 0.06, "2BC11F11"),
    ("HSL_0995_J", "nádrž", "HMWB", 486.8, 28.2, 2.102, 9.2, 0.21, "2BC21F22"),
    ("HSL_1295_J", "nádrž", "HMWB", 323.8, 31.8, 1.038, 8.9, 0.59, "2BC21F23"),
    ("HSL_1465_J", "rybník", "HMWB", 205.0, 2.8, 1.739, 1.9, 0.03, "2BC12F11"),
    ("HSL_1845_J", "nádrž", "HMWB", 731.0, 37.0, 1.399, 15.1, 0.82, "3BC21F23"),
    ("HSL_1895_J", "nádrž", "HMWB", 766.5, 16.5, 0.846, 7.5, 0.32, "3BC21F22"),
    ("HVL_0095_J", "nádrž", "HMWB", 729.0, 4.0, 1.221, 1.5, 0.27, "3BC11F12"),
    ("HVL_0105_J", "nádrž", "HMWB", 724.9, 19.3, 45.137, 6.0, 0.67, "3BC21F23"),
    ("HVL_0305_J", "nádrž", "HMWB", 470.7, 43.2, 1.915, 15.8, 0.23, "2BC21F22"),
    ("HVL_0395_J", "rybník", "HMWB", 405.0, 3.8, 2.387, 1.9, 0.43, "2BC11F12"),
    ("HVL_0445_J", "rybník", "HMWB", 395.0, 3.0, 3.664, 1.5, 0.17, "2BC12F12"),
    ("HVL_0475_J", "nádrž", "HMWB", 370.1, 17.5, 2.69, 7.6, 0.02, "2BC21F21"),
    ("HVL_0545_J", "rybník", "HMWB", 535.0, 3.0, 1.829, 1.5, 0.27, "2BC11F12"),
    ("HVL_0555_J", "rybník", "HMWB", 468.0, 6.0, 1.974, 2.6, 0.36, "2BC11F12"),
    ("HVL_0605_J", "rybník", "HMWB", 422.0, 3.0, 1.965, 1.5, 0.27, "2BC12F12"),
    ("HVL_0625_J", "rybník", "HMWB", 430.0, 3.0, 1.215, 1.5, 0.27, "2BC12F12"),
    ("HVL_0635_J", "rybník", "HMWB", 426.0, 3.0, 4.273, 1.5, 0.05, "2BC11F11"),
    ("HVL_0646_J", "rybník", "HMWB", 445.0, 3.0, 3.106, 1.5, 0.27, "2BC12F12"),
    ("HVL_0655_J", "rybník", "HMWB", 425.0, 3.0, 2.612, 1.5, 0.27, "2BC12F12"),
    ("HVL_0676_J", "rybník", "HMWB", 430.0, 3.0, 3.764, 1.5, 0.27, "2BC12F12"),
    ("HVL_0835_J", "rybník", "HMWB", 460.0, 3.0, 2.013, 1.5, 0.27, "2BC11F12"),
    ("HVL_1035_J", "nádrž", "HMWB", 352.6, 8.0, 1.351, 2.8, 0.0, "2BC11F11"),
    ("HVL_1055_J", "nádrž", "HMWB", 351.2, 45.0, 6.082, 13.3, 0.09, "2BC11F11"),
    ("HVL_1525_J", "nádrž", "HMWB", 351.2, 45.0, 2.784, 13.1, 0.05, "2BC11F11"),
    ("MOV_0915_J", "nádrž", "HMWB", 273.6, 13.9, 0.548, 5.2, 0.16, "2BC21F22"),
    ("MOV_0985_J", "nádrž", "HMWB", 333.4, 34.4, 0.64, 13.6, 1.59, "2BC21F23"),
    ("MOV_1195_J", "nádrž", "HMWB", 316.4, 27.6, 0.731, 12.1, 0.56, "2BC22F23"),
    ("OHL_0045_J", "nádrž", "HMWB", 513.4, 51.4, 1.125, 18.6, 0.24, "2BC21F22"),
    ("OHL_0185_J", "nádrž", "HMWB", 439.2, 16.6, 6.359, 7.4, 0.44, "2BC21F22"),
    ("OHL_0225_J", "nádrž", "HMWB", 504.7, 38.1, 1.157, 15.8, 0.94, "2BC21F23"),
    ("OHL_0305_J", "těžební jáma", "AWB", 400.0, 60.0, 4.824, 25.0, 2.47,
     "2BC22F23"),
    ("OHL_0575_J", "nádrž", "HMWB", 269.0, 42.0, 11.8, 19.3, 0.24, "2BC21F22"),
    ("OHL_0825_J", "těžební jáma", "AWB", 195.0, 75.0, 1.44, 22.0, 1.0,
     "1BC22F23"),
    ("OHL_0835_J", "těžební jáma", "AWB", 245.0, 60.0, 0.629, 20.0, 1.0,
     "2BC22F23"),
    ("OHL_0855_J", "těžební jáma", "AWB", 148.0, 25.0, 2.503, 15.0, 1.0,
     "1BC22F23"),
    ("OHL_1075_J", "nádrž", "HMWB", 268.0, 4.0, 2.633, 2.0, 0.49, "2BC12F12"),
    ("OHL_1295_J", "nádrž", "HMWB", 732.8, 44.1, 3.185, 14.6, 1.48, "3BC21F23"),
    ("OHL_1335_J", "nádrž", "HMWB", 737.1, 47.2, 1.395, 15.0, 0.48, "3BC21F22"),
    ("OHL_2075_J", "nádrž", "HMWB", 442.2, 12.2, 3.725, 4.4, 0.07, "2BC11F11"),
)

#: Utvary, u kterych kod z Prilohy 1 neodpovida pravidlum z Tabulky 1.
#: {ID_UTVARU: (kod_z_prilohy, kod_podle_pravidel, vysvetleni)}
ROZPORY = {
    "BER_2015_J": ("2BC21F23", "2BC21F22",
                   "TRT 0,13 spadá podle Tab. 1 do H=2, Příloha 1 uvádí H=3"),
    "DVL_0015_J": ("2BC11F12", "2BC21F22",
                   "Orlík III: zmax 67,6 m a zprum 26,5 m odpovídají D=2 "
                   "a G=2, Příloha 1 uvádí D=1 a G=1"),
    "DVL_0095_J": ("2BC21F22", "2BC21F21",
                   "Slapy: TRT vytištěno 0,10, což je podle Tab. 1 H=1; "
                   "Příloha 1 uvádí H=2 — nejspíš zaokrouhlení skutečné "
                   "hodnoty nad 0,1"),
    "HVL_1055_J": ("2BC11F11", "2BC21F21",
                   "Orlík I: zmax 45 m a zprum 13,3 m odpovídají D=2 a G=2"),
    "HVL_1525_J": ("2BC11F11", "2BC21F21",
                   "Orlík II: zmax 45 m a zprum 13,1 m odpovídají D=2 a G=2"),
}

#: Rychly pristup podle ID utvaru.
PODLE_ID = {u[0]: u for u in UTVARY}


def parametry(id_utvaru):
    """Abioticke parametry utvaru z Prilohy 1.

    Args:
        id_utvaru: napr. "BER_0165_J"

    Returns:
        dict s klici MNM, MAX_HLOUBKA, PLOCHA_KM2, PRUM_HLOUBKA, TRT
        a KATEGORIE; None, kdyz utvar v Priloze 1 neni
    """
    u = PODLE_ID.get(id_utvaru)
    if u is None:
        return None
    return {
        "KATEGORIE": "J",
        "MNM": u[3],
        "MAX_HLOUBKA": u[4],
        "PLOCHA_KM2": u[5],
        "PRUM_HLOUBKA": u[6],
        "TRT": u[7],
    }


def je_rybnik(id_utvaru):
    """True pro utvary typu rybnik - podle ryb se nehodnoti (kap. 3)."""
    u = PODLE_ID.get(id_utvaru)
    return u is not None and u[1] == "rybník"


def je_stojata_voda(id_utvaru):
    """True, kdyz utvar patri mezi vymezene utvary kategorie jezero."""
    return id_utvaru in PODLE_ID
