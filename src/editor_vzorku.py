"""
Okno pro upravu obsahu vzorku - taxonu a chemickych parametru.

Detail vzorku na zalozce Vzorky je jen ke cteni: stoji na
`QSqlQueryModel`, ktery zapisovat neumi. Tenhle dialog je doplnek -
nacte radky tabulky `data` pro jeden vzorek, necha je upravit a zmeny
zapise najednou.

Co jde upravit
--------------
    nazev taxonu    textove pole; nazev se pri ulozeni overi proti
                    taxalistu dane slozky a neznamy se oznaci
    hodnota         abundance, pokryvnost, biomasa - podle slozky
    sit, zona       doplnkove udaje u ryb

Chemicke parametry jsou v teze tabulce, jen misto jmena taxonu maji kod
parametru. Rozliseni je na ciselniku `taxalist_chem`, takze se v seznamu
ukazuji s popisem a jejich nazev se proti taxalistu neoveruje.

Zapis probiha v transakci: bud projde vse, nebo nic. Radek se maze
tlacitkem, novy se prida prazdny na konec.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtSql import QSqlQuery
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableView, QVBoxLayout,
)

#: Sloupce tabulky `data`, ktere jdou v dialogu menit.
#: (popisek, sloupec v databazi, sirka v px)
SLOUPCE = (
    ("Taxon / parametr", "name", 320),
    ("Hodnota", "val", 90),
    ("Biomasa", "BIOMASA", 90),
    ("Pokryvnost", "POKRYVNOST", 90),
    ("Síť", "SIT", 70),
    ("Zóna", "ZONA", 70),
)

#: Podbarveni radku, jehoz taxon neni v taxonomickem seznamu.
#: Stejna barva jako v prehledu vzorku, at to znamena totez.
HEX_NEZNAMY = "#ffe0b2"


class EditorVzorku(QDialog):
    """Dialog pro úpravu řádků jednoho vzorku."""

    def __init__(self, db, sample_id, taxalist=None, parent=None):
        """Args:
            db: otevřené QSqlDatabase
            sample_id: kód vzorku
            taxalist: tabulka pro ověření názvů; None = neověřovat
        """
        super().__init__(parent)
        self.db = db
        self.sample_id = sample_id
        self.taxalist = taxalist
        self._smazane = []

        self.setWindowTitle(f"Úprava vzorku {sample_id}")
        self.resize(900, 600)

        self.model = QStandardItemModel(0, len(SLOUPCE))
        self.model.setHorizontalHeaderLabels([p for p, _, _ in SLOUPCE])

        self.pohled = QTableView()
        self.pohled.setModel(self.model)
        self.pohled.verticalHeader().setVisible(False)
        self.pohled.setAlternatingRowColors(True)
        self.pohled.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        hlavicka = self.pohled.horizontalHeader()
        for i, (_, _, sirka) in enumerate(SLOUPCE):
            hlavicka.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.pohled.setColumnWidth(i, sirka)
        hlavicka.setStretchLastSection(True)

        pridat = QPushButton("Přidat řádek")
        pridat.clicked.connect(self.pridej_radek)
        smazat = QPushButton("Smazat řádek")
        smazat.clicked.connect(self.smaz_radek)

        tlacitka_radku = QHBoxLayout()
        tlacitka_radku.addWidget(pridat)
        tlacitka_radku.addWidget(smazat)
        tlacitka_radku.addStretch(1)

        self.hlaska = QLabel()
        self.hlaska.setWordWrap(True)
        self.hlaska.setStyleSheet("color: #7a4c00;")

        tlacitka = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        tlacitka.accepted.connect(self.uloz)
        tlacitka.rejected.connect(self.reject)

        rozvrzeni = QVBoxLayout(self)
        rozvrzeni.addWidget(QLabel(
            "Prázdný název řádek při uložení smaže. Oranžově jsou taxony, "
            "které nejsou v taxonomickém seznamu."))
        rozvrzeni.addWidget(self.pohled, 1)
        rozvrzeni.addLayout(tlacitka_radku)
        rozvrzeni.addWidget(self.hlaska)
        rozvrzeni.addWidget(tlacitka)

        self.nacti()

    # -- nacteni -------------------------------------------------------

    def _zname_taxony(self):
        """Nazvy z taxalistu dane slozky; prazdna mnozina = neoverovat."""
        if not self.taxalist:
            return set()
        dotaz = QSqlQuery(self.db)
        znama = set()
        if dotaz.exec(f"SELECT NAME FROM {self.taxalist}"):
            while dotaz.next():
                znama.add(dotaz.value(0))
        return znama

    def nacti(self):
        """Načte řádky vzorku do tabulky."""
        self.model.removeRows(0, self.model.rowCount())
        self._smazane = []
        znama = self._zname_taxony()

        sloupce = ", ".join(s for _, s, _ in SLOUPCE)
        dotaz = QSqlQuery(self.db)
        dotaz.prepare(f"SELECT ID, {sloupce} FROM data WHERE sample = ? "
                      f"ORDER BY name")
        dotaz.addBindValue(self.sample_id)
        if not dotaz.exec():
            QMessageBox.critical(
                self, "Chyba",
                f"Data vzorku nelze načíst:\n{dotaz.lastError().text()}")
            return

        while dotaz.next():
            polozky = []
            for i, _ in enumerate(SLOUPCE):
                hodnota = dotaz.value(i + 1)
                polozka = QStandardItem(
                    "" if hodnota is None else str(hodnota))
                polozky.append(polozka)
            # ID řádku si nese první buňka, ať se ví, co se aktualizuje.
            polozky[0].setData(dotaz.value(0), Qt.ItemDataRole.UserRole)
            self.model.appendRow(polozky)

        self._obarvi(znama)
        self.hlaska.setText("")

    def _obarvi(self, znama):
        """Podbarví řádky s taxonem mimo taxonomický seznam."""
        if not znama:
            return
        barva = QColor(HEX_NEZNAMY)
        neznamych = 0
        for radek in range(self.model.rowCount()):
            jmeno = self.model.item(radek, 0).text().strip()
            if jmeno and jmeno not in znama:
                neznamych += 1
                for sloupec in range(self.model.columnCount()):
                    self.model.item(radek, sloupec).setBackground(barva)
        if neznamych:
            self.hlaska.setText(
                f"{neznamych} taxonů není v seznamu — do metrik nevstoupí.")

    # -- upravy --------------------------------------------------------

    def pridej_radek(self):
        polozky = [QStandardItem("") for _ in SLOUPCE]
        self.model.appendRow(polozky)
        self.pohled.scrollToBottom()

    def smaz_radek(self):
        radky = sorted(
            {i.row() for i in self.pohled.selectionModel().selectedIndexes()},
            reverse=True)
        for radek in radky:
            polozka = self.model.item(radek, 0)
            id_radku = polozka.data(Qt.ItemDataRole.UserRole)
            if id_radku is not None:
                self._smazane.append(id_radku)
            self.model.removeRow(radek)

    # -- ulozeni -------------------------------------------------------

    def _radky_k_zapisu(self):
        """Posbírá obsah tabulky.

        Returns:
            (aktualizace, vlozeni, smazani) - seznamy připravené k zápisu
        """
        aktualizace, vlozeni, smazani = [], [], list(self._smazane)
        for radek in range(self.model.rowCount()):
            hodnoty = {}
            for i, (_, sloupec, _) in enumerate(SLOUPCE):
                text = self.model.item(radek, i).text().strip()
                hodnoty[sloupec] = text if text else None
            id_radku = self.model.item(radek, 0).data(Qt.ItemDataRole.UserRole)

            if not hodnoty["name"]:
                # Prázdný název = řádek k odstranění. Nový prázdný řádek
                # se prostě zahodí.
                if id_radku is not None:
                    smazani.append(id_radku)
                continue
            if id_radku is None:
                vlozeni.append(hodnoty)
            else:
                aktualizace.append((id_radku, hodnoty))
        return aktualizace, vlozeni, smazani

    def uloz(self):
        """Zapíše změny v jedné transakci."""
        aktualizace, vlozeni, smazani = self._radky_k_zapisu()

        self.db.transaction()
        try:
            for id_radku in smazani:
                self._proved("DELETE FROM data WHERE ID = ?", [id_radku])

            for id_radku, hodnoty in aktualizace:
                sety = ", ".join(f"[{s}] = ?" for s in hodnoty)
                self._proved(f"UPDATE data SET {sety} WHERE ID = ?",
                             list(hodnoty.values()) + [id_radku])

            for hodnoty in vlozeni:
                sloupce = list(hodnoty) + ["sample"]
                otazniky = ", ".join("?" for _ in sloupce)
                self._proved(
                    f"INSERT INTO data ({', '.join(f'[{s}]' for s in sloupce)})"
                    f" VALUES ({otazniky})",
                    list(hodnoty.values()) + [self.sample_id])
        except RuntimeError as e:
            self.db.rollback()
            QMessageBox.critical(self, "Chyba", f"Uložení se nezdařilo:\n{e}")
            return

        if not self.db.commit():
            QMessageBox.critical(
                self, "Chyba",
                f"Změny nelze potvrdit:\n{self.db.lastError().text()}")
            return

        QMessageBox.information(
            self, "Uloženo",
            f"Upraveno {len(aktualizace)}, přidáno {len(vlozeni)}, "
            f"smazáno {len(smazani)} řádků.\n\n"
            "Výsledky vzorku je potřeba přepočítat.")
        self.accept()

    def _proved(self, sql, parametry):
        """Provede dotaz, nebo vyvolá RuntimeError."""
        dotaz = QSqlQuery(self.db)
        dotaz.prepare(sql)
        for p in parametry:
            dotaz.addBindValue(p)
        if not dotaz.exec():
            raise RuntimeError(dotaz.lastError().text() or "dotaz selhal")
