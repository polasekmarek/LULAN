"""
Orchestrace vypoctu indexu: jednotlivy vzorek, davka na pozadi, agregace.

Jednotlive hodnotici moduly si vysledky do tabulky `results` zapisuji samy;
tento modul je pouze spousti, hlida prubeh a nasledne agreguje vysledky do
rocnich prumeru po vodnich utvarech (tabulka `results_year`).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlQuery
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

from .registry import (
    duvod_nehodnoceni,
    vlastnosti_utvaru,
    vyber_funkci_pro_vzorek,
)

#: Slozky, jejichz multimetriky se agreguji do rocnich vysledku.
SLOZKY = ["MZB", "FB", "FP", "MF", "RYBY"]

#: Hranice trid pouzite v tabulce results_year (jednopismenne kody).
HRANICE_ROCNI = [(0.8, "VD"), (0.6, "D"), (0.4, "S"), (0.2, "P"), (0.0, "Z")]

#: Kod tridy pro vzorek, ktery se podle metodiky nehodnoti.
#:
#: Neni to spatny stav - je to "nehodnoceno". Drive takovy vzorek zmizel
#: z tabulky `results` uplne a v aplikaci vypadal, jako by se vypocet
#: nepovedl. Ted se zapise radek s prazdnym EQR a duvodem v poznamce.
#:
#: Rocni agregace takovy radek preskoci: vybira jen `VAL_EQR IS NOT NULL`
#: a tridu doplnuje jen tam, kde EQR vyslo.
TRIDA_NEHODNOCENO = "NA"


# ---------------------------------------------------------------------------
# Vypocet jednoho vzorku
# ---------------------------------------------------------------------------

def zapis_nehodnoceno(db_connection, sample_id, slozka, duvod):
    """Zapise do `results` radek "nehodnoceno" s duvodem.

    Vzorky, ktere metodika nehodnoti (tok nizkeho radu u ryb a makrofyt,
    Strahler pod 7 u fytoplanktonu, velke reky mimo letni kampan), nejsou
    chyba vypoctu. Drive po nich v tabulce nezustala zadna stopa a v
    aplikaci to vypadalo, jako by se vypocet nepovedl.
    """
    from .common import smaz_vysledky, zapis_vysledky

    kod = f"{slozka}_CELKEM"
    smaz_vysledky(db_connection, sample_id, [kod])
    zapis_vysledky(db_connection, sample_id, [{
        "metric": kod,
        "val": None,
        "eqr": None,
        "class": TRIDA_NEHODNOCENO,
        "pozn": duvod or "Nehodnoceno",
    }])


def calc_indexes(sample_id, db_connection):
    """Spocita indexy pro jeden vzorek.

    Returns:
        dict s vysledky, nebo None pokud vzorek neexistuje
    """
    try:
        query = QSqlQuery(db_connection)
        query.prepare("SELECT TYP FROM samples WHERE SAMPLE_ID = ?")
        query.addBindValue(sample_id)
        if not query.exec() or not query.next():
            print(f"[runner] Vzorek {sample_id} nenalezen")
            return None

        slozka = query.value(0)
        utvar = vlastnosti_utvaru(sample_id, db_connection)
        funkce, potencial = vyber_funkci_pro_vzorek(
            slozka, utvar, sample_id, db_connection
        )

        if funkce is None:
            duvod = duvod_nehodnoceni(slozka, utvar)
            zapis_nehodnoceno(db_connection, sample_id, slozka, duvod)
            return {
                f"{slozka}_CELKEM": None,
                f"{slozka}_CLASS": TRIDA_NEHODNOCENO,
                f"{slozka}_POZN": duvod,
            }

        vysledek = funkce(sample_id, db_connection, potencial=potencial)
        if vysledek is None:
            return {f"{slozka}_POZN": "Vypocet vratil None"}

        # Metodika vzorek nehodnoti (nebo pro nej neni implementovana):
        # zapsat "nehodnoceno" s duvodem misto toho, aby po vzorku
        # v tabulce nezustala zadna stopa.
        if vysledek.get(f"{slozka}_CELKEM") is None:
            zapis_nehodnoceno(db_connection, sample_id, slozka,
                              vysledek.get(f"{slozka}_POZN"))
            vysledek[f"{slozka}_CLASS"] = TRIDA_NEHODNOCENO

        vysledek.setdefault(
            f"{slozka}_TYP_HODNOCENI", "POTENCIAL" if potencial else "STAV"
        )
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        print(f"[runner] Kriticka chyba u vzorku {sample_id}: {e}")
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# Davkovy vypocet
# ---------------------------------------------------------------------------
#
# Vypocet bezi v hlavnim (GUI) vlakne nad TYMZ spojenim, ktere pouziva
# aplikace. Drivejsi verze pro nej mela QThread; obe varianty s vlaknem ale
# narazi na to, jak funguje Qt a SQLite:
#
#   * predat vlaknu spojeni z GUI Qt zakazuje - QSqlDatabase smi pouzivat
#     jen to vlakno, ktere ho vytvorilo, jinak kazdy dotaz selze hlaskou
#     "requested database does not belong to the calling thread";
#   * otevrit ve vlakne spojeni vlastni znamena dva zapisovatele nad jednim
#     souborem SQLite. Zapisy se pak navzajem blokuji a cely vypocet se
#     protahne z desitek sekund na hodiny ("database is locked").
#
# Cela davka trva 1639 vzorku asi 25 s, takze vlakno prakticky nic nepridava.
# Odezvu dialogu drzi QProgressDialog.setValue(), ktere u modalniho dialogu
# samo zpracuje frontu udalosti, takze tlacitko Zrusit funguje.


def run_index_calculation(parent_widget, db_connection):
    """Spusti vypocet indexu vsech vzorku s dialogem prubehu."""
    query = QSqlQuery(db_connection)
    query.exec(
        "SELECT SAMPLE_ID FROM samples "
        "WHERE SAMPLE_ID IS NOT NULL AND SAMPLE_ID != ''"
    )

    sample_ids = []
    while query.next():
        if query.value(0):
            sample_ids.append(query.value(0))

    if not sample_ids:
        QMessageBox.information(
            parent_widget, "Info", "Nebyly nalezeny žádné vzorky pro výpočet."
        )
        return False

    odpoved = QMessageBox.question(
        parent_widget,
        "Potvrzení výpočtu",
        f"Chcete spustit výpočet indexů pro {len(sample_ids)} vzorků?\n\n"
        "Existující výsledky budou přepsány.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if odpoved != QMessageBox.StandardButton.Yes:
        return False

    # upozornit na nezmigrovanou databázi dřív, než se spustí celý výpočet
    from .registry import zkontroluj_schema

    v_poradku, zprava = zkontroluj_schema(db_connection)
    if not v_poradku:
        pokracovat = QMessageBox.warning(
            parent_widget,
            "Zastaralé schéma databáze",
            zprava + "\n\nChcete přesto pokračovat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if pokracovat != QMessageBox.StandardButton.Yes:
            return False

    # upozornit na nesoulad mezi vymezením velkých řek a sloupcem BROD
    from .velke_reky_utvary import popis_nesouladu, zkontroluj_soulad

    nesoulad = popis_nesouladu(zkontroluj_soulad(db_connection))
    if nesoulad:
        pokracovat = QMessageBox.warning(
            parent_widget,
            "Nesoulad ve vymezení velkých řek",
            "Seznam útvarů v metodice velkých nebroditelných řek nesouhlasí "
            "se sloupcem BROD v databázi.\n\n" + nesoulad +
            "\n\nO použité metodice rozhoduje seznam z metodiky, ne sloupec "
            "BROD. Chcete pokračovat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if pokracovat != QMessageBox.StandardButton.Yes:
            return False

    # upozornit na změněné trait hodnoty v taxonomických seznamech
    from .common import (
        ZALOHY_TAXALISTU,
        popis_zmen_traitu,
        zkontroluj_traity,
    )

    zmeny = []
    for tabulka in ZALOHY_TAXALISTU:
        zmeny += zkontroluj_traity(db_connection, tabulka)

    popis = popis_zmen_traitu(zmeny)
    if popis:
        pokracovat = QMessageBox.warning(
            parent_widget,
            "Změněné hodnoty v taxonomickém seznamu",
            popis +
            "\n\nVýpočet takovou změnu nijak neohlásí — vzorec zůstává "
            "správný, jen dostane jiná vstupní data. Zkontrolujte, zda jsou "
            "hodnoty správné.\n\nChcete pokračovat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if pokracovat != QMessageBox.StandardButton.Yes:
            return False

    dialog = QProgressDialog(
        "Výpočet indexů…", "Zrušit", 0, len(sample_ids), parent_widget
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.show()

    # Taxonomicke seznamy se behem davky nemeni - nacteme je jen jednou,
    # ale zacneme s cistou cache, aby se promitly zmeny provedene v GUI.
    from .common import vycisti_cache
    from .registry import vycisti_hlaseni

    vycisti_cache()
    vycisti_hlaseni()

    uspesnych = 0
    nehodnocenych = 0
    zpracovano = 0
    try:
        for i, sample_id in enumerate(sample_ids, 1):
            if dialog.wasCanceled():
                break
            # setValue u modalniho dialogu samo zpracuje frontu udalosti,
            # takze se dialog prekresluje a Zrusit reaguje.
            dialog.setValue(i)
            if i == 1 or i % 25 == 0:
                dialog.setLabelText(
                    f"Zpracovávám vzorek {sample_id} ({i}/{len(sample_ids)})")
            zpracovano = i

            try:
                vysledek = calc_indexes(sample_id, db_connection)
                if vysledek and any(
                    vysledek.get(f"{s}_CELKEM") is not None for s in SLOZKY
                ):
                    uspesnych += 1
                elif vysledek and any(
                    vysledek.get(f"{s}_CLASS") == TRIDA_NEHODNOCENO
                    for s in SLOZKY
                ):
                    # metodika vzorek nehodnoti - neni to chyba vypoctu
                    nehodnocenych += 1
            except Exception as e:  # noqa: BLE001
                import traceback

                print(f"[runner] Chyba u vzorku {sample_id}: {e}")
                traceback.print_exc()
    except Exception as e:  # noqa: BLE001
        dialog.close()
        QMessageBox.critical(
            parent_widget, "Chyba při výpočtu",
            f"Vyskytla se chyba během výpočtu indexů:\n{e}",
        )
        return False
    finally:
        dialog.close()

    if zpracovano < len(sample_ids):
        QMessageBox.information(
            parent_widget, "Výpočet přerušen",
            f"Výpočet jste zrušili po {zpracovano} z {len(sample_ids)} "
            f"vzorků.\nÚspěšně vyhodnoceno: {uspesnych}, "
            f"nehodnoceno podle metodiky: {nehodnocenych}\n\n"
            f"Už spočítané výsledky zůstávají uložené.",
        )
    else:
        agregace = aggregate_results_to_year(db_connection)
        zprava = (
            f"Výpočet dokončen.\n"
            f"Zpracováno vzorků: {zpracovano}\n"
            f"Úspěšně vyhodnoceno: {uspesnych}\n"
            f"Nehodnoceno podle metodiky: {nehodnocenych}"
        )
        neuspesnych = zpracovano - uspesnych - nehodnocenych
        if neuspesnych:
            zprava += f"\nNepodařilo se vyhodnotit: {neuspesnych}"
        if nehodnocenych:
            zprava += (
                "\n\nNehodnocené vzorky mají v přehledu výsledků třídu "
                f"\u201e{TRIDA_NEHODNOCENO}\u201c a v poznámce uvedený důvod "
                "(např. tok nízkého řádu, mimo hodnocenou kampaň)."
            )
        zprava += (
            f"\n\nAgregace: {agregace['message']}"
            if agregace["success"]
            else f"\n\nVarování: {agregace['message']}"
        )
        QMessageBox.information(parent_widget, "Výpočet dokončen", zprava)

    if hasattr(parent_widget, "apply_results_sample_filter"):
        parent_widget.apply_results_sample_filter()
    return True


# ---------------------------------------------------------------------------
# Agregace do rocnich vysledku
# ---------------------------------------------------------------------------

def _sql_klasifikace(sloupec_eqr):
    """Sestavi SQL CASE vyraz pro zarazeni EQR do tridy."""
    vetve = "\n".join(
        f"WHEN {sloupec_eqr} >= {mez} THEN '{trida}'"
        for mez, trida in HRANICE_ROCNI[:-1]
    )
    posledni = HRANICE_ROCNI[-1][1]
    return f"CASE\n{vetve}\nELSE '{posledni}'\nEND"


def aggregate_results_to_year(db_connection):
    """Agreguje multimetriky do rocnich prumeru po vodnich utvarech.

    Returns:
        dict {'success': bool, 'message': str, 'aggregated_count': int}
    """
    try:
        query = QSqlQuery(db_connection)

        query.exec(
            """
            CREATE TABLE IF NOT EXISTS results_year (
                UTVAR_POV TEXT, ROK INTEGER,
                MZB_EQR REAL, MZB_CLASS TEXT,
                FB_EQR REAL, FB_CLASS TEXT,
                FP_EQR REAL, FP_CLASS TEXT,
                MF_EQR REAL, MF_CLASS TEXT,
                RYBY_EQR REAL, RYBY_CLASS TEXT,
                FYZCHEM_CLASS TEXT
            )
            """
        )

        if not query.exec("DELETE FROM results_year"):
            return {
                "success": False,
                "message": f"Chyba při mazání results_year: "
                           f"{query.lastError().text()}",
                "aggregated_count": 0,
            }

        prumery = ",\n".join(
            f"AVG(CASE WHEN r.METRIC = '{s}_CELKEM' THEN r.VAL_EQR END) AS {s}_EQR"
            for s in SLOZKY
        )
        metriky = ", ".join(f"'{s}_CELKEM'" for s in SLOZKY)
        sloupce = ", ".join(f"{s}_EQR" for s in SLOZKY)

        if not query.exec(
            f"""
            INSERT INTO results_year (UTVAR_POV, ROK, {sloupce})
            SELECT
                l.VU AS UTVAR_POV,
                CAST(substr(s.DATE, -4) AS INTEGER) AS ROK,
                {prumery}
            FROM samples s
            LEFT JOIN loc l ON s.LOC_ID = l.KOD
            LEFT JOIN results r ON s.SAMPLE_ID = r.SAMPLE_ID
            WHERE l.VU IS NOT NULL
              AND s.DATE IS NOT NULL
              AND r.VAL_EQR IS NOT NULL
              AND r.METRIC IN ({metriky})
            GROUP BY l.VU, CAST(substr(s.DATE, -4) AS INTEGER)
            """
        ):
            return {
                "success": False,
                "message": f"Chyba při agregaci: {query.lastError().text()}",
                "aggregated_count": 0,
            }

        pocet = 0
        if query.exec("SELECT COUNT(*) FROM results_year") and query.next():
            pocet = query.value(0)

        for slozka in SLOZKY:
            query.exec(
                f"UPDATE results_year "
                f"SET {slozka}_CLASS = {_sql_klasifikace(f'{slozka}_EQR')} "
                f"WHERE {slozka}_EQR IS NOT NULL"
            )

        return {
            "success": True,
            "message": f"Agregováno {pocet} záznamů",
            "aggregated_count": pocet,
        }

    except Exception as e:  # noqa: BLE001
        return {"success": False, "message": f"Chyba: {e}", "aggregated_count": 0}


def get_yearly_results_summary(db_connection):
    """Nacte rocni vysledky pro zobrazeni v GUI.

    Returns:
        list dictu se sloupci tabulky results_year
    """
    sloupce = ["UTVAR_POV", "ROK"]
    for s in SLOZKY:
        sloupce += [f"{s}_EQR", f"{s}_CLASS"]
    sloupce.append("FYZCHEM_CLASS")

    query = QSqlQuery(db_connection)
    if not query.exec(
        f"SELECT {', '.join(sloupce)} FROM results_year ORDER BY UTVAR_POV, ROK DESC"
    ):
        print(f"Chyba při načítání ročních výsledků: {query.lastError().text()}")
        return []

    vysledky = []
    while query.next():
        vysledky.append(
            {
                sloupec: query.value(i)
                for i, sloupec in enumerate(sloupce)
            }
        )
    return vysledky
