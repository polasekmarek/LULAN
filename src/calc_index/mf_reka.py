"""
Makrofyta (MF) - toky.

Vypocet indexu MTV (Macrophyte Trophic Value) a jeho prevod na EQR podle
typu toku. Typ toku se urcuje z nadmorske vysky, Strahlerova radu a umori.

MTV se pocita v SQL primo nad tabulkami `data` a `taxalist_mf`:
    * abundance se transformuje do peti tridni stupnice
    * uplatni se pravidlo alternujiciho druhu (viz nize)
    * MTV = sum(val_trans * MTV) / sum(val_trans)

Hranice trid jsou pro kazdy typ toku jine - viz TYPY nize.

Pravidlo alternujiciho druhu
----------------------------
Metodika (kap. 5): "V případě společného výskytu druhů obou skupin
započítáváme širokovalentní druhy jen jako jeden tzv. alternující druh,
kterému přidělujeme vypočtenou hodnotou MTV a pokryvnosti, rovnající se
průměru hodnot všech širokovalentních druhů v zápise."

Stenovalentnich druhu je pet a vsechny jsou vazane na nadmorske vysky nad
500 m, takze pravidlo doslova vzato pripada v uvahu jen v typu 1.

IS ARROW ho ale v typu 1 uplatnuje i tam, kde zadny stenovalentni druh
neni - vsechny sirokovalentni druhy slouci do jednoho a index pak vyjde
jako prosty prumer jejich MTV. Odpovida to vete, kterou metodika pravidlu
predesila: "u typu vod 1 dochází ... ke zkreslení výsledků ... V tomto typu
vod je proto vhodnější provést výpočet jiným způsobem."

Overeno na vsech trech vzorcich typu 1 bez stenovalentnich druhu
(REF_027_III, REF_081_II, REF_081_III) - viz OPRAVY.md, kap. 6.
"""

from __future__ import annotations

from PyQt6.QtSql import QSqlQuery

from .common import klasifikuj, smaz_vysledky, to_float, zapis_vysledky

#: Typ toku, ve kterem se sirokovalentni druhy agreguji do alternujiciho
#: druhu i bez pritomnosti stenovalentnich druhu.
AGREGOVAT_VZDY_V_TYPU_1 = "1"


def _agregovat_vzdy(typ):
    """Ma se u tohoto typu toku agregovat i bez stenovalentnich druhu?"""
    return 1 if typ == AGREGOVAT_VZDY_V_TYPU_1 else 0


#: Definice typu toku a jejich prevodu MTV -> EQR.
#:
#: Kazdy zaznam:
#:   'popis'     - slovni popis typu
#:   'delitel'   - EQR = (MTV - 1) / delitel
#:   'stav'      - hranice trid pro hodnoceni stavu
#:   'potencial' - hranice trid pro hodnoceni potencialu
#:
#: Hranice jsou seznamy (dolni_mez, trida) serazene sestupne; pouziva se
#: ostra nerovnost (EQR > mez), stejne jako v puvodni metodice.
TYPY = {
    "1": {
        "popis": "Horske toky (nad 500 m n.m., Strahler 4-7)",
        "delitel": 9,
        "stav": [(0.83, "VD"), (0.67, "D"), (0.5, "S"), (0.25, "P")],
        "potencial": [(0.78, "VD"), (0.62, "D"), (0.45, "S"), (0.20, "P")],
    },
    "2A": {
        "popis": "Nizinne toky (pod 200 m n.m., Strahler 4-9), umori 1-2",
        "delitel": 5,
        "stav": [(0.86, "VD"), (0.62, "D"), (0.33, "S"), (0.16, "P")],
        "potencial": [(0.81, "VD"), (0.57, "D"), (0.28, "S"), (0.11, "P")],
    },
    "2B": {
        "popis": "Nizinne toky (pod 200 m n.m., Strahler 4-9), umori 3",
        "delitel": 5,
        "stav": [(0.75, "VD"), (0.5, "D"), (0.33, "S"), (0.16, "P")],
        "potencial": [(0.70, "VD"), (0.45, "D"), (0.28, "S"), (0.11, "P")],
    },
    "2": {
        "popis": "Nizinne toky (pod 200 m n.m., Strahler 4-9), umori neurceno",
        "delitel": 5,
        "stav": [(0.81, "VD"), (0.56, "D"), (0.33, "S"), (0.16, "P")],
        "potencial": [(0.76, "VD"), (0.51, "D"), (0.28, "S"), (0.11, "P")],
    },
    "3": {
        "popis": "Pahorkatinne velke toky (200-500 m n.m., Strahler 7-9)",
        "delitel": 7,
        "stav": [(0.6, "VD"), (0.49, "D"), (0.38, "S"), (0.19, "P")],
        "potencial": [(0.55, "VD"), (0.44, "D"), (0.33, "S"), (0.14, "P")],
    },
    "4A": {
        "popis": "Pahorkatinne stredni a mensi toky (200-500 m n.m., "
                 "Strahler 4-6), umori 1-2",
        "delitel": 8,
        "stav": [(0.82, "VD"), (0.64, "D"), (0.44, "S"), (0.22, "P")],
        "potencial": [(0.77, "VD"), (0.59, "D"), (0.39, "S"), (0.17, "P")],
    },
    "4B": {
        "popis": "Pahorkatinne stredni a mensi toky (200-500 m n.m., "
                 "Strahler 4-6), umori 3",
        "delitel": 8,
        "stav": [(0.77, "VD"), (0.56, "D"), (0.44, "S"), (0.22, "P")],
        "potencial": [(0.72, "VD"), (0.51, "D"), (0.39, "S"), (0.17, "P")],
    },
    "4": {
        "popis": "Pahorkatinne stredni a mensi toky (200-500 m n.m., "
                 "Strahler 4-6), umori neurceno",
        "delitel": 8,
        "stav": [(0.80, "VD"), (0.60, "D"), (0.44, "S"), (0.22, "P")],
        "potencial": [(0.75, "VD"), (0.55, "D"), (0.39, "S"), (0.17, "P")],
    },
}

#: Vypocet indexu MTV.
#:
#: Dotaz bere TRI parametry v tomto poradi:
#:   1. SAMPLE_ID
#:   2. priznak "agregovat i bez stenovalentnich druhu" (0/1) - dvakrat,
#:      protoze tataz podminka je ve filtered_data i v aggregated_poly
#:
#: K priznaku viz AGREGOVAT_VZDY_V_TYPU_1 nize.
MTV_SQL = """
WITH synonym_resolved AS (
    SELECT
        d.sample AS SAMPLE_ID,
        d.name AS original_name,
        d.val,
        t.SYN,
        COALESCE(tp.NAME, t.NAME) AS resolved_name,
        COALESCE(tp.MTV, t.MTV) AS MTV,
        COALESCE(tp.STEN_POLY, t.STEN_POLY) AS STEN_POLY
    FROM data d
    JOIN taxalist_mf t ON d.name = t.NAME
    LEFT JOIN taxalist_mf tp ON t.SYN IS NOT NULL AND tp.NAME = t.SYN
    WHERE d.sample = ?
),
transformed_data AS (
    -- Metodika (kap. 5) zna jen DVE skupiny: stenovalentni druhy, coz je
    -- vyjmenovanych pet druhu ze skupiny A+D (Fontinalis squamosa,
    -- Myriophyllum alterniflorum, Potamogeton alpinus, P. polygonifolius,
    -- Scapania undulata), a vsechny ostatni = sirokovalentni. Hodnota
    -- 'OTHER', kterou ma taxalist u ctyr druhu (Lemanea, Nuphar pumila,
    -- Ranunculus aquatilis, Zannichellia palustris), v metodice neexistuje;
    -- vsechny ctyri jsou v Tab. 6 ve skupinach B nebo C, tedy sirokovalentni.
    SELECT
        SAMPLE_ID, original_name, resolved_name, val,
        CASE
            WHEN val < 0.1 THEN 1
            WHEN val >= 0.1 AND val < 1 THEN 2
            WHEN val >= 1 AND val < 5 THEN 3
            WHEN val >= 5 AND val <= 10 THEN 4
            WHEN val > 10 THEN 5
        END AS val_transformed,
        MTV,
        CASE WHEN STEN_POLY = 'STEN' THEN 'STEN' ELSE 'POLY' END AS STEN_POLY
    FROM synonym_resolved
    WHERE STEN_POLY IS NOT NULL
),
sample_flags AS (
    SELECT
        SAMPLE_ID,
        SUM(CASE WHEN STEN_POLY = 'STEN' THEN 1 ELSE 0 END) AS sten_count,
        SUM(CASE WHEN STEN_POLY = 'POLY' THEN 1 ELSE 0 END) AS poly_count
    FROM transformed_data
    GROUP BY SAMPLE_ID
),
filtered_data AS (
    SELECT td.*
    FROM transformed_data td
    JOIN sample_flags sf ON td.SAMPLE_ID = sf.SAMPLE_ID
    WHERE NOT ((sf.sten_count > 0 OR ?) AND sf.poly_count > 1
               AND td.STEN_POLY = 'POLY')
),
aggregated_poly AS (
    SELECT
        td.SAMPLE_ID, NULL AS original_name, 'aggregated_POLY' AS resolved_name,
        NULL AS val, AVG(td.val_transformed) AS val_transformed,
        AVG(td.MTV) AS MTV, 'POLY' AS STEN_POLY
    FROM transformed_data td
    JOIN sample_flags sf ON td.SAMPLE_ID = sf.SAMPLE_ID
    WHERE td.STEN_POLY = 'POLY' AND (sf.sten_count > 0 OR ?)
          AND sf.poly_count > 1
    GROUP BY td.SAMPLE_ID
),
final_data AS (
    SELECT * FROM filtered_data
    UNION ALL
    SELECT * FROM aggregated_poly
),
mtv_result AS (
    SELECT ROUND(SUM(val_transformed * MTV * 1.0) / SUM(val_transformed * 1.0), 3)
        AS mtv_index
    FROM final_data
),
original_taxa_count AS (
    SELECT COUNT(*) AS taxa_count FROM transformed_data WHERE MTV IS NOT NULL
)
SELECT mtv_index, taxa_count FROM mtv_result, original_taxa_count
"""


def urci_typ(mnm, strahler, umori):
    """Urci typ toku pro hodnoceni makrofyt.

    Returns:
        (klic_typu, poznamka) - klic_typu je None, pokud tok nelze zaradit
    """
    # hodnoty mohou z databaze prijit jako retezec, viz to_float
    mnm = to_float(mnm)
    strahler = to_float(strahler)
    if mnm is None or strahler is None:
        return None, "Chybi nadmorska vyska nebo Strahleruv rad"

    if 1 <= strahler <= 3:
        return None, ("Nehodnoceno: tok 1.-3. Strahlerova řádu, "
                      "makrofyta se v něm podle metodiky nehodnotí")

    if mnm > 500 and 4 <= strahler <= 7:
        return "1", None

    if mnm < 200 and 4 <= strahler <= 9:
        if umori in (1, 2):
            return "2A", None
        if umori == 3:
            return "2B", None
        return "2", None

    if 200 <= mnm <= 500 and 7 <= strahler <= 9:
        return "3", None

    if 200 <= mnm <= 500 and 4 <= strahler <= 6:
        if umori in (1, 2):
            return "4A", None
        if umori == 3:
            return "4B", None
        return "4", None

    return None, "Vzorek neni zarazen do zadneho typu toku"


def _klasifikuj_mf(eqr, definice, potencial):
    """Zaradi EQR do tridy podle hranic daneho typu toku (ostra nerovnost)."""
    if eqr is None:
        return None
    for mez, trida in definice["potencial" if potencial else "stav"]:
        if eqr > mez:
            return trida
    return "Z"


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte MF hodnoceni pro tok."""
    try:
        query = QSqlQuery(db_connection)
        query.prepare(
            """
            SELECT l.STRAHLER, l.MNM, l.UMORI
            FROM samples s
            JOIN loc l ON s.LOC_ID = l.KOD
            WHERE s.SAMPLE_ID = ?
            """
        )
        query.addBindValue(sample_id)
        if not query.exec() or not query.next():
            return {"MF_POZN": "Chybi abioticke parametry lokality"}

        strahler = query.value(0)
        mnm = query.value(1)
        umori = query.value(2)

        # Typ toku rozhoduje o tom, zda se uplatni agregace i bez
        # stenovalentnich druhu, takze se musi urcit pred vypoctem MTV.
        typ, duvod = urci_typ(mnm, strahler, umori)
        agreguj = _agregovat_vzdy(typ)

        query = QSqlQuery(db_connection)
        query.prepare(MTV_SQL)
        query.addBindValue(sample_id)
        query.addBindValue(agreguj)
        query.addBindValue(agreguj)
        if not query.exec() or not query.next():
            return {"MF_POZN": "Chybi taxonomicka data nebo taxalist_mf"}

        mtv = to_float(query.value(0))
        pocet_taxonu = to_float(query.value(1))

        if mtv is None:
            return {"MF_POZN": (
                "Nehodnoceno: vzorek neobsahuje žádný skórující taxon "
                "makrofyt (druh s hodnotou MTV v taxalistu)"
            )}

        pozn = f"Pocet taxonu s MTV hodnotou: {pocet_taxonu}"

        if typ is None:
            # U nehodnoceneho vzorku ma byt v poznamce jen duvod - pocet
            # taxonu by ho jen zaclonil.
            pozn = duvod
            eqr, trida = None, None
        else:
            definice = TYPY[typ]
            eqr = round((mtv - 1) / definice["delitel"], 3)
            trida = _klasifikuj_mf(eqr, definice, potencial)
            pozn += f"; typ {typ} ({definice['popis']})"

        smaz_vysledky(db_connection, sample_id, ["MF_01", "MF_CELKEM"])
        zapis_vysledky(
            db_connection,
            sample_id,
            [
                {"metric": "MF_01", "val": mtv, "eqr": eqr,
                 "class": None, "pozn": pozn},
                {"metric": "MF_CELKEM", "val": eqr, "eqr": eqr,
                 "class": trida, "pozn": pozn},
            ],
        )

        return {
            "MF_01": mtv,
            "MF_01_EQR": eqr,
            "MF_CELKEM": eqr,
            "MF_CLASS": trida,
            "MF_POZN": pozn,
            "MF_TYP_HODNOCENI": "POTENCIAL" if potencial else "STAV",
        }

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"MF_POZN": f"Kriticka chyba: {e}"}
