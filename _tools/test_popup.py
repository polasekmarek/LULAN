"""
Zjisti, zda se v tomto prostredi vubec otevírají vyskakovací nabidky.

V LULANu prestaly fungovat rozbalovaci seznamy (`QComboBox`) - po
kliknuti se nabidka neotevre. Nahradili jsme je prepínaci, ale to je
obejiti priciny, ne jeji odstraneni. Tenhle skript ji pomuze zuzit.

Okno obsahuje pet ovladacich prvku, ktere kazdy otevira nabidku jinym
zpusobem. Podle toho, ktere z nich funguji, se da rict, kde je problem:

    vsechno funguje            chyba je v LULANu, ne v prostredi
    nefunguje nic              chyba je v Qt nebo v grafickem prostredi
    jen combo nefunguje        problem je specificky pro QComboBox
    combo i menu nefunguji     problem je s vyskakovacimi okny obecne
    nejde jen seznam v bunce   problem je v editaci tabulky, ne v popupu

Skript zaroven vypise verzi Qt a pouzity platform plugin - to byva
u takovych potizi rozhodujici udaj.

Pouziti:
    python _tools/test_popup.py
"""

import sys

from PyQt6.QtCore import QT_VERSION_STR, QLibraryInfo, QTimer
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QPushButton, QRadioButton, QStyledItemDelegate, QTableView, QVBoxLayout,
    QWidget,
)


class DelegatSeznamu(QStyledItemDelegate):
    """Editor bunky = rozbalovaci seznam, ktery se hned otevre.

    Stejny postup jako `CiselnikovyDelegate` v LULANu.
    """

    MOZNOSTI = ("R — řeka", "J — jezero")

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt API
        combo = QComboBox(parent)
        combo.addItems(self.MOZNOSTI)
        QTimer.singleShot(0, combo.showPopup)
        return combo


def prostredi():
    """Radky s udaji o prostredi, ktere se hodi pri hlaseni chyby."""
    from PyQt6.QtCore import PYQT_VERSION_STR

    app = QApplication.instance()
    return [
        f"Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}",
        f"platform plugin: {app.platformName()}",
        f"styl: {app.style().objectName()}",
        f"Python {sys.version.split()[0]} na {sys.platform}",
        f"pluginy: {QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)}",
    ]


class Okno(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test vyskakovacích nabídek")
        self.resize(620, 380)

        rozvrzeni = QVBoxLayout()
        rozvrzeni.addWidget(QLabel(
            "<b>Vyzkoušejte postupně všech pět prvků.</b><br>"
            "U každého si poznamenejte, jestli se nabídka otevře."))

        # 1. QComboBox - to, co v LULANu nefunguje
        rozvrzeni.addWidget(QLabel("<b>1.</b> Rozbalovací seznam (QComboBox):"))
        combo = QComboBox()
        combo.addItems(["první", "druhá", "třetí", "čtvrtá"])
        combo.currentTextChanged.connect(
            lambda t: self.statusBar().showMessage(f"combo: vybráno {t}"))
        rozvrzeni.addWidget(combo)

        # 2. Editovatelny combo - jina cesta k tomu samemu popupu
        rozvrzeni.addWidget(QLabel(
            "<b>2.</b> Rozbalovací seznam s možností psát:"))
        combo2 = QComboBox()
        combo2.setEditable(True)
        combo2.addItems(["alfa", "beta", "gama"])
        rozvrzeni.addWidget(combo2)

        # 3. Nabidka pod tlacitkem - popup, ale jiny nez u comba
        rozvrzeni.addWidget(QLabel("<b>3.</b> Nabídka pod tlačítkem (QMenu):"))
        tlacitko = QPushButton("Rozbalit nabídku")
        nabidka = QMenu(tlacitko)
        for text in ("položka A", "položka B", "položka C"):
            nabidka.addAction(text).triggered.connect(
                lambda _=False, t=text:
                self.statusBar().showMessage(f"menu: {t}"))
        tlacitko.setMenu(nabidka)
        rozvrzeni.addWidget(tlacitko)

        # 4. Prepínace - nahrada pouzita v LULANu, popup nepotrebuje
        rozvrzeni.addWidget(QLabel(
            "<b>4.</b> Přepínače (náhrada použitá v LULANu):"))
        rada = QHBoxLayout()
        for text in ("MZB", "FB", "MF", "RYBY"):
            prepinac = QRadioButton(text)
            prepinac.toggled.connect(
                lambda zapnuto, t=text: zapnuto and
                self.statusBar().showMessage(f"přepínač: {t}"))
            rada.addWidget(prepinac)
        rada.addStretch()
        obal = QWidget()
        obal.setLayout(rada)
        rozvrzeni.addWidget(obal)

        # 5. Rozbalovaci seznam primo v bunce tabulky - jako na zalozce
        #    Utvary. Otevira se jinak nez samostatny combo, proto zvlast.
        rozvrzeni.addWidget(QLabel(
            "<b>5.</b> Seznam v buňce tabulky "
            "(klikněte na buňku ve sloupci „kategorie“):"))
        tabulka = QTableView()
        model = QStandardItemModel(3, 2)
        model.setHorizontalHeaderLabels(["útvar", "kategorie"])
        for radek, (kod, kat) in enumerate(
                [("BER_0060", "R"), ("DYJ_0540", "R"), ("OHL_0970", "J")]):
            model.setItem(radek, 0, QStandardItem(kod))
            model.setItem(radek, 1, QStandardItem(kat))
        tabulka.setModel(model)
        tabulka.setItemDelegateForColumn(1, DelegatSeznamu(tabulka))
        tabulka.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.SelectedClicked)
        tabulka.setMaximumHeight(120)
        rozvrzeni.addWidget(tabulka)

        rozvrzeni.addStretch()
        rozvrzeni.addWidget(QLabel(
            "<span style='color:#555'>" + "<br>".join(prostredi())
            + "</span>"))

        stred = QWidget()
        stred.setLayout(rozvrzeni)
        self.setCentralWidget(stred)
        self.statusBar().showMessage("Připraveno")


def main():
    app = QApplication(sys.argv)
    print("\n".join(prostredi()))
    okno = Okno()
    okno.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
