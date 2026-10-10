"""
Radek filtrovacich poli, ktery lícuje se sloupci tabulky pod nim.

Puvodne mel kazdy prehled vlastni radek `QLineEdit`u s natvrdo
zapsanymi sirkami. Jakmile si uzivatel sloupec pretahl, prestalo to
sedet - a stacilo i jine pismo nebo jina delka dat, aby se pole
rozesla se zahlavim hned po spusteni.

Tenhle widget si sirky bere primo od tabulky a drzi je synchronni:
nasloucha zmenam sirky sloupce, jejich presunum, skryti i vodorovnemu
posunu. Pole nad skrytym sloupcem se skryje taky.

Pouziti:

    self.filtry = RadekFiltru(pohled, [1, 2, 3, 4], ["KOD", "TOK", ...])
    self.filtry.zmenen.connect(self.pouzij_filtr)
    ...
    self.filtry.text(0)        # obsah prvniho pole
    self.filtry.vycisti()
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QPoint, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLineEdit, QWidget

from cesty import v_korenu

#: Ikona trychtyre v poli filtru. Vedle zakladni velikosti se pridava
#: i dvojnasobna pro obrazovky s vysokym rozlisenim - jinak by ikona
#: byla rozmazana.
#:
#: Obe se vyrabeji z `img/filter_icon.svg`: SVG se vykresli na 256 px
#: a teprve ta bitmapa se zmensi. Zmensovat tenky obrys rovnou na 16 px
#: nejde - z linky siroke par pixelu nezbyde nic nez seda plocha.
IKONA_FILTRU = os.path.join("img", "filtr_ikona.png")
IKONA_FILTRU_2X = os.path.join("img", "filtr_ikona@2x.png")

#: Vzhled pole. Vyska se dopocitava podle vysky radku tabulky, aby
#: filtr vypadal jako dalsi radek prehledu, ne jako cizi prvek.
STYL_POLE = (
    "QLineEdit {"
    " padding: 0px 2px; margin: 0px;"
    " border: 1px solid #c8c8c8;"
    " background: #fbfbfb;"
    "}"
    "QLineEdit:focus { border: 1px solid #2b6cb0; background: #ffffff; }"
)


def ikona_filtru():
    """Ikona trychtýře, nebo prázdná ikona, když soubor chybí."""
    zaklad = v_korenu(IKONA_FILTRU)
    if not os.path.exists(zaklad):
        return QIcon()
    ikona = QIcon(zaklad)
    dvojnasobna = v_korenu(IKONA_FILTRU_2X)
    if os.path.exists(dvojnasobna):
        ikona.addFile(dvojnasobna)
    return ikona


class RadekFiltru(QWidget):
    """Řada filtrovacích polí zarovnaná se sloupci tabulky."""

    #: Někdo do některého pole psal.
    zmenen = pyqtSignal()

    def __init__(self, pohled, sloupce, popisky=None, parent=None):
        """Args:
            pohled: QTableView, se kterým se má řádek srovnávat
            sloupce: indexy sloupců, ke kterým pole patří
            popisky: nápovědné texty v polích; None = bez nich
        """
        super().__init__(parent)
        self.pohled = pohled
        self.sloupce = list(sloupce)
        self.pole = []

        # Bez rozvržení: pole se umisťují na přesné souřadnice sloupců.
        # Pružné rozvržení tu selhávalo ve chvíli, kdy se tabulka nevešla
        # do okna. Sloupce pak přetečou přes okraj a rolují se stranou,
        # jenže rozvržení o rolování neví a pole dál poctivě vyplňovala
        # celou šířku panelu - záhlaví a filtry se rozešly.
        ikona = ikona_filtru()
        for i, _ in enumerate(self.sloupce):
            editace = QLineEdit(self)
            editace.setStyleSheet(STYL_POLE)
            editace.setClearButtonEnabled(True)
            if popisky and i < len(popisky):
                editace.setPlaceholderText(str(popisky[i]))
            if not ikona.isNull():
                editace.addAction(
                    ikona, QLineEdit.ActionPosition.LeadingPosition)
            editace.textChanged.connect(self.zmenen)
            self.pole.append(editace)

        hlavicka = pohled.horizontalHeader()
        hlavicka.sectionResized.connect(self._srovnej)
        hlavicka.sectionMoved.connect(self._srovnej)
        pohled.horizontalScrollBar().valueChanged.connect(self._srovnej)

        # Poslední sloupec má `setStretchLastSection(True)`, takže svou
        # konečnou šířku dostane až ve chvíli, kdy tabulka zná tu svou -
        # tedy při prvním rozložení. Do té doby vrací `sectionSize()`
        # předběžnou, menší hodnotu a poslední pole filtru by zůstalo
        # kratší, dokud se záložka nepřekreslí. Sledování změny velikosti
        # tabulky to řeší: jakmile se rozloží, řádek se srovná znovu.
        pohled.viewport().installEventFilter(self)
        pohled.installEventFilter(self)

        # Při sestavení okna ještě tabulka nezná svou šířku, takže se
        # srovnává až po prvním kole smyčky událostí.
        QTimer.singleShot(0, self._srovnej)

    def eventFilter(self, sledovany, udalost):  # noqa: N802 - Qt API
        """Po každé změně velikosti tabulky srovná šířky polí."""
        if udalost.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            # Až po vyřízení události - v jejím průběhu má tabulka ještě
            # starou šířku a poslední sloupec by se přepočítal špatně.
            QTimer.singleShot(0, self._srovnej)
        return super().eventFilter(sledovany, udalost)

    # -- obsah ---------------------------------------------------------

    def text(self, poradi):
        """Obsah pole na daném pořadí."""
        return self.pole[poradi].text().strip() if poradi < len(self.pole) else ""

    def texty(self):
        """Obsah všech polí jako seznam."""
        return [p.text().strip() for p in self.pole]

    def vycisti(self):
        """Vyprázdní všechna pole bez vyvolání signálu za každé zvlášť."""
        for p in self.pole:
            p.blockSignals(True)
            p.clear()
            p.blockSignals(False)
        self.zmenen.emit()

    def __len__(self):
        return len(self.pole)

    def __iter__(self):
        return iter(self.pole)

    # -- zarovnani -----------------------------------------------------

    def vyska_radku(self):
        """Výška běžného řádku tabulky."""
        svisla = self.pohled.verticalHeader()
        vyska = svisla.defaultSectionSize()
        if self.pohled.model() is not None and self.pohled.model().rowCount():
            vyska = svisla.sectionSize(0) or vyska
        return max(int(vyska), 18)

    def _posun_plochy(self):
        """Vzdálenost levého okraje tabulky od začátku jejích sloupců.

        Zahrnuje rám tabulky i svislé záhlaví, když je zobrazené.
        `columnViewportPosition()` totiž počítá až od nich.
        """
        return self.pohled.viewport().mapTo(self.pohled, QPoint(0, 0)).x()

    def _srovnej(self, *_):
        """Umístí pole přesně nad sloupce tabulky.

        Souřadnice se berou z `columnViewportPosition()`, takže samy
        počítají s odrolováním stranou. Pole se pak ořízne na viditelnou
        plochu tabulky - sloupec zrolovaný za okraj tedy ani ve filtrech
        nezabírá místo a řádek nikdy nepřeteče.
        """
        pohled = self.pohled
        hlavicka = pohled.horizontalHeader()
        vyska = self.vyska_radku()
        zacatek = self._posun_plochy()
        konec = zacatek + pohled.viewport().width()

        for editace, sloupec in zip(self.pole, self.sloupce):
            if pohled.isColumnHidden(sloupec):
                editace.setVisible(False)
                continue

            levy = zacatek + pohled.columnViewportPosition(sloupec)
            pravy = levy + hlavicka.sectionSize(sloupec)

            # Oříznutí na viditelnou plochu tabulky.
            levy = max(levy, zacatek)
            pravy = min(pravy, konec)

            if pravy - levy < 2:
                # Sloupec je odrolovaný pryč, nebo z něj zbyl proužek.
                editace.setVisible(False)
                continue

            editace.setVisible(True)
            editace.setGeometry(int(levy), 0, int(pravy - levy), vyska)

        self.setFixedHeight(vyska)

    def sizeHint(self):  # noqa: N802 - Qt API
        return QSize(self.pohled.width(), self.vyska_radku())

    def resizeEvent(self, udalost):  # noqa: N802 - Qt API
        super().resizeEvent(udalost)
        self._srovnej()

    def showEvent(self, udalost):  # noqa: N802 - Qt API
        super().showEvent(udalost)
        self._srovnej()
