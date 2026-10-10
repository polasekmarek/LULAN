import contextlib
import os
import shutil
import sqlite3
import stat
import sys
import datetime
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog,
    QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressDialog,
    QPushButton, QRadioButton, QSplitter, QTabWidget, QTableView,
    QTextBrowser, QVBoxLayout, QWidget,
)
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel, QSqlQueryModel, QSqlQuery
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QTimer, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor
from PyQt6.QtWidgets import QGroupBox, QStyledItemDelegate

from cesty import je_zabalena, v_korenu
import ciselnik_metrik
import ciselnik_traits
from radek_filtru import RadekFiltru
import ciselniky as ciselniky_modul
from mapa_lokalit import MapaLokalit, souradnice_lokality
from ciselniky import popisek_sloupce as ciselnik_popisek
import export_csv
import import_csv


#: Výchozí umístění databáze vůči kořeni projektu.
VYCHOZI_DB = "dtb/LULAN_dtb_001.db"

#: Jak dlouho čekat na zámek databáze [s].
#:
#: Uplatní se na každý příkaz zvlášť, a zápis běží v cyklu přes vzorky —
#: dlouhá lhůta by se proto nasčítala do minut zamrzlého okna a stejně
#: by skončila chybou. Pokrývá se tím jen krátké zdržení od jiného
#: procesu (synchronizační klient, antivirus), což je otázka zlomků
#: sekundy. Shodou okolností je to i výchozí hodnota modulu sqlite3.
CEKANI_NA_ZAMEK = 5.0


#: Ikona aplikace. ICO nese víc velikostí najednou (16 až 256 px), což
#: Windows potřebuje pro lištu i pro Průzkumníka; PNG je záloha pro
#: systémy, kde Qt formát ICO neumí.
IKONY = (
    os.path.join("img", "LULAN_icon.ico"),
    os.path.join("img", "LULAN_icon.png"),
    os.path.join("img", "LULAN_logo.jpg"),
)


def ikona_aplikace():
    """Vrátí ikonu aplikace, nebo prázdnou ikonu, když soubor chybí."""
    from PyQt6.QtGui import QIcon

    for relativni in IKONY:
        cesta = v_korenu(relativni)
        if os.path.exists(cesta):
            ikona = QIcon(cesta)
            if not ikona.isNull():
                return ikona
    return QIcon()


def cesta_k_databazi():
    """Sestaví cestu k databázi.

    Pořadí:
      1. proměnná prostředí LULAN_DB
      2. u nainstalované verze uživatelská kopie v datech aplikace;
         při prvním spuštění se tam přenese ta dodaná s programem
      3. soubor v kořeni projektu (vývojový běh ze zdrojáků)

    Nainstalovaný program leží v Program Files, kam běžný uživatel
    nesmí zapisovat — databáze tam tedy zůstat nemůže. Kopíruje se
    proto do adresáře pro data aplikací, který je zapisovatelný a při
    odinstalaci se nemaže, takže o data nikdo nepřijde.
    """
    z_prostredi = os.environ.get("LULAN_DB")
    if z_prostredi:
        return os.path.abspath(os.path.expanduser(z_prostredi))

    dodana = v_korenu(VYCHOZI_DB)
    if not je_zabalena():
        return dodana

    from uloziste import doporucene_umisteni

    uzivatelska = doporucene_umisteni(os.path.basename(VYCHOZI_DB))
    if os.path.exists(uzivatelska):
        return uzivatelska

    if not os.path.exists(dodana):
        raise FileNotFoundError(
            "Nenašel jsem databázi dodanou s programem.\n\n"
            f"Hledal jsem: {dodana}\n\n"
            "Program nejspíš není nainstalovaný celý — zkuste ho "
            "nainstalovat znovu.")

    os.makedirs(os.path.dirname(uzivatelska), exist_ok=True)
    shutil.copy2(dodana, uzivatelska)
    # Předloha leží v Program Files a může být jen ke čtení; kopie musí
    # být zapisovatelná, jinak SQLite neuloží ani jeden vzorek.
    os.chmod(uzivatelska, stat.S_IREAD | stat.S_IWRITE)
    return uzivatelska


#: Sloupce v prehledu taxonu: (popisek, mozne nazvy sloupce).
#: Autora vede MZB a FB jako `AUTOR`, MF a RYBY jako `AUTHOR` - proto
#: se u kazdeho sloupce zkousi vic nazvu a bere se prvni, ktery tabulka
#: ma. Driv se hledal jen `AUTOR` a u dvou taxalistu to plnilo konzoli
#: hlaskami "Column AUTOR not found".
SLOUPCE_PREHLEDU = (
    ("NAME", ("NAME",)),
    ("PARENT", ("PARENT",)),
    ("LEVEL", ("LEVEL",)),
    ("AUTOR", ("AUTOR", "AUTHOR")),
    ("SYN", ("SYN",)),
)

#: Vychozi sirky sloupcu v prehledu taxonu [px].
#: Jmeno taxonu musi pobrat i nejdelsi soubory druhu, napriklad
#: "Rhyacophila fasciata/loeffleri/obliterata/pascoei/vulgaris"
#: (56 znaku) - proto 420 px, coz je zhruba 60 znaku a nechava rezervu.
SIRKY_SLOUPCU_TAXONU = {
    "NAME": 420,
    "PARENT": 190,
    "LEVEL": 70,
    "AUTOR": 200,
    "SYN": 220,
}

#: Sloupce, ktere se v detailu taxonu neukazuji. Bud uz jsou videt
#: v radkovem prehledu vlevo, nebo jde o vnitrni identifikatory.
#: V detailu tak zbydou jen autekologicke charakteristiky.
SLOUPCE_MIMO_TRAITY = frozenset({
    "ID", "NAME", "PARENT", "PARENT_ID", "LEVEL",
    "AUTOR", "AUTHOR", "SYN", "SYN_ID", "DTCH",
})

#: Vyska zahlavi panelu. Levy panel ma v zahlavi popisek i zaskrtavatko,
#: pravy jen popisek - bez jednotne vysky by pravy panel zacinal vys
#: a tabulky vedle sebe by nelícovaly.
VYSKA_ZAHLAVI = 30


#: Nabidka taxonomickych seznamu na zalozce Taxony: (popisek, tabulka).
#: Uzivatel vybira podle slozky, ne podle nazvu tabulky v databazi.
#:
#: Zkratka slozky je v nazvu tabulky velkymi pismeny (`taxalist_MZB`).
#: Bezny SQL dotaz je na velikost pismen v nazvu tabulky necitlivy,
#: ale `QSqlTableModel.setTable()` si nazev drzi tak, jak ho dostane,
#: a pouziva ho pri sestavovani dalsich dotazu - proto se tu nazvy
#: uvadeji presne. Jistotu dava `nazev_tabulky()` nize.
TAXALISTY_NABIDKA = (
    ("MZB — makrozoobentos", "taxalist_MZB"),
    ("FB — fytobentos (i fytoplankton)", "taxalist_FB"),
    ("MF — makrofyta", "taxalist_MF"),
    ("RYBY — ryby", "taxalist_RYBY"),
)

#: Taxonomicky seznam, proti kteremu se overuji taxony dane slozky.
#: Fytoplankton sdili seznam s fytobentosem (viz `fp_reka.TAXALIST`).
TAXALIST_SLOZKY = {
    "MZB": "taxalist_MZB",
    "FB": "taxalist_FB",
    "FP": "taxalist_FB",
    "MF": "taxalist_MF",
    "RYBY": "taxalist_RYBY",
}

#: Podbarveni taxonu, ktery v taxonomickem seznamu neni. Takovy taxon
#: se nespari s autekologickymi charakteristikami a do metrik nevstoupi,
#: aniz by na to vypocet upozornil - proto je videt uz v prehledu vzorku.
#: Barva je zapsana jako hex, aby sla pouzit i ve stylesheetu legendy.
HEX_NEZNAMY = "#ffe0b2"
BARVA_NEZNAMY = QColor(HEX_NEZNAMY)

#: Popisek, ktery se u takoveho taxonu ukaze po najeti mysi.
POPIS_NEZNAMY = (
    "Taxon není v taxonomickém seznamu — nespáruje se "
    "s autekologickými charakteristikami a do metrik nevstoupí "
    "(do celkové abundance ano)."
)


class ModelTaxalistu(QSqlTableModel):
    """Taxalist, který ve sloupci SYN ukazuje platné jméno.

    Sloupec `SYN` nese jen příznak `SYNONYM` — informaci, že jde
    o synonymum. Které jméno je to platné, říká až `SYN_ID`, což je
    odkaz do téhož taxalistu. Uživateli je slovo "SYNONYM" k ničemu,
    v přehledu ho zajímá právě to platné jméno.

    Převod se dělá až při zobrazení, data se nemění. Když se platné
    jméno nepodaří dohledat (`SYN_ID` je prázdné nebo ukazuje jinam),
    zůstane původní hodnota — mlčky zmizet by neměla.
    """

    def __init__(self, parent=None, db=None):
        super().__init__(parent, db)
        self._jmena = {}
        self._sloupec_syn = -1
        self._sloupec_syn_id = -1

    def select(self):
        vysledek = super().select()
        self._sloupec_syn = self.fieldIndex("SYN")
        self._sloupec_syn_id = self.fieldIndex("SYN_ID")
        self._nacti_jmena()
        return vysledek

    def _nacti_jmena(self):
        """Načte mapu ID → jméno pro dohledání platných jmen."""
        self._jmena = {}
        if self._sloupec_syn_id < 0 or not self.tableName():
            return
        dotaz = QSqlQuery(self.database())
        if not dotaz.exec(f"SELECT ID, NAME FROM {self.tableName()}"):
            return
        while dotaz.next():
            self._jmena[str(dotaz.value(0))] = dotaz.value(1)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (role == Qt.ItemDataRole.DisplayRole
                and self._sloupec_syn >= 0
                and index.column() == self._sloupec_syn):
            puvodni = super().data(index, role)
            if puvodni:
                syn_id = super().data(
                    self.index(index.row(), self._sloupec_syn_id),
                    Qt.ItemDataRole.DisplayRole)
                platne = self._jmena.get(str(syn_id))
                if platne:
                    return platne
            return puvodni
        return super().data(index, role)


class PrepinacMoznosti(QWidget):
    """Přepínač mezi několika možnostmi - řada přepínačů vedle sebe.

    Náhrada za `QComboBox` na místech, kde se rozbalovací seznam na
    cílovém prostředí odmítal rozbalit. Příčinu se nepodařilo najít,
    a u několika málo možností stejně není důvod popup potřebovat:
    přepínače jsou vidět všechny naráz, klikne se rovnou na ten
    správný a žádné vyskakovací okno se neotevírá.

    Navenek se chová jako jednoduchá hodnota: `hodnota()` vrátí data
    vybrané položky, `nastav()` ji vybere bez vyvolání signálu
    a `zmenen` ohlásí změnu uživatelem.
    """

    zmenen = pyqtSignal()

    def __init__(self, polozky, popisek=None, parent=None):
        """Args:
            polozky: iterovatelné dvojic (popisek, hodnota)
            popisek: text před přepínači; None = žádný
        """
        super().__init__(parent)
        self._skupina = QButtonGroup(self)
        self._skupina.setExclusive(True)
        self._hodnoty = {}

        rozvrzeni = QHBoxLayout(self)
        rozvrzeni.setContentsMargins(0, 0, 0, 0)
        rozvrzeni.setSpacing(14)
        if popisek:
            rozvrzeni.addWidget(QLabel(popisek))

        for poradi, (text, hodnota) in enumerate(polozky):
            prepinac = QRadioButton(text)
            self._skupina.addButton(prepinac, poradi)
            self._hodnoty[poradi] = hodnota
            rozvrzeni.addWidget(prepinac)
            if poradi == 0:
                prepinac.setChecked(True)
        rozvrzeni.addStretch()

        # idClicked, ne idToggled - pri prepnuti se meni dva prepinace
        # (jeden se vypne, druhy zapne) a signal by prisel dvakrat.
        self._skupina.idClicked.connect(lambda _id: self.zmenen.emit())

    def hodnota(self):
        """Data právě vybrané položky."""
        return self._hodnoty.get(self._skupina.checkedId())

    def nastav(self, hledana):
        """Vybere danou možnost, aniž by ohlásila změnu.

        Používá se při návratu výběru, když uživatel přepnutí zruší -
        signál by v ten okamžik spustil další kolo dotazů na uložení.
        """
        for poradi, hodnota in self._hodnoty.items():
            if hodnota == hledana:
                tlacitko = self._skupina.button(poradi)
                if tlacitko is not None:
                    tlacitko.setChecked(True)
                return


def nazev_tabulky(db_connection, nazev):
    """Vrátí název tabulky tak, jak je uložený v databázi.

    SQLite je při dotazech na velikost písmen v názvu tabulky nevšímavá,
    ale `QSqlTableModel` si název drží a používá ho dál, takže na
    přesném tvaru záleží. Tahle funkce nesrovnalost srovná: hledá
    bez ohledu na velikost písmen a vrací skutečný název.

    Když tabulka neexistuje, vrací zadaný název beze změny - ať se chyba
    projeví na místě, kde se s ní dá něco dělat, a ne tady.
    """
    dotaz = QSqlQuery(db_connection)
    dotaz.prepare(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND lower(name) = lower(?)"
    )
    dotaz.addBindValue(nazev)
    if dotaz.exec() and dotaz.next():
        return dotaz.value(0)
    return nazev


class ModelDetailuVzorku(QSqlQueryModel):
    """Seznam taxonů vzorku; neznámé taxony podbarvuje.

    Dotaz vrací třetí sloupec `nezname` (1/0). Ten se v tabulce skrývá
    a slouží jen k obarvení řádku.
    """

    SLOUPEC_PRIZNAKU = 2

    def _je_neznamy(self, index):
        priznak = super().data(
            self.index(index.row(), self.SLOUPEC_PRIZNAKU),
            Qt.ItemDataRole.DisplayRole,
        )
        return bool(priznak)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.BackgroundRole and self._je_neznamy(index):
            return BARVA_NEZNAMY
        if role == Qt.ItemDataRole.ToolTipRole and self._je_neznamy(index):
            return POPIS_NEZNAMY
        return super().data(index, role)


class CiselnikovyModel(QSqlTableModel):
    """Model tabulky `utvary`, který kódované sloupce zobrazuje slovně.

    V databázi zůstávají krátké kódy (R, J, P, S, U, I, B, NEBROD) - jen
    s nimi umí pracovat rozřazovací registr. Uživatel ale vidí a zadává
    plné popisky (ŘEKA, JEZERO, PŘIROZENÝ, ...).

    Model proto překládá:
      * `data()` v roli zobrazení    kód -> popisek
      * `data()` v roli editace      kód -> popisek (aby combo trefilo položku)
      * `setData()`                  popisek -> kód, neznámou hodnotu odmítne
      * `headerData()`               název sloupce -> popisek hlavičky
    """

    def __init__(self, parent, db, ciselniky=None, popisky=None):
        super().__init__(parent, db)
        self._ciselniky_dle_jmena = (
            ciselniky if ciselniky is not None else ciselniky_modul.UTVARY
        )
        self._popisky = (
            popisky if popisky is not None else ciselniky_modul.UTVARY_POPISKY
        )
        self._ciselniky = {}

    def select(self):
        vysledek = super().select()
        # index sloupce známe až po načtení, název sloupce je stabilní
        self._ciselniky = {
            self.fieldIndex(sloupec): ciselnik
            for sloupec, ciselnik in self._ciselniky_dle_jmena.items()
            if self.fieldIndex(sloupec) >= 0
        }
        return vysledek

    def ciselnik_sloupce(self, sloupec):
        """Vrátí číselník pro daný index sloupce, nebo None."""
        return self._ciselniky.get(sloupec)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            ciselnik = self._ciselniky.get(index.column())
            if ciselnik is not None:
                return ciselnik.popis(super().data(index, Qt.ItemDataRole.DisplayRole))
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        ciselnik = self._ciselniky.get(index.column())
        if ciselnik is not None and role == Qt.ItemDataRole.EditRole:
            kod = ciselnik.kod(value)
            if kod is None:
                QMessageBox.warning(
                    None, "Neplatná hodnota",
                    f"'{value}' není povolená hodnota pro sloupec "
                    f"{ciselnik.popisek}.\n\nPovolené hodnoty: "
                    f"{', '.join(ciselnik.popisky)}",
                )
                return False
            value = kod
        return super().setData(index, value, role)

    def headerData(self, sekce, orientace, role=Qt.ItemDataRole.DisplayRole):
        if (orientace == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            nazev = self.record().fieldName(sekce)
            if nazev:
                return ciselnik_popisek(nazev, self._ciselniky_dle_jmena,
                                        self._popisky)
        return super().headerData(sekce, orientace, role)


class CiselnikovyDelegate(QStyledItemDelegate):
    """Editor kódovaných sloupců - rozbalovací nabídka povolených hodnot.

    Bez něj by uživatel psal popisek ručně a překlep by model odmítl;
    takhle se nedá zadat nic jiného než povolená hodnota.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

    def _ciselnik(self, index):
        model = index.model()
        if isinstance(model, QSortFilterProxyModel):
            index = model.mapToSource(index)
        zdroj = index.model()
        if hasattr(zdroj, "ciselnik_sloupce"):
            ciselnik = zdroj.ciselnik_sloupce(index.column())
            if ciselnik is not None:
                return ciselnik

        # Pojistka: model si mapu číselníků staví až v `select()`. Kdyby
        # se editor otevřel dřív, mapa je prázdná a delegát by místo
        # nabídky nabídl obyčejné textové pole. Číselník se proto zkusí
        # dohledat ještě podle názvu sloupce, který je stabilní vždycky.
        if zdroj is None:
            return None
        nazev = zdroj.headerData(
            index.column(), Qt.Orientation.Horizontal,
            Qt.ItemDataRole.EditRole)
        if not nazev and hasattr(zdroj, "record"):
            nazev = zdroj.record().fieldName(index.column())
        return ciselniky_modul.UTVARY.get(str(nazev or "").upper())

    def createEditor(self, parent, option, index):
        """Číselníkové sloupce se needitují v buňce.

        Vracet `None` znamena "tenhle sloupec nemam cim editovat", takze
        Qt zadny editor nevytvori. Hodnotu misto toho meni dialog
        s prepinaci - viz `LULANApp.uprav_ciselnikovou_bunku()`, ktery
        se otevre po dvojkliku.

        Duvod: v bunce byl driv rozbalovaci seznam, ale ten se na macOS
        vykresluje jako nativni nabidka, ktera se nekdy neotevre. Prvek
        pak vypada funkcne, jen na kliknuti nereaguje. Prepinace v dialogu
        zadnou vyskakovaci nabidku nepotrebuji.
        """
        if self._ciselnik(index) is not None:
            return None
        return super().createEditor(parent, option, index)

    # setEditorData ani setModelData se neprepisuji: pro ciselnikove
    # sloupce zadny editor nevznika (viz createEditor) a u ostatnich
    # sloupcu staci vychozi chovani QStyledItemDelegate.


class LULANApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_kod = None  # Initialize current_kod
        self._changing_selection = False  # Flag to prevent recursive selection changes
        self.table_data_modified = False  # Flag for left table changes
        self.detail_data_modified = False  # Flag for right detail changes
        self.pracovni_kopie = None  # nastaví se, pokud DB leží na síťovém disku
        self.initUI()

    #: Velikost okna, kdyz se na obrazovku vejde [px].
    VYCHOZI_OKNO = (1400, 900)

    def initUI(self):
        self.setWindowTitle('LULAN')
        self.setWindowIcon(ikona_aplikace())
        self._nastav_velikost_okna()

        # Připojení se drží po celý běh; mění se jen soubor, na který
        # ukazuje. Vytvořit se musí dřív, než se postaví záložky - modely
        # si spojení berou právě odsud.
        self.db = QSqlDatabase.addDatabase("QSQLITE")

        self.vytvor_menu()

        if not self._priprav_databazi():
            # Uživatel žádnou databázi nevybral - okno se ani neotevře.
            sys.exit(0)

        self.postav_taby()

    def _nastav_velikost_okna(self):
        """Otevře okno tak, aby se vešlo na obrazovku.

        Dřív se velikost nastavovala natvrdo na 1400×900. Na interním
        displeji notebooku, kde je plocha menší, okno přesahovalo přes
        okraj a jeho pravá část byla nedostupná. Rozměr se proto ořízne
        podle dostupné plochy (tedy bez systémových lišt) a okno se
        umístí doprostřed.
        """
        sirka, vyska = self.VYCHOZI_OKNO

        obrazovka = self.screen() or QApplication.primaryScreen()
        if obrazovka is None:
            self.resize(sirka, vyska)
            return

        plocha = obrazovka.availableGeometry()
        sirka = min(sirka, plocha.width())
        vyska = min(vyska, plocha.height())
        self.resize(sirka, vyska)

        # Vycentrovat, ale nikdy nezačít mimo plochu - na části obrazovky
        # schované pod lištou by se okno nedalo chytit za titulek.
        x = plocha.left() + max((plocha.width() - sirka) // 2, 0)
        y = plocha.top() + max((plocha.height() - vyska) // 2, 0)
        self.move(x, y)

    # -----------------------------------------------------------------
    # Databáze
    # -----------------------------------------------------------------

    def _priprav_databazi(self):
        """Otevře databázi při startu; když se nedaří, nechá vybrat jinou.

        Dřív se v takové chvíli aplikace ukončila. Jenže důvodů, proč
        se výchozí databáze neotevře, je víc — od neúplné instalace po
        soubor přesunutý jinam — a ve všech případech je užitečnější
        nechat uživatele ukázat, kde databáze leží, než ho poslat pryč.

        Returns:
            True, když je otevřená databáze; False, když uživatel skončil.
        """
        try:
            vychozi = cesta_k_databazi()
        except OSError as chyba:
            duvod = str(chyba)
        else:
            if self.otevri_databazi(vychozi, tise=True):
                return True
            duvod = self._duvod_neuspechu(vychozi)

        while True:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Databáze není k dispozici")
            dialog.setText(duvod)
            dialog.setInformativeText(
                "Můžete otevřít jiný soubor s databází LULANu.")
            vybrat = dialog.addButton(
                "Vybrat soubor…", QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton("Ukončit", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(vybrat)
            dialog.exec()

            if dialog.clickedButton() is not vybrat:
                return False

            cesta = self._dialog_vyberu_databaze()
            if not cesta:
                duvod = "Žádný soubor jste nevybral."
                continue
            if self.otevri_databazi(cesta):
                return True
            duvod = self._duvod_neuspechu(cesta)

    def _duvod_neuspechu(self, cesta):
        """Text pro dialog: proč se databáze neotevřela.

        Přednost má vlastní vysvětlení od `otevri_databazi()`. Chybu ze
        SQLite totiž Qt nemusí vždycky vyplnit — třeba když soubor sice
        otevřít jde, ale nejsou v něm tabulky LULANu.
        """
        podrobnost = getattr(self, "_posledni_duvod", "").strip()
        if podrobnost:
            return podrobnost
        chyba = self.db.lastError().text().strip()
        zprava = f"Databázi se nepodařilo otevřít:\n{cesta}"
        return f"{zprava}\n\n{chyba}" if chyba else zprava

    def _dialog_vyberu_databaze(self):
        """Nechá vybrat soubor s databází. Vrací cestu, nebo prázdný řetězec."""
        vychozi = os.path.dirname(self.db.databaseName() or "") or os.getcwd()
        cesta, _ = QFileDialog.getOpenFileName(
            self, "Otevřít databázi LULANu", vychozi,
            "Databáze SQLite (*.db *.sqlite *.sqlite3);;Všechny soubory (*)")
        return cesta

    def otevri_databazi(self, cesta, tise=False):
        """Připojí se k databázi na dané cestě.

        Args:
            cesta: soubor s databází
            tise: nevypisovat chybové hlášky (používá start, který si
                  poradí sám nabídkou jiného souboru)

        Returns:
            True při úspěchu.
        """
        self._posledni_duvod = ""
        if not cesta:
            return False

        if not os.path.exists(cesta):
            return self._neuspech(f"Soubor neexistuje:\n{cesta}", tise)

        # Kontrola úložiště může cestu změnit na místní pracovní kopii,
        # nebo vrátit None, když uživatel práci s takovou databází odmítl.
        cesta = self.zkontroluj_uloziste(cesta)
        if cesta is None:
            return self._neuspech(
                "Práci s databází na tomto úložišti jste odmítl.", tise)

        if self.db.isOpen():
            self.db.close()
        self.db.setDatabaseName(cesta)

        if not self.db.open():
            return self._neuspech(
                "Nelze se připojit k databázi:\n"
                f"{self.db.lastError().text()}\n\nSoubor: {cesta}", tise)

        chybi = self._chybejici_tabulky()
        if chybi:
            self.db.close()
            return self._neuspech(
                f"Soubor {os.path.basename(cesta)} sice jde otevřít, "
                "ale nevypadá jako databáze LULANu.\n\n"
                "Chybí tabulky: " + ", ".join(chybi), tise)

        self._aktualizuj_titulek(cesta)
        return True

    def _neuspech(self, zprava, tise):
        """Zaznamená, proč se databáze neotevřela, a případně to oznámí.

        Text si drží i tichý režim - startovní dialog ho pak ukáže sám,
        takže uživatel nedostane dvě okna po sobě.
        """
        self._posledni_duvod = zprava
        if not tise:
            QMessageBox.critical(self, "Chyba", zprava)
        return False

    #: Tabulky, bez kterych by aplikace nemela co zobrazovat. Slouzi jen
    #: k rozliseni "databaze LULANu" od jineho souboru SQLite - proto
    #: staci par zakladnich, ne cele schema.
    ZAKLADNI_TABULKY = ("loc", "samples", "data", "utvary")

    def _chybejici_tabulky(self):
        """Vrátí základní tabulky, které v otevřené databázi nejsou.

        SQLite otevře i prázdný nebo cizí soubor bez hlesnutí; kdyby se
        to nekontrolovalo, aplikace by se postavila a teprve při klikání
        by sypala hlášky o chybějících tabulkách.
        """
        pritomne = set()
        dotaz = QSqlQuery(self.db)
        if dotaz.exec("SELECT lower(name) FROM sqlite_master "
                      "WHERE type = 'table'"):
            while dotaz.next():
                pritomne.add(dotaz.value(0))
        return [t for t in self.ZAKLADNI_TABULKY if t.lower() not in pritomne]

    def _aktualizuj_titulek(self, cesta=None):
        """Do titulku okna dá název otevřené databáze."""
        cesta = cesta or self.db.databaseName()
        if self.pracovni_kopie is not None:
            self.setWindowTitle(
                f"LULAN — {os.path.basename(cesta)} (místní kopie, "
                f"originál: {self.pracovni_kopie.puvodni_cesta})")
        else:
            self.setWindowTitle(f"LULAN — {cesta}")

    def zmen_databazi(self):
        """Přepne aplikaci na jinou databázi (menu Databáze → Otevřít)."""
        if not self._smim_opustit_databazi():
            return

        cesta = self._dialog_vyberu_databaze()
        if not cesta:
            return
        if os.path.abspath(cesta) == os.path.abspath(self.db.databaseName()):
            return

        puvodni = self.db.databaseName()
        self._zahod_taby()
        # Případnou pracovní kopii je nutné vrátit dřív, než se pustíme
        # jinam - jinak by změny zůstaly viset v dočasném souboru.
        # Spojení se zavírá první, aby SQLite stihla dopsat žurnál.
        if self.db.isOpen():
            self.db.close()
        self.uloz_databazi_zpet()
        self.pracovni_kopie = None

        if self.otevri_databazi(cesta):
            self.postav_taby()
            self.statusBar().showMessage(
                f"Otevřena databáze {os.path.basename(cesta)}", 5000)
            return

        # Nepovedlo se - zkusíme se vrátit tam, kde jsme byli.
        if self.otevri_databazi(puvodni, tise=True):
            self.postav_taby()
            self.statusBar().showMessage(
                f"Zůstávám u {os.path.basename(puvodni)}", 5000)
        elif not self._priprav_databazi():
            self.close()
        else:
            self.postav_taby()

    def nacti_znovu(self):
        """Znovu načte data ze současné databáze."""
        if not self._smim_opustit_databazi():
            return
        self._zahod_taby()
        self.postav_taby()
        self.statusBar().showMessage("Data načtena znovu", 5000)

    def _smim_opustit_databazi(self):
        """Zeptá se na neuložené změny. Vrací False, když má zůstat vše tak."""
        rozdelane = []
        if getattr(self, "table_data_modified", False) or \
                getattr(self, "detail_data_modified", False):
            rozdelane.append("lokality")
        try:
            if self.has_unsaved_taxon_changes():
                rozdelane.append("taxony")
        except (AttributeError, RuntimeError):
            # Záložky ještě nestojí, takže rozdělaného nic být nemůže.
            pass
        if not rozdelane:
            return True

        odpoved = QMessageBox.question(
            self, "Neuložené změny",
            "Máte neuložené změny (" + ", ".join(rozdelane) + ").\n\n"
            "Pokračovat a změny zahodit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return odpoved == QMessageBox.StandardButton.Yes

    # -----------------------------------------------------------------
    # Záložky
    # -----------------------------------------------------------------

    #: Modely, ktere zalozky vyrabeji. Pri prepnuti databaze se musi
    #: zahodit vsechny - drzi si spojeni i nazvy tabulek te predchozi.
    MODELY = (
        "utvary_model", "utvary_proxy_model",
        "loc_model", "loc_proxy_model", "loc_detail_model",
        "samples_model", "samples_detail_model",
        "taxon_model", "taxon_detail_model",
        "results_samples_model", "results_detail_model",
        "results_yearly_model",
    )

    def postav_taby(self):
        """Postaví všech pět záložek nad právě otevřenou databází."""
        self.tabs = QTabWidget()
        self.tab0 = QWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tab4 = QWidget()

        self.tabs.addTab(self.tab0, "Útvary povrchových vod")
        self.tabs.addTab(self.tab1, "Lokality")
        self.tabs.addTab(self.tab2, "Vzorky")
        self.tabs.addTab(self.tab3, "Taxony")
        self.tabs.addTab(self.tab4, "Výsledky")

        self.initTab0()
        self.initTab1()
        self.initTab2()
        self.initTab3()
        self.initTab4()

        self.setCentralWidget(self.tabs)
        self._aktualizuj_titulek()

        # Šířky sloupců se srovnávají až po rozložení okna - do té doby
        # tabulky svou skutečnou šířku neznají. Dvojí odložení je záměr:
        # v prvním kole si rozdělovníky nastaví velikosti panelů a teprve
        # ve druhém je plocha tabulek konečná.
        QTimer.singleShot(0, lambda: QTimer.singleShot(
            0, self.srovnej_sirky_sloupcu))

    def srovnej_sirky_sloupcu(self):
        """Upraví šířky sloupců tak, aby se tabulky vešly bez posuvníku.

        Jen při sestavení záložek. Pozdější zvětšení okna do šířek nesahá,
        aby aplikace nepřeprala sloupec, který si uživatel sám přetáhl.
        """
        import sirky_sloupcu

        if self.centralWidget() is not None:
            sirky_sloupcu.srovnej_vse(self.centralWidget())

    def _zahod_taby(self):
        """Zruší záložky i modely, aby nedržely starou databázi.

        Model, který přežije přepnutí, by se dál ptal staré databáze -
        a jakmile se spojení pod ním zavře, začne Qt sypat varování do
        konzole. Proto se ruší i odkazy na modely, ne jen widgety.
        """
        stare = self.centralWidget()
        self.setCentralWidget(QWidget())
        if stare is not None:
            stare.setParent(None)
            stare.deleteLater()

        for nazev in self.MODELY:
            if hasattr(self, nazev):
                setattr(self, nazev, None)

        self.current_kod = None
        self.table_data_modified = False
        self.detail_data_modified = False

    # -----------------------------------------------------------------
    # Menu
    # -----------------------------------------------------------------

    def vytvor_menu(self):
        """Sestavi hlavni menu aplikace.

        Nabidka IMPORT je rizena popisem tabulek v modulu `import_csv`,
        takze pridani dalsi importovatelne tabulky nevyzaduje zasah do GUI.
        """
        from PyQt6.QtGui import QAction, QKeySequence

        menu = self.menuBar()

        databaze = menu.addMenu("&Databáze")
        akce = QAction("Otevřít…", self)
        akce.setShortcut(QKeySequence.StandardKey.Open)
        akce.setStatusTip("Přepnout na jiný soubor s databází LULANu")
        akce.triggered.connect(self.zmen_databazi)
        databaze.addAction(akce)

        akce = QAction("Načíst znovu", self)
        akce.setShortcut(QKeySequence.StandardKey.Refresh)
        akce.setStatusTip("Znovu načíst data ze současné databáze")
        akce.triggered.connect(self.nacti_znovu)
        databaze.addAction(akce)

        databaze.addSeparator()
        akce = QAction("Ukončit", self)
        akce.setShortcut(QKeySequence.StandardKey.Quit)
        akce.triggered.connect(self.close)
        databaze.addAction(akce)

        nabidka = menu.addMenu("&Import")

        vzory = nabidka.addMenu("Stáhnout vzorový soubor")
        for klic, popis in import_csv.POPISY.items():
            akce = QAction(f"{popis.nazev}…", self)
            akce.setStatusTip(popis.popis)
            akce.triggered.connect(
                lambda _=False, k=klic: self.uloz_vzorovy_soubor(k)
            )
            vzory.addAction(akce)

        nabidka.addSeparator()

        for klic, popis in import_csv.POPISY.items():
            akce = QAction(f"Importovat: {popis.nazev}…", self)
            akce.setStatusTip(f"Načíst CSV do tabulky {popis.tabulka}")
            akce.triggered.connect(
                lambda _=False, k=klic: self.importuj_csv(k)
            )
            nabidka.addAction(akce)

        export = menu.addMenu("&Export")
        for popis, akce_fn in (
            ("Vzorky…", self.exportuj_vzorky),
            ("Výsledky…", self.exportuj_vysledky),
        ):
            akce = QAction(popis, self)
            akce.triggered.connect(lambda _=False, f=akce_fn: f())
            export.addAction(akce)

        info = menu.addMenu("&Info")
        akce = QAction("O aplikaci…", self)
        akce.setStatusTip("Licence, zdroje dat, poděkování")
        akce.triggered.connect(self.zobraz_o_aplikaci)
        info.addAction(akce)

        akce = QAction("Kontrola prostředí…", self)
        akce.setStatusTip("Údaje o Qt a stav ovládacích prvků — pro hlášení chyb")
        akce.triggered.connect(self.zobraz_kontrolu_prostredi)
        info.addAction(akce)

        self.statusBar().showMessage("Připraveno")

    def uprav_ciselnikovou_bunku(self, index):
        """Změní hodnotu kódovaného sloupce dialogem s přepínači.

        Volá se po dvojkliku na buňku v tabulce útvarů. U sloupců bez
        číselníku neudělá nic - ty se editují normálně v buňce.
        """
        ciselnik = self.utvary_delegate._ciselnik(index)
        if ciselnik is None:
            return

        nynejsi = str(index.data() or "")
        sloupec = index.model().headerData(
            index.column(), Qt.Orientation.Horizontal) or ""

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Změnit: {sloupec}")

        prepinac = PrepinacMoznosti(
            [(popisek, popisek) for popisek in ciselnik.popisky])
        if nynejsi:
            prepinac.nastav(nynejsi)

        tlacitka = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        tlacitka.accepted.connect(dialog.accept)
        tlacitka.rejected.connect(dialog.reject)

        rozvrzeni = QVBoxLayout(dialog)
        rozvrzeni.addWidget(QLabel(f"Hodnota sloupce <b>{sloupec}</b>:"))
        rozvrzeni.addWidget(prepinac)
        rozvrzeni.addWidget(tlacitka)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        nova = prepinac.hodnota()
        if nova and nova != nynejsi:
            # Zapisuje se přes model pohledu, aby se změna propsala
            # i proxy modelem a spustila obvyklou kontrolu.
            index.model().setData(index, nova, Qt.ItemDataRole.EditRole)

    def kontrola_prostredi(self):
        """Údaje o prostředí a o stavu ovládacích prvků.

        Slouží k hledání příčin potíží, které se projeví jen u někoho -
        typicky když se nějaký prvek chová jinak, než jak vypadá v kódu.
        Místo dohadování ukáže, co aplikace o sobě opravdu ví.

        Returns:
            list řádků textu
        """
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        app = QApplication.instance()
        radky = [
            "— prostředí —",
            f"Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}",
            f"platform plugin: {app.platformName()}",
            f"styl: {app.style().objectName()}",
            f"Python {sys.version.split()[0]} na {sys.platform}",
            f"databáze: {self.db.databaseName()}",
            "",
            "— číselníkové sloupce na záložce Útvary —",
        ]

        pohled = getattr(self, "utvary_table_view", None)
        if pohled is None:
            radky.append("tabulka útvarů není sestavená")
            return radky

        vychozi = pohled.itemDelegate()
        for nazev in ciselniky_modul.UTVARY:
            sloupec = self.utvary_model.fieldIndex(nazev)
            if sloupec < 0:
                radky.append(f"{nazev}: sloupec v tabulce není")
                continue
            delegat = pohled.itemDelegateForColumn(sloupec)
            vlastni = delegat is not None and delegat is not vychozi
            ciselnik = self.utvary_model.ciselnik_sloupce(sloupec)
            radky.append(
                f"{nazev}: sloupec {sloupec}, "
                f"delegát {'ANO' if vlastni else 'NE'}, "
                f"číselník {'ANO' if ciselnik else 'NE'}"
                + (f" ({len(ciselnik.popisky)} hodnot)" if ciselnik else "")
            )

        radky += [
            "",
            f"spouštěče editace: {int(pohled.editTriggers().value)}",
            f"model pohledu: {type(pohled.model()).__name__}",
            f"zdrojový model: {type(self.utvary_model).__name__}",
        ]
        return radky

    def zobraz_kontrolu_prostredi(self):
        """Dialog s výsledkem kontroly; text jde označit a zkopírovat."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Kontrola prostředí")
        dialog.resize(620, 460)

        text = QTextBrowser(dialog)
        text.setPlainText("\n".join(self.kontrola_prostredi()))

        tlacitka = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        tlacitka.rejected.connect(dialog.reject)
        tlacitka.accepted.connect(dialog.accept)

        rozvrzeni = QVBoxLayout(dialog)
        rozvrzeni.addWidget(QLabel(
            "Tyhle údaje se hodí přiložit k hlášení chyby."))
        rozvrzeni.addWidget(text)
        rozvrzeni.addWidget(tlacitka)
        dialog.exec()

    def zobraz_o_aplikaci(self):
        """Dialog s licencí, zdroji dat a poděkováním."""
        import o_aplikaci

        dialog = QDialog(self)
        dialog.setWindowTitle("O aplikaci LULAN")
        dialog.resize(760, 640)

        text = QTextBrowser(dialog)
        text.setOpenExternalLinks(True)
        text.setHtml(o_aplikaci.html())

        tlacitka = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        tlacitka.rejected.connect(dialog.reject)
        tlacitka.accepted.connect(dialog.accept)

        rozvrzeni = QVBoxLayout(dialog)
        rozvrzeni.addWidget(text)
        rozvrzeni.addWidget(tlacitka)
        dialog.exec()

    def uloz_vzorovy_soubor(self, klic):
        """Ulozi vzorovy CSV soubor s hlavickou, napovedou a ukazkovym radkem."""
        popis = import_csv.POPISY[klic]
        vychozi = os.path.join(
            os.path.expanduser("~"), f"LULAN_vzor_{klic}.csv"
        )
        cesta, _ = QFileDialog.getSaveFileName(
            self, f"Uložit vzorový soubor - {popis.nazev}", vychozi,
            "CSV soubory (*.csv)"
        )
        if not cesta:
            return
        try:
            with open(cesta, "w", encoding="utf-8-sig", newline="") as f:
                f.write(import_csv.sablona_csv(klic))
        except OSError as e:
            QMessageBox.critical(self, "Chyba",
                                 f"Soubor se nepodařilo uložit: {e}")
            return
        QMessageBox.information(
            self, "Vzorový soubor uložen",
            f"Soubor byl uložen do:\n{cesta}\n\n"
            f"Řádky začínající znakem # jsou nápověda - můžete je nechat, "
            f"import je přeskočí.\nPrvní datový řádek je ukázkový, "
            f"přepište ho vlastními hodnotami.",
        )

    def importuj_csv(self, klic):
        """Nacte CSV, zkontroluje ho a po potvrzeni zapise do databaze."""
        popis = import_csv.POPISY[klic]
        cesta, _ = QFileDialog.getOpenFileName(
            self, f"Vyberte CSV soubor - {popis.nazev}", "",
            "CSV soubory (*.csv *.txt);;Všechny soubory (*)"
        )
        if not cesta:
            return

        try:
            radky, oddelovac, kodovani = import_csv.nacti_csv(cesta)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Soubor nelze načíst", str(e))
            return

        conn = self.sqlite_spojeni()
        try:
            znama = import_csv.existujici_klice(conn, klic)
            kontrola = import_csv.zkontroluj(radky, klic, znama)
        finally:
            conn.close()

        if not kontrola.ok:
            QMessageBox.critical(
                self, "Soubor obsahuje chyby",
                f"Import nebyl proveden - v souboru je "
                f"{len(kontrola.chyby)} chyb:\n\n"
                + "\n".join(kontrola.chyby[:15])
                + ("\n\n(zobrazeno prvních 15)" if len(kontrola.chyby) > 15
                   else ""),
            )
            return

        if not self._potvrd_import(cesta, oddelovac, kodovani, kontrola):
            return

        prepsat = QMessageBox.question(
            self, "Existující záznamy",
            "Co udělat se záznamy, které v databázi už jsou?\n\n"
            "Ano = přepsat je hodnotami ze souboru\n"
            "Ne  = ponechat původní a nové řádky přeskočit",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        # Zápis jde jiným spojením než to, kterým čtou tabulky, takže
        # se databáze na tu dobu z Qt uvolní - jinak by zápis narazil
        # na zámek rozečtených dotazů (viz `databaze_pro_zapis`).
        stat = None
        chyba = None
        with self.databaze_pro_zapis():
            conn = self.sqlite_spojeni()
            try:
                stat = import_csv.importuj(conn, kontrola.radky, klic, prepsat)
            except sqlite3.Error as e:
                conn.rollback()
                chyba = str(e)
            finally:
                conn.close()

        if chyba is not None:
            QMessageBox.critical(self, "Chyba při zápisu",
                                 f"Import se nezdařil: {chyba}")
            return

        QMessageBox.information(
            self, "Import dokončen",
            f"Vloženo: {stat.vlozeno}\n"
            f"Přepsáno: {stat.prepsano}\n"
            f"Přeskočeno (už existovalo): {stat.preskoceno}\n"
            f"Sloučeno duplicitních řádků: {stat.slouceno}",
        )

    #: Kolik radku prehledu se vejde do dialogu; zbytek jde do podrobnosti.
    MAX_RADKU_PREHLEDU = 15

    def _potvrd_import(self, cesta, oddelovac, kodovani, kontrola):
        """Ukáže, co se chystá importovat, a zeptá se na potvrzení.

        Dlouhý přehled by dialog roztáhl přes celou obrazovku, proto se
        v něm ukáže jen začátek a celý se schová pod tlačítko Podrobnosti.

        Returns:
            True, když uživatel potvrdil.
        """
        text = [
            f"Soubor: {os.path.basename(cesta)}",
            f"Oddělovač: '{oddelovac}', kódování: {kodovani}",
        ]

        if kontrola.souhrn:
            text.append("")
            text.extend(kontrola.souhrn[:self.MAX_RADKU_PREHLEDU])
            zbytek = len(kontrola.souhrn) - self.MAX_RADKU_PREHLEDU
            if zbytek > 0:
                text.append(f"   … a dalších {zbytek} "
                            "(celý seznam pod tlačítkem Podrobnosti)")
        else:
            text.append(f"Připraveno k importu: {len(kontrola.radky)} řádků")

        if kontrola.varovani:
            text.append("")
            text.append("Upozornění:")
            text.extend(f"  • {v}" for v in kontrola.varovani[:5])
            if len(kontrola.varovani) > 5:
                text.append(f"  • … a dalších {len(kontrola.varovani) - 5}")

        text.append("")
        text.append("Pokračovat v importu?")

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Potvrzení importu")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("\n".join(text))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes
                                  | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.Yes)

        podrobnosti = list(kontrola.souhrn)
        if len(kontrola.varovani) > 5:
            podrobnosti += ["", "Upozornění:"] + \
                [f"  • {v}" for v in kontrola.varovani]
        if podrobnosti:
            dialog.setDetailedText("\n".join(podrobnosti))

        return dialog.exec() == QMessageBox.StandardButton.Yes

    def sqlite_spojeni(self):
        """Otevre sqlite3 spojeni na tutez databazi, kterou pouziva GUI.

        Import pracuje s obycejnym sqlite3, aby sel spustit i mimo aplikaci.
        Cestu bere z Qt spojeni, takze respektuje pracovni kopii databaze
        i volbu jineho souboru.

        Cekani na zamek kryje jen kratkodobe zdrzeni od jineho procesu -
        synchronizacni klient nebo antivirus, ktery si soubor zrovna
        cte. To trva zlomky sekundy; pet vterin je tedy s rezervou dost
        a zaroven to neni doba, kterou by uzivatel odsedel u zamrzleho
        okna. Na zamek drzeny Qt modely lhuta nepomuze vubec - ten se
        sam neuvolni, od toho je `databaze_pro_zapis`.
        """
        return sqlite3.connect(self.db.databaseName(), timeout=CEKANI_NA_ZAMEK)

    #: Pojistka proti nekonecne smycce pri docitani modelu. Jedna davka
    #: je 256 radku, takze tohle staci na 1,25 milionu radku v modelu.
    MAX_DAVEK = 5000

    def _docti_modely(self):
        """Dočte všechny modely do konce, aby uvolnily zámky nad databází.

        Modely načítají řádky po dávkách po 256, takže jim dotaz zůstává
        otevřený, dokud uživatel nedoroluje na konec — a otevřený dotaz
        drží nad souborem čtecí zámek. Jakmile se dotaz dočte do konce,
        SQLite ho uzavře a zámek pustí.

        Dotazy se hledají dvěma cestami: mezi potomky okna a podle
        jmenného seznamu MODELY. Kdyby některý model nebyl zavěšený pod
        oknem, první cesta by ho minula — a jediný přehlédnutý model
        stačí k tomu, aby zámek držel dál.
        """
        modely = {id(m): m for m in self.findChildren(QSqlQueryModel)}
        for nazev in self.MODELY:
            model = getattr(self, nazev, None)
            if isinstance(model, QSqlQueryModel):
                modely.setdefault(id(model), model)

        for model in modely.values():
            self._docti_model(model)

    def _docti_model(self, model):
        """Dočte jeden model do konce; řádky chodí po dávkách po 256."""
        if model is None:
            return
        try:
            for _ in range(self.MAX_DAVEK):
                if not model.canFetchMore():
                    return
                model.fetchMore()
        except RuntimeError:
            return  # model mezitím zanikl

    @contextlib.contextmanager
    def databaze_pro_zapis(self):
        """Na dobu zápisu uvolní zámky, které nad databází drží Qt.

        SQLite pustí k zápisu jen jedno spojení, a jen tehdy, když nad
        souborem nikdo nedrží rozečtený dotaz. Qt modely si přitom dotaz
        otevřený drží — řádky načítají po dávkách, až jak uživatel roluje,
        takže dotaz nikdy samy nedočtou do konce. Zápis druhým spojením
        proto skončil hláškou „database is locked“.

        Ruční úpravy v tabulkách na to nenarazí: ty jdou týmž spojením,
        kterým se čte, a se sebou samým se spojení nepotká.

        Blok použijte všude, kde se do databáze zapisuje jinak než přes
        spojení aplikace — import CSV, dopočet abiotických parametrů,
        výpočet indexů (kvůli B-indexu). Po skončení se modely načtou
        znovu, takže tabulky ukazují čerstvá data.

        Yields:
            cesta k souboru s databází
        """
        self._docti_modely()
        try:
            yield self.db.databaseName()
        finally:
            self.obnov_modely()

    def obnov_modely(self):
        """Znovu nacte data do vsech tabulkovych modelu.

        Jen `utvary_model` a `loc_model` jsou QSqlTableModel a umí
        `select()`. Vzorky, taxony a výsledky drží QSqlQueryModel nad
        ručně skládaným dotazem, který se obnovuje přes příslušný
        `apply_*_filter()` — volání `select()` na něm skončí
        AttributeError a shodí aplikaci.

        Obnovují se i záložky, na které uživatel zrovna nekouká: po
        importu nebo výpočtu jsou jejich data stejně zastaralá a zjistil
        by to až ve chvíli, kdy by se podle nich rozhodoval.
        """
        for nazev in ("utvary_model", "loc_model"):
            model = getattr(self, nazev, None)
            if model is None:
                continue
            if nazev == "loc_model":
                # Zachovat filtr kategorie, jinak by se po importu objevily
                # i stojaté vody, které uživatel nemá zobrazené.
                model.setFilter(self._filtr_kategorie())
            model.select()

        for obnovit, model in (
            (self.apply_sample_filter, "samples_model"),
            (self.apply_taxon_filter, "taxon_model"),
            (self.apply_results_sample_filter, "results_samples_model"),
        ):
            if getattr(self, model, None) is None:
                continue
            try:
                obnovit()
            except (AttributeError, RuntimeError) as chyba:
                # Záložka ještě nestojí nebo se rozpadla; zbytek obnovy
                # kvůli tomu padnout nesmí.
                print(f"[obnov_modely] {model}: {chyba}")

    def initTab0(self):
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # Levá část - tabulka s útvary
        left_layout = QVBoxLayout()
        left_label = QLabel("Přehled útvarů povrchových vod")
        left_layout.addWidget(left_label)

        # Create table model
        self.utvary_model = CiselnikovyModel(self, self.db)
        self.utvary_model.setTable("utvary")
        
        # Configure the model for manual submit to prevent auto-saving
        self.utvary_model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        
        # Connect to dataChanged signal for validation
        self.utvary_model.dataChanged.connect(self.on_utvary_data_changed)
        
        # Before submitting, validate the data
        self.utvary_model.beforeUpdate.connect(self.validate_utvary_before_submit)
        
        self.utvary_model.select()
        
        # Popisky hlaviček dodává sám model (viz CiselnikovyModel.headerData),
        # aby byly na jednom místě spolu s číselníky.

        # Create table view
        self.utvary_table_view = QTableView()
        self.utvary_table_view.verticalHeader().setVisible(False)
        self.utvary_table_view.setSortingEnabled(True)
        self.utvary_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.utvary_table_view.setAlternatingRowColors(True)
        
        # Editace: kromě dvojkliku stačí i kliknutí na už vybranou buňku.
        # U číselníkových sloupců se tím rovnou otevře nabídka hodnot.
        self.utvary_table_view.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked |
            QTableView.EditTrigger.SelectedClicked |
            QTableView.EditTrigger.EditKeyPressed
        )
        
        # --- Přidání proxy modelu pro filtrování ---
        self.utvary_proxy_model = QSortFilterProxyModel(self)
        self.utvary_proxy_model.setSourceModel(self.utvary_model)
        self.utvary_proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.utvary_table_view.setModel(self.utvary_proxy_model)

        # Kódované sloupce se mění dialogem po dvojkliku, ne v buňce.
        self.utvary_table_view.doubleClicked.connect(
            self.uprav_ciselnikovou_bunku)

        self.utvary_delegate = CiselnikovyDelegate(self.utvary_model, self)
        for sloupec in ciselniky_modul.UTVARY:
            index = self.utvary_model.fieldIndex(sloupec)
            if index >= 0:
                self.utvary_table_view.setItemDelegateForColumn(
                    index, self.utvary_delegate
                )
        
        # Hide DTCH column if it exists (usually last column)
        total_columns = self.utvary_model.columnCount()
        if total_columns > 7:
            self.utvary_table_view.setColumnHidden(total_columns - 1, True)

        # Resize columns
        header = self.utvary_table_view.horizontalHeader()
        header.setStretchLastSection(True)
        self.utvary_table_view.resizeColumnsToContents()
        
        # --- Filtrovací řádek nad tabulkou ---
        # Viditelné sloupce: 0-6 (KOD, NÁZEV, DÍLČÍ POVODÍ, KATEGORIE, HMWB, VYSYCHAVÝ, BROD)
        visible_columns = [0, 1, 2, 3, 4, 5, 6]
        popisky = [self.utvary_model.headerData(c, Qt.Orientation.Horizontal)
                   or "" for c in visible_columns]
        filter_widget = RadekFiltru(
            self.utvary_table_view, visible_columns, popisky)
        filter_widget.zmenen.connect(self.pouzij_filtr_utvaru)
        self.utvary_filters = filter_widget
        
        # Stacked layout pro filtry a tabulku
        stacked_layout = QVBoxLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        stacked_layout.addWidget(filter_widget)
        stacked_layout.addWidget(self.utvary_table_view)
        
        stacked_container = QWidget()
        stacked_container.setLayout(stacked_layout)
        left_layout.addWidget(stacked_container)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Pravá část - tlačítka pod sebou
        right_layout = QVBoxLayout()
        right_label = QLabel("Akce")
        right_layout.addWidget(right_label)
        
        self.save_utvary_button = QPushButton("Uložit změny")
        self.save_utvary_button.clicked.connect(self.save_utvary_changes)
        right_layout.addWidget(self.save_utvary_button)
        
        self.add_utvar_button = QPushButton("Přidat útvar")
        self.add_utvar_button.clicked.connect(self.add_new_utvar)
        right_layout.addWidget(self.add_utvar_button)
        
        self.delete_utvar_button = QPushButton("Smazat útvar")
        self.delete_utvar_button.clicked.connect(self.delete_selected_utvary)
        right_layout.addWidget(self.delete_utvar_button)
        
        self.import_utvary_button = QPushButton("Načíst z CSV")
        self.import_utvary_button.clicked.connect(self.import_utvary_from_csv)
        right_layout.addWidget(self.import_utvary_button)
        
        # Přidání prázdného prostoru, aby tlačítka byla nahoře
        right_layout.addStretch()
        
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        right_widget.setFixedWidth(200)  # Nastavení pevné šířky pravého widgetu

        # Přidání widgetů do splitteru
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([1100, 200])  # Nastavení výchozí šířky: levý 1100px, pravý 200px

        # Přidání splitteru do hlavního layoutu
        main_layout.addWidget(splitter)
        
        self.tab0.setLayout(main_layout)
        
        # Define allowed values for validation
        # Povolené hodnoty drží ciselniky.UTVARY - jedno místo pro
        # zobrazení, editaci i kontrolu.
        self.utvary_allowed_values = {
            sloupec: list(ciselnik.kody)
            for sloupec, ciselnik in ciselniky_modul.UTVARY.items()
        }
    
    def initTab1(self):
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # Levá část - tabulka s názvem "Přehled lokalit"
        left_layout = QVBoxLayout()

        # Záhlaví: popisek a přepínač kategorie vodních útvarů.
        # Stojaté vody jsou v českém systému hodnocení okrajové (77 útvarů
        # proti tisícovce tekoucích), takže se ve výchozím stavu nezobrazují
        # a běžný uživatel o ně nezakopne.
        zahlavi = QHBoxLayout()
        zahlavi.setContentsMargins(0, 0, 0, 0)
        zahlavi.addWidget(QLabel("Přehled lokalit"))
        zahlavi.addStretch(1)
        self.stojate_vody_checkbox = QCheckBox("Zobrazit i stojaté vody")
        self.stojate_vody_checkbox.setToolTip(
            "Útvary kategorie jezero (nádrže, rybníky, zatopené těžební "
            "jámy). Hodnotí se podle jiné metodiky a mají jiné abiotické "
            "parametry — hloubky a dobu zdržení místo Strahlerova řádu, "
            "plochy povodí a sklonu."
        )
        self.stojate_vody_checkbox.toggled.connect(self.prepni_kategorii_lokalit)
        zahlavi.addWidget(self.stojate_vody_checkbox)
        zahlavi_widget = QWidget()
        zahlavi_widget.setLayout(zahlavi)
        zahlavi_widget.setFixedHeight(VYSKA_ZAHLAVI)
        left_layout.addWidget(zahlavi_widget)

        self.loc_model = QSqlTableModel(self, self.db)
        self.loc_model.setTable("loc")
        
        # Configure the model for manual submit to prevent auto-saving
        self.loc_model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        
        # Connect to dataChanged signal to track table modifications
        self.loc_model.dataChanged.connect(self.on_table_data_changed)
        
        self.loc_model.setFilter(self._filtr_kategorie())
        self.loc_model.select()
        self.loc_model.setHeaderData(1, Qt.Orientation.Horizontal, "KOD")
        self.loc_model.setHeaderData(2, Qt.Orientation.Horizontal, "VODNÍ ÚTVAR")
        self.loc_model.setHeaderData(3, Qt.Orientation.Horizontal, "TOK")
        self.loc_model.setHeaderData(4, Qt.Orientation.Horizontal, "PROFIL")

        self.loc_table_view = QTableView()
        self.loc_table_view.verticalHeader().setVisible(False)

        # --- Začátek bloku pro filtrování a proxy model ---
        self.loc_table_view.setSortingEnabled(True)
        self.loc_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.loc_table_view.setAlternatingRowColors(True)

        # Přidání filtrů do záhlaví
        header = self.loc_table_view.horizontalHeader()
        header.setSectionsClickable(True)
        # Poslední sloupec (PROFIL) vyplní zbytek šířky tabulky.
        header.setStretchLastSection(True)

        # Použijeme QSortFilterProxyModel
        self.loc_proxy_model = QSortFilterProxyModel(self)
        self.loc_proxy_model.setSourceModel(self.loc_model)
        self.loc_proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.loc_table_view.setModel(self.loc_proxy_model)

        # --- Konec bloku pro filtrování a proxy model ---

        self.loc_table_view.resizeColumnsToContents()

        # Connect selection change instead of click to handle selection changes properly
        self.loc_table_view.selectionModel().currentRowChanged.connect(self.on_location_selection_changed)

        # Skrytí vúech ostatních sloupců kromě "KOD", "VODNI_UTVAR" "TOK" a "PROFIL"
        total_columns = self.loc_model.columnCount()
        visible_columns = [1, 2, 3, 4]  # Sloupce, které chceme zobrazit
        for col in range(total_columns):
            if col not in visible_columns:
                self.loc_table_view.setColumnHidden(col, True)

        # --- Filtrovací řádek nad tabulkou ---
        sloupce_filtru = [1, 2, 3, 4]
        popisky = [self.loc_model.headerData(c, Qt.Orientation.Horizontal)
                   or "" for c in sloupce_filtru]
        self.filter_overlay_widget = RadekFiltru(
            self.loc_table_view, sloupce_filtru, popisky)
        self.filter_overlay_widget.zmenen.connect(self.pouzij_filtr_lokalit)
        self.loc_filters = self.filter_overlay_widget

        stacked_layout = QVBoxLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        stacked_layout.addWidget(self.filter_overlay_widget)
        stacked_layout.addWidget(self.loc_table_view, 1)

        stacked_container = QWidget()
        stacked_container.setLayout(stacked_layout)
        left_layout.addWidget(stacked_container)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Pravá část - tabulka s názvem "Abiotické parametry"
        right_layout = QVBoxLayout()
        pravé_zahlavi = QHBoxLayout()
        pravé_zahlavi.setContentsMargins(0, 0, 0, 0)
        pravé_zahlavi.addWidget(QLabel("Abiotické parametry"))
        pravé_zahlavi.addStretch(1)
        zahlavi_vpravo = QWidget()
        zahlavi_vpravo.setLayout(pravé_zahlavi)
        zahlavi_vpravo.setFixedHeight(VYSKA_ZAHLAVI)
        right_layout.addWidget(zahlavi_vpravo)

        self.loc_detail_model = QStandardItemModel(0, 2)
        self.loc_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
        
        # Connect to data changed signal to track modifications
        self.loc_detail_model.dataChanged.connect(self.on_detail_data_changed)
        self.detail_data_modified = False
        
        self.loc_detail_table_view = QTableView()
        self.loc_detail_table_view.setModel(self.loc_detail_model)
        self.loc_detail_table_view.verticalHeader().setVisible(False)
        self.loc_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.loc_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.loc_detail_table_view.setAlternatingRowColors(True)
        self.loc_detail_table_view.setColumnWidth(1, 100)  # pevná úířka druhého sloupce

        # Výška se odvozuje od počtu řádků, aby se vešly všechny parametry
        # a pod tabulkou nezůstával prázdný pás. Pevná hodnota by při každém
        # přidání parametru do DETAIL_LOKALITY přestala stačit.
        self.loc_detail_table_view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._uprav_vysku_detailu()

        right_layout.addWidget(self.loc_detail_table_view)

        # Tlačítka pro uložení změn a přidání/smazání lokality
        self.save_changes_button = QPushButton("Uložit změny")
        self.save_changes_button.clicked.connect(self.save_changes_button_click_handler)

        self.add_location_button = QPushButton("Přidat lokalitu")
        self.add_location_button.clicked.connect(self.add_new_location)

        right_layout.addWidget(self.save_changes_button)
        right_layout.addWidget(self.add_location_button)

        self.delete_location_button = QPushButton("Smazat lokalitu")
        self.delete_location_button.clicked.connect(self.delete_selected_locations)
        right_layout.addWidget(self.delete_location_button)

        # Přidání tlačítka pro import lokalit z CSV
        self.import_locations_button = QPushButton("Načíst lokality z csv")
        self.import_locations_button.clicked.connect(self.import_locations_from_csv)
        right_layout.addWidget(self.import_locations_button)

        # Doplnění abiotických parametrů (souřadnice, nadm. výška, Strahler, …)
        self.abiotic_button = QPushButton("Doplnit abiotické parametry")
        self.abiotic_button.setToolTip(
            "Dopočítá chybějící abiotické parametry lokalit: souřadnice "
            "S-42 / S-JTSK / UTM, nadmořskou výšku a sklon z DMR 5G, "
            "Strahlerův řád, úmoří, vzdálenost od pramene a plochu povodí.\n\n"
            "Pomocná funkce — zdroje dat, licence a upozornění se zobrazí "
            "před spuštěním. Odvozené hodnoty je vždy nutné zkontrolovat."
        )
        self.abiotic_button.clicked.connect(self.fill_abiotic_params)
        right_layout.addWidget(self.abiotic_button)

        # --- Mapa: poloha vybrané lokality v rámci ČR --------------------
        # Rámeček bez vlastního pozadí - obrys ČR se kreslí přímo na panel,
        # aby pod mapou nezůstával bílý obdélník.
        # Rámeček je bez nadpisu i bez rámu - mapa se vysvětluje sama
        # a popisek nad ní jen ubíral místo.
        mapa_ramecek = QGroupBox()
        mapa_ramecek.setStyleSheet("QGroupBox { border: none; margin: 0px; }")
        mapa_layout = QVBoxLayout()
        mapa_layout.setContentsMargins(0, 6, 0, 0)
        self.mapa_lokalit = MapaLokalit()
        self.mapa_lokalit.setToolTip(
            "Hranice ČR ze shapefilu src/GIS/hrcr_S42.shp (S-42, pásmo 3). "
            "Červená tečka označuje vybranou lokalitu."
        )
        mapa_layout.addWidget(self.mapa_lokalit)
        mapa_ramecek.setLayout(mapa_layout)
        right_layout.addWidget(mapa_ramecek)

        # zbytek volného místa zůstane pod mapou, ne uvnitř rámečku
        right_layout.addStretch()

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        # Širší panel: popisky abiotických parametrů jsou dlouhé (úmoří
        # má nejdelší) a zároveň tím dostane víc místa mapa pod nimi.
        right_widget.setFixedWidth(430)

        # Přidání widgetů do splitteru
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([780, 430])

        # Přidání splitteru do hlavního layoutu
        main_layout.addWidget(splitter)

        self.tab1.setLayout(main_layout)

    def on_table_data_changed(self):
        """Track when main table data is modified"""
        self.table_data_modified = True

    def on_detail_data_changed(self):
        """Track when detail data is modified"""
        self.detail_data_modified = True

    def has_unsaved_changes(self):
        """Check if there are any unsaved changes"""
        return (hasattr(self, 'table_data_modified') and self.table_data_modified) or \
            (hasattr(self, 'detail_data_modified') and self.detail_data_modified)

    def on_location_selection_changed(self, current, previous):
        """Handle location selection changes with proper unsaved data checking"""
        if not current.isValid():
            return
        
        # Prevent recursive calls
        if hasattr(self, '_changing_selection') and self._changing_selection:
            return
            
        # Check if there are unsaved changes in either table or detail view
        if self.has_unsaved_changes():
            # Set flag to prevent recursive calls
            self._changing_selection = True
            
            try:
                changes_text = []
                if hasattr(self, 'table_data_modified') and self.table_data_modified:
                    changes_text.append("v hlavní tabulce")
                if hasattr(self, 'detail_data_modified') and self.detail_data_modified:
                    changes_text.append("v detailech lokality")
                
                changes_description = " a ".join(changes_text)
                
                reply = QMessageBox.question(
                    self,
                    "Neuložené změny",
                    f"Máte neuložené změny {changes_description}. Chcete je uložit?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Save all changes using QTimer to defer execution
                    QTimer.singleShot(0, lambda: self.save_all_changes(refresh_model=False))
                    return
                elif reply == QMessageBox.StandardButton.Cancel:
                    # Revert selection by blocking signals temporarily
                    self.loc_table_view.selectionModel().blockSignals(True)
                    if previous.isValid():
                        self.loc_table_view.selectionModel().setCurrentIndex(previous, 
                            self.loc_table_view.selectionModel().SelectionFlag.SelectCurrent)
                    self.loc_table_view.selectionModel().blockSignals(False)
                    self._changing_selection = False
                    return
                # If No - continue with loading new data (changes will be discarded)
                else:
                    # Discard changes
                    self.discard_all_changes()
                
            finally:
                # Always reset the flag
                self._changing_selection = False
        
        # Load new location details
        self.load_location_details(current)

    def save_all_changes(self, refresh_model=True):
        """Save changes in the main location table and optionally in detail view"""
        success = True
        
        # Save main table changes
        if hasattr(self, 'table_data_modified') and self.table_data_modified:
            try:
                if not self.loc_model.submitAll():
                    error_msg = self.loc_model.lastError().text()
                    QMessageBox.critical(self, "Chyba", f"Nepodařilo se uložit změny v tabulce: {error_msg}")
                    return False
                
                self.table_data_modified = False
                
            except Exception as e:
                QMessageBox.critical(self, "Chyba", f"Neočekávaná chyba při ukládání tabulky: {str(e)}")
                return False
        
        # Save detail changes if they exist
        if hasattr(self, 'detail_data_modified') and self.detail_data_modified:
            success = self.save_location_changes(refresh_model=False)
            if not success:
                return False
        
        # Refresh model only if requested and all saves were successful
        if refresh_model and success:
            QTimer.singleShot(0, self.loc_model.select)
            # -- Begin Added Block --
            self.loc_model.select()
            self.loc_table_view.clearSelection()
            # -- End Added Block --
            if hasattr(self, 'detail_data_modified') and not self.detail_data_modified:
                QMessageBox.information(self, "Úspěch", "Změny byly úspěšně uloženy.")
        
        return success

    def discard_all_changes(self):
        """Discard all unsaved changes"""
        # Discard table changes
        if hasattr(self, 'table_data_modified') and self.table_data_modified:
            self.loc_model.revertAll()
            self.table_data_modified = False
        
        # Detail changes will be discarded when new data is loaded
        self.detail_data_modified = False

    #: Sloupce zobrazované v detailu lokality.
    #:
    #: Jediný seznam pro načtení i uložení - popisek, název sloupce v tabulce
    #: `loc` a typ pro převod hodnoty. Ukládání se váže podle NÁZVU sloupce
    #: (drží se v roli Qt.ItemDataRole.UserRole u řádku), ne podle pořadí:
    #: dřív stačilo vložit jeden řádek na špatné místo a hodnota se tiše
    #: zapsala do jiného sloupce.
    #: Abiotické parametry tekoucích vod (kategorie R).
    DETAIL_TEKOUCI = [
        ("Zeměpisná šířka", "WGS84_LAT", "cislo"),
        ("Zeměpisná délka", "WGS84_LON", "cislo"),
        ("Strahlerův řád", "STRAHLER", "cele"),
        ("Nadmořská výška (m n. m.)", "MNM", "cislo"),
        ("Plocha povodí (km²)", "PLOCHA_POV", "cislo"),
        ("Vzdálenost od pramene (km)", "KM_OD_PRAM", "cislo"),
        ("Sklon (‰)", "SLOPE", "cislo"),
        ("Úmoří (1 = Labe, 2 = Odra, 3 = Dunaj)", "UMORI", "cele"),
    ]

    #: Abiotické parametry stojatých vod (kategorie J). Metodika pro
    #: hodnocení ekologického potenciálu kategorie jezero (Borovec a kol.
    #: 2014, Tab. 1) staví typologii na nadmořské výšce, hloubkách a době
    #: zdržení; Strahlerův řád, plocha povodí ani sklon toku pro ni nemají
    #: smysl.
    DETAIL_STOJATE = [
        ("Zeměpisná šířka", "WGS84_LAT", "cislo"),
        ("Zeměpisná délka", "WGS84_LON", "cislo"),
        ("Nadmořská výška hladiny (m n. m.)", "MNM", "cislo"),
        ("Maximální hloubka (m)", "MAX_HLOUBKA", "cislo"),
        ("Průměrná hloubka (m)", "PRUM_HLOUBKA", "cislo"),
        ("Plocha hladiny (km²)", "PLOCHA_KM2", "cislo"),
        ("Doba zdržení (rok)", "TRT", "cislo"),
        ("Geologie (1 = krystalinikum, 2 = sedimenty)", "GEOLOGIE", "cele"),
        ("Úmoří (1 = Labe, 2 = Odra, 3 = Dunaj)", "UMORI", "cele"),
    ]

    #: Sada, se kterou se právě pracuje. Přepíná ji `_sada_detailu()` podle
    #: kategorie vybrané lokality.
    DETAIL_LOKALITY = DETAIL_TEKOUCI

    def _filtr_kategorie(self):
        """SQL podmínka pro seznam lokalit podle stavu zaškrtávátka.

        Prázdná KATEGORIE se bere jako tekoucí voda — takové jsou všechny
        záznamy pořízené před rozšířením schématu o stojaté vody.
        """
        if getattr(self, "stojate_vody_checkbox", None) is not None \
                and self.stojate_vody_checkbox.isChecked():
            return ""
        return "KATEGORIE IS NULL OR KATEGORIE <> 'J'"

    def prepni_kategorii_lokalit(self, _zaskrtnuto=False):
        """Překreslí seznam lokalit podle zaškrtávátka stojatých vod."""
        model = getattr(self, "loc_model", None)
        if model is None:
            return
        model.setFilter(self._filtr_kategorie())
        model.select()
        pohled = getattr(self, "loc_table_view", None)
        if pohled is not None:
            pohled.resizeColumnsToContents()

    def _sada_detailu(self, kod):
        """Vybere sadu abiotických parametrů podle kategorie lokality.

        Tekoucí a stojaté vody mají zcela jiné vstupy — u jezera nedává
        Strahlerův řád ani sklon toku smysl a naopak jsou potřeba hloubky
        a doba zdržení.

        Args:
            kod: KOD lokality

        Returns:
            seznam trojic (popisek, sloupec, typ)
        """
        dotaz = QSqlQuery(self.db)
        dotaz.prepare("SELECT KATEGORIE FROM loc WHERE KOD = ?")
        dotaz.addBindValue(kod)
        if dotaz.exec() and dotaz.next() and dotaz.value(0) == "J":
            return self.DETAIL_STOJATE
        return self.DETAIL_TEKOUCI

    def _uprav_vysku_detailu(self):
        """Nastaví výšku tabulky detailu tak, aby se vešly všechny řádky."""
        pohled = getattr(self, "loc_detail_table_view", None)
        if pohled is None:
            return
        # Rozhoduje delší ze sad, aby se výška neměnila při každém kliknutí.
        nejvic = max(len(self.DETAIL_TEKOUCI), len(self.DETAIL_STOJATE))
        radku = max(pohled.model().rowCount(), nejvic)
        vyska_radku = pohled.verticalHeader().defaultSectionSize()
        vyska = (
            pohled.horizontalHeader().height()
            + radku * vyska_radku
            + 2 * pohled.frameWidth()
        )
        pohled.setFixedHeight(vyska)

    def zobraz_lokalitu_na_mape(self, kod):
        """Vykreslí polohu lokality do mapového rámečku.

        Bere souřadnice S-42, protože v témže systému je i vrstva hranic.
        Když je lokalita nemá, dopočítají se z WGS84 (viz mapa_lokalit).
        """
        mapa = getattr(self, "mapa_lokalit", None)
        if mapa is None:
            return

        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT S42_X, S42_Y, WGS84_LAT, WGS84_LON, TOK, PROFIL "
            "FROM loc WHERE KOD = ?"
        )
        query.addBindValue(kod)
        if not query.exec() or not query.next():
            mapa.vycisti()
            return

        radek = {
            "S42_X": query.value(0), "S42_Y": query.value(1),
            "WGS84_LAT": query.value(2), "WGS84_LON": query.value(3),
        }
        x, y = souradnice_lokality(radek)
        popis = " – ".join(
            str(query.value(i)) for i in (4, 5) if query.value(i)
        ) or str(kod)
        mapa.zobraz_lokalitu(x, y, popis)

    def load_location_details(self, index):
        """Load location details with improved error handling"""
        try:
            source_index = self.loc_proxy_model.mapToSource(index)
            kod = self.loc_model.record(source_index.row()).value("KOD")

            # Sada parametrů se řídí kategorií lokality (tekoucí / stojatá).
            self.DETAIL_LOKALITY = self._sada_detailu(kod)
            sloupce = [s for _, s, _ in self.DETAIL_LOKALITY]
            query = QSqlQuery(self.db)
            query.prepare(
                f"SELECT {', '.join(sloupce)} FROM loc WHERE KOD = ?"
            )
            query.addBindValue(kod)

            if not query.exec():
                QMessageBox.warning(self, "Chyba", f"Nepodařilo se načíst detaily: {query.lastError().text()}")
                return

            if not query.next():
                QMessageBox.warning(self, "Chyba", f"Nepodařilo se načíst detaily pro lokalitu s KOD: {kod}")
                return

            details = [query.value(i) for i in range(len(sloupce))]
            self.zobraz_lokalitu_na_mape(kod)

            # Disconnect the dataChanged signal temporarily to avoid triggering during loading
            self.loc_detail_model.dataChanged.disconnect()

            try:
                # Clear model and load new values
                self.loc_detail_model.clear()
                self.loc_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
                for (popisek, sloupec, _typ), value in zip(
                        self.DETAIL_LOKALITY, details):
                    label_item = QStandardItem(popisek)
                    label_item.setEditable(False)  # Make description non-editable
                    # název sloupce si neseme s řádkem, ať na něm ukládání
                    # nezávisí na pořadí
                    label_item.setData(sloupec, Qt.ItemDataRole.UserRole)
                    value_item = QStandardItem(str(value) if value is not None else "")
                    value_item.setEditable(True)
                    value_item.setData(sloupec, Qt.ItemDataRole.UserRole)
                    self.loc_detail_model.appendRow([label_item, value_item])
            finally:
                # Reconnect the signal and reset modification flag
                self.loc_detail_model.dataChanged.connect(self.on_detail_data_changed)
                self.detail_data_modified = False
                self._uprav_vysku_detailu()

            # Store current kod for saving changes
            self.current_kod = kod

            # Set column widths in loc_detail_table_view
            self.loc_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.loc_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.loc_detail_table_view.setColumnWidth(1, 100)
            
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Neočekávaná chyba při načítání detailů: {str(e)}")
            # Reconnect signal if it was disconnected
            try:
                self.loc_detail_model.dataChanged.connect(self.on_detail_data_changed)
            except TypeError:
                pass  # signál už může být připojený

    def save_location_changes(self, refresh_model=True):
        """Save location changes with improved error handling"""
        if not hasattr(self, 'current_kod') or self.current_kod is None:
            QMessageBox.warning(self, "Chyba", "Není vybrána žádná lokalita pro uložení změn.")
            return False

        # Move focus to button to end any active editing
        self.save_changes_button.setFocus()

        # Use the existing Qt database connection instead of creating a new one
        if not self.db.isOpen():
            QMessageBox.critical(self, "Chyba", "Databázové připojení není aktivní.")
            return False

        # Hodnoty se sbírají podle NÁZVU sloupce uloženého u řádku, takže
        # na pořadí řádků v modelu nezáleží. Neplatný zápis se rovnou ohlásí
        # místo toho, aby se do databáze tiše zapsalo NULL.
        typy = {sloupec: typ for _, sloupec, typ in self.DETAIL_LOKALITY}
        hodnoty = {}
        chyby = []
        for row in range(self.loc_detail_model.rowCount()):
            item = self.loc_detail_model.item(row, 1)
            if item is None:
                continue
            sloupec = item.data(Qt.ItemDataRole.UserRole)
            if sloupec not in typy:
                continue
            popisek = self.loc_detail_model.item(row, 0).text()
            text = (item.text() or "").strip()
            if text == "":
                hodnoty[sloupec] = None
                continue
            try:
                cislo = float(text.replace(",", "."))
            except ValueError:
                chyby.append(f"{popisek}: '{text}' není číslo")
                continue
            if typy[sloupec] == "cele":
                if abs(cislo - round(cislo)) > 1e-9:
                    chyby.append(f"{popisek}: '{text}' musí být celé číslo")
                    continue
                cislo = int(round(cislo))
            hodnoty[sloupec] = cislo

        if chyby:
            QMessageBox.warning(
                self, "Neplatné hodnoty",
                "Změny nebyly uloženy, opravte prosím:\n\n"
                + "\n".join(f"  • {c}" for c in chyby),
            )
            return False

        if not hodnoty:
            QMessageBox.warning(self, "Chyba",
                                "Detail lokality neobsahuje žádná pole k uložení.")
            return False

        # Start transaction
        if not self.db.transaction():
            QMessageBox.critical(self, "Chyba", "Nepodařilo se začít transakci.")
            return False

        try:
            sloupce = list(hodnoty)
            query = QSqlQuery(self.db)
            query.prepare(
                "UPDATE loc SET "
                + ", ".join(f"{s} = ?" for s in sloupce)
                + " WHERE KOD = ?"
            )
            for sloupec in sloupce:
                query.addBindValue(hodnoty[sloupec])
            query.addBindValue(self.current_kod)

            if not query.exec():
                self.db.rollback()
                error_msg = query.lastError().text()
                QMessageBox.critical(self, "Chyba", f"Nepodařilo se uložit změny: {error_msg}")
                return False

            # Commit the transaction
            if not self.db.commit():
                QMessageBox.critical(self, "Chyba", "Nepodařilo se potvrdit změny.")
                return False
                
            # Reset the modification flag after successful save
            self.detail_data_modified = False
            
            # Only refresh the model if requested (avoid during selection changes)
            if refresh_model:
                self.loc_model.select()
                QMessageBox.information(self, "Úspěch", "Změny byly úspěšně uloženy.")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Chyba", f"Neočekávaná chyba při ukládání: {str(e)}")
            return False
    
    def save_changes_button_click_handler(self):
        """Handle save button click - save all changes"""
        success = self.save_all_changes(refresh_model=True)
        if success:
            self.loc_table_view.clearSelection()
            self.table_data_modified = False
            self.detail_data_modified = False
            #QMessageBox.information(self, "Uloženo", "Data byla úspěšně uložena.")

    def add_new_location(self):
        # Generování unikátního KOD
        kod_value = self.generate_unique_kod()
        profil_value = "Nový PROFIL"
        tok_value = "Nový TOK"

        # Použití QSqlQuery pro práci s databází přes QSqlDatabase
        query = QSqlQuery(self.db)
        query.prepare("""
            INSERT INTO loc (KOD, PROFIL, TOK, WGS84_LAT, WGS84_LON, STRAHLER, MNM, PLOCHA_POV, KM_OD_PRAM, SLOPE, UMORI)
            VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
        """)
        query.addBindValue(kod_value)
        query.addBindValue(profil_value)
        query.addBindValue(tok_value)

        if not query.exec():
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se přidat novou lokalitu: {query.lastError().text()}")
            return

        # Obnovení zobrazení tabulky a nastavení výběru na novou lokalitu
        self.loc_model.select()  # Refresh levého pohledu
        for row in range(self.loc_model.rowCount()):
            if self.loc_model.record(row).value("KOD") == kod_value:
                proxy_index = self.loc_proxy_model.mapFromSource(self.loc_model.index(row, 1))
                self.loc_table_view.selectRow(proxy_index.row())
                break

    def generate_unique_kod(self):
        base_kod = "New_Loc"
        index = 1
        kod = f"{base_kod}_{index}"

        while any(self.loc_model.record(row).value("KOD") == kod for row in range(self.loc_model.rowCount())):
            index += 1
            kod = f"{base_kod}_{index}"

        return kod

    def import_locations_from_csv(self):
        """Import lokalit z CSV - viz menu Import."""
        self.importuj_csv("lokality")

    def delete_selected_locations(self):
        selected_rows = self.loc_table_view.selectionModel().selectedRows()
        count = len(selected_rows)
        if count == 0:
            QMessageBox.information(self, "Žádný výběr", "Nejsou vybrány žádné lokality ke smazání.")
            return

        reply = QMessageBox.question(
            self,
            "Potvrzení smazání",
            f"Opravdu chcete smazat {count} lokalit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Use Qt database connection instead of separate sqlite3 connection
        success_count = 0
        failed_deletions = []
        
        # Start transaction
        self.db.transaction()
        
        try:
            for index in selected_rows:
                source_index = self.loc_proxy_model.mapToSource(index)
                kod = self.loc_model.record(source_index.row()).value("KOD")
                
                # Use QSqlQuery with the existing Qt database connection
                query = QSqlQuery(self.db)
                query.prepare("DELETE FROM loc WHERE KOD = ?")
                query.addBindValue(kod)
                
                if query.exec():
                    success_count += 1
                else:
                    failed_deletions.append(f"{kod}: {query.lastError().text()}")
            
            if failed_deletions:
                self.db.rollback()
                QMessageBox.critical(self, "Chyba při mazání", 
                                f"Nepodařilo se smazat některé lokality:\n" + "\n".join(failed_deletions))
                return
            else:
                self.db.commit()
                QMessageBox.information(self, "Úspěch", f"Úspěšně smazáno {success_count} lokalit.")
            
        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Chyba při mazání", f"Nepodařilo se smazat lokality: {str(e)}")
            return

        # Simple refresh - this should work now that we're using the same connection
        self.loc_model.select()
        
        # Clear selection and detail view
        self.loc_table_view.clearSelection()
        self.loc_detail_model.clear()
        self.loc_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
        
        # Clear the current_kod attribute if it exists
        if hasattr(self, 'current_kod'):
            delattr(self, 'current_kod')

    def initTab2(self):
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # Levá část - tabulka s názvem "Přehled vzorků"
        left_layout = QVBoxLayout()
        left_label = QLabel("Přehled vzorků")
        left_layout.addWidget(left_label)

        # Use QSqlQueryModel for filtering
        self.samples_model = QSqlQueryModel(self)
        self.samples_table_view = QTableView()
        self.samples_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.samples_table_view.setAlternatingRowColors(True)
        self.samples_table_view.verticalHeader().setVisible(False)
        self.samples_table_view.clicked.connect(self.load_sample_details)
        # Selection change signal for sample selection (will be set after model is applied)

        # Nové sloupce a hlavičky
        visible_columns = [1, 2, 3, 4, 5, 8, 9]
        headers = ["SAMPLE_ID", "TYP", "INTERMITTENT", "DATE", "LOC_ID", "TOK", "PROFIL"]

        # Filtrovací řádek pro vzorky
        filter_widget = RadekFiltru(
            self.samples_table_view, visible_columns, headers)
        filter_widget.zmenen.connect(self.apply_sample_filter)
        self.samples_filters = filter_widget

        stacked_layout = QVBoxLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        stacked_layout.addWidget(filter_widget)
        stacked_layout.addWidget(self.samples_table_view, 1)

        stacked_container = QWidget()
        stacked_container.setLayout(stacked_layout)
        left_layout.addWidget(stacked_container, 1)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Pravá část - detail vzorku
        right_layout = QVBoxLayout()
        right_label = QLabel("Detail vzorku")
        right_layout.addWidget(right_label)

        self.samples_detail_model = QStandardItemModel(self)
        self.samples_detail_model.setHorizontalHeaderLabels(["Taxon / parametr", "Hodnota"])
        self.samples_detail_table_view = QTableView()
        self.samples_detail_table_view.setModel(self.samples_detail_model)
        # Set resize modes and fixed width for columns after setting the model
        self.samples_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.samples_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.samples_detail_table_view.setColumnWidth(1, 80)
        self.samples_detail_table_view.setAlternatingRowColors(True)
        self.samples_detail_table_view.verticalHeader().setVisible(False)
        # Connect dataChanged to track modifications in sample detail
        self.samples_detail_model.dataChanged.connect(lambda: setattr(self, 'samples_detail_data_modified', True))

        self.samples_detail_table_view.setMinimumHeight(200)

        # Faktor 1 dá tabulce všechen volný prostor, takže sahá až
        # k tlačítkům pod ní. Bez něj by si vzala jen svou přirozenou
        # výšku a zbytek by zůstal prázdný.
        right_layout.addWidget(self.samples_detail_table_view, 1)

        # Layout for sample buttons (delete, import, export)
        sample_button_layout = QVBoxLayout()

        # Remove "Uložit změny" and "Přidat vzorek" buttons if present
        # (do not add them)

        # --- Úprava obsahu vzorku ---
        self.edit_sample_button = QPushButton("Upravit vzorek")
        self.edit_sample_button.setToolTip(
            "Otevře okno, ve kterém jdou přepsat názvy taxonů a jejich "
            "hodnoty, přidat nebo odebrat řádky.")
        self.edit_sample_button.clicked.connect(self.uprav_vzorek)
        sample_button_layout.addWidget(self.edit_sample_button)

        # --- Add Delete Samples Button ---
        delete_samples_button = QPushButton("Smazat vzorek")
        delete_samples_button.clicked.connect(self.delete_selected_samples)
        sample_button_layout.addWidget(delete_samples_button)

        # Přidání tlačítka pro import vzorků z CSV
        self.import_samples_button = QPushButton("Načíst vzorky z csv")
        self.import_samples_button.clicked.connect(self.import_samples_from_csv)
        sample_button_layout.addWidget(self.import_samples_button)

        # --- Add Export Samples Button ---
        export_samples_button = QPushButton("Exportovat vzorky")
        export_samples_button.clicked.connect(self.exportuj_vzorky)
        sample_button_layout.addWidget(export_samples_button)

        # Tlačítka jsou pod tabulkou a drží se u spodního okraje. Volný
        # prostor si bere tabulka (faktor 1 výše), ne mezera pod tlačítky -
        # proto tu není žádné addStretch().
        sample_button_layout.setContentsMargins(0, 6, 0, 0)
        right_layout.addLayout(sample_button_layout)

        # Legenda k podbarvení - bez ní není zřejmé, co oranžová znamená.
        legenda = QLabel(
            "Oranžově jsou taxony, které nejsou v taxonomickém seznamu — "
            "do metrik nevstupují."
        )
        legenda.setWordWrap(True)
        legenda.setStyleSheet(
            f"color: #7a4c00; background: {HEX_NEZNAMY};"
            "padding: 4px; border-radius: 3px; font-size: 11px;"
        )
        right_layout.addWidget(legenda)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        right_widget.setFixedWidth(450)  # Nastavení pevné šířky pravého widgetu

        # Přidání widgetů do splitteru
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        # Set explicit initial sizes for the splitter after event loop starts
        QTimer.singleShot(0, lambda: splitter.setSizes([400, 500]))

        # Přidání splitteru do hlavního layoutu
        main_layout.addWidget(splitter)
        self.tab2.setLayout(main_layout)

        # Inicializace zobrazení vzorků s filtrem
        self.apply_sample_filter()
        # Connect selection change signal for sample selection
        self.samples_table_view.selectionModel().currentRowChanged.connect(self.on_sample_selection_changed)

    def uprav_vzorek(self):
        """Otevře okno pro úpravu taxonů a hodnot vybraného vzorku."""
        from editor_vzorku import EditorVzorku

        index = self.samples_table_view.currentIndex()
        if not index.isValid():
            QMessageBox.information(
                self, "Úprava vzorku",
                "Nejdřív vyberte vzorek v tabulce vlevo.")
            return

        zaznam = self.samples_model.record(index.row())
        sample_id = zaznam.value("SAMPLE_ID")
        typ = zaznam.value("TYP")
        if not sample_id:
            return

        # Taxalist podle složky - podle něj se pozná neznámý taxon.
        # U chemických vzorků se název neověřuje, jsou to kódy parametrů.
        taxalist = TAXALIST_SLOZKY.get(typ)
        if taxalist:
            taxalist = nazev_tabulky(self.db, taxalist)

        dialog = EditorVzorku(self.db, sample_id, taxalist, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Detail vlevo ukazuje tatáž data, po zápisu je nutné ho
            # načíst znovu - jinak by zobrazoval starý stav.
            self.load_sample_details(index)

    def export_samples_placeholder(self):
        """Ponechano kvuli zpetne kompatibilite; presmerovava na export."""
        self.exportuj_vzorky()

    def exportuj_vzorky(self):
        """Export vzorku - seznam podle filtru, nebo vcetne taxonu."""
        self._export_dialog(
            "Export vzorků", export_csv.EXPORTY_VZORKU,
            {"seznam": self._export_seznamu_vzorku})

    def exportuj_vysledky(self):
        """Export vysledku - souhrn, vsechny metriky, nebo rocni."""
        self._export_dialog("Export výsledků", export_csv.EXPORTY_VYSLEDKU, {})

    def _export_seznamu_vzorku(self, cesta):
        """Zapise to, co je prave videt v tabulce vzorku, vcetne filtru."""
        return export_csv.exportuj_model(
            self.samples_model, cesta,
            sloupce=[1, 2, 3, 4, 5, 7, 8],
            hlavicky=["SAMPLE_ID", "TYP", "INTERMITTENT", "DATE",
                      "LOC_ID", "TOK", "PROFIL"])

    def _export_dialog(self, titulek, nabidka, vlastni):
        """Necha uzivatele vybrat sestavu, misto ulozeni a zapise CSV.

        Args:
            nabidka: {klic: PopisExportu}
            vlastni: {klic: funkce(cesta) -> pocet radku} pro sestavy,
                ktere nejdou vyjadrit dotazem (typicky export modelu
                vcetne filtru)
        """
        klice = list(nabidka)
        polozky = [f"{nabidka[k].nazev} — {nabidka[k].popis}" for k in klice]
        volba, potvrzeno = QInputDialog.getItem(
            self, titulek, "Co exportovat?", polozky, 0, False)
        if not potvrzeno:
            return
        klic = klice[polozky.index(volba)]
        popis = nabidka[klic]

        cesta, _ = QFileDialog.getSaveFileName(
            self, titulek,
            os.path.join(os.path.expanduser("~"), popis.soubor),
            "CSV (*.csv)")
        if not cesta:
            return

        try:
            if klic in vlastni:
                pocet = vlastni[klic](cesta)
            else:
                pocet = export_csv.exportuj_dotaz(self.db, popis.sql, cesta)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, titulek, f"Export se nezdařil:\n{e}")
            return

        if not pocet:
            QMessageBox.information(
                self, titulek,
                "Export proběhl, ale nebyl co uložit — dotaz nevrátil "
                "žádné řádky.")
            return
        QMessageBox.information(
            self, titulek,
            f"Uloženo {pocet} řádků do:\n{cesta}\n\n"
            "Soubor je v kódování UTF-8 se středníkem jako oddělovačem. "
            "Desetinný oddělovač je tečka — při otevírání v Excelu to "
            "potvrďte, jinak se čísla načtou jako text.")

    def import_samples_from_csv(self):
        """Import vzorku z CSV - viz menu Import."""
        self.importuj_csv("vzorky")

    def apply_sample_filter(self):
        filters = []
        visible_columns = [1, 2, 3, 4, 5, 7, 8]
        headers = ["SAMPLE_ID", "TYP", "INTERMITTENT", "DATE", "LOC_ID", "TOK", "PROFIL"]
        for i, text in enumerate(self.samples_filters.texty()):
            if text:
                # Apostrof by dotaz rozbil - zdvojením se z něj stane
                # obyčejný znak.
                bezpecny = text.replace("'", "''")
                filters.append(f"{headers[i]} LIKE '%{bezpecny}%'")
        where_clause = " AND ".join(filters)
        # Upravený dotaz s LEFT JOIN loc
        query = """
            SELECT samples.*, loc.TOK AS TOK_NAME, loc.PROFIL AS PROFIL_NAME
            FROM samples
            LEFT JOIN loc ON samples.LOC_ID = loc.KOD
        """
        if where_clause:
            query += f" WHERE {where_clause}"
        self.samples_model.setQuery(query, self.db)
        self.samples_table_view.setModel(self.samples_model)
        # Nastavit šířky sloupců automaticky
        self.samples_table_view.resizeColumnsToContents()
        # Stretch last column (PROFIL)
        self.samples_table_view.horizontalHeader().setStretchLastSection(True)
        # Hide columns not in visible_columns
        total_columns = self.samples_model.columnCount()
        for col in range(total_columns):
            if col not in visible_columns:
                self.samples_table_view.setColumnHidden(col, True)
            else:
                self.samples_table_view.setColumnHidden(col, False)
        # Set headers if results exist
        for idx, header in enumerate(headers):
            self.samples_model.setHeaderData(visible_columns[idx], Qt.Orientation.Horizontal, header)
        # Šířky filtrovacích polí si RadekFiltru srovná sám podle
        # sloupců; po výměně modelu je potřeba ho jen pobídnout.
        self.samples_filters.sloupce = list(visible_columns)
        self.samples_filters._srovnej()

    def load_sample_details(self, index):
        sample_id = self.samples_model.record(index.row()).value("SAMPLE_ID")
        sample_typ = self.samples_model.record(index.row()).value("TYP")

        if sample_typ not in TAXALIST_SLOZKY and sample_typ != "CHEM":
            QMessageBox.warning(self, "Chyba", "Neznámý typ vzorku!")
            return

        # Apostrof v kodu vzorku by dotaz rozbil - zdvojenim se z nej
        # stane obycejny znak.
        kod = str(sample_id).replace("'", "''")

        if sample_typ == "CHEM":
            # LEFT JOIN, ne INNER - jinak by kod, ktery ciselnik nezna,
            # ze seznamu tise zmizel misto toho, aby se zvyraznil.
            query_text = f"""
                SELECT COALESCE(c.descript, d.name) AS nazev, d.val,
                       CASE WHEN c.KOD IS NULL THEN 1 ELSE 0 END AS nezname
                FROM data d
                LEFT JOIN taxalist_chem c ON c.KOD = d.name
                WHERE d.sample = '{kod}'
            """
        else:
            taxalist = TAXALIST_SLOZKY[sample_typ]
            query_text = f"""
                SELECT d.name, d.val,
                       CASE WHEN t.NAME IS NULL THEN 1 ELSE 0 END AS nezname
                FROM data d
                LEFT JOIN {taxalist} t ON t.NAME = d.name
                WHERE d.sample = '{kod}'
            """

        model = ModelDetailuVzorku(self)
        model.setQuery(query_text, self.db)
        model.setHeaderData(0, Qt.Orientation.Horizontal, "Taxon / parametr")
        model.setHeaderData(1, Qt.Orientation.Horizontal, "Hodnota")
        self.samples_detail_table_view.setModel(model)

        # Nastavení hlaviček a úířek znovu po přiřazení nového modelu
        self.samples_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.samples_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.samples_detail_table_view.setColumnWidth(1, 80)
        # Priznak "nezname" je jen pro obarveni, uzivateli se neukazuje.
        self.samples_detail_table_view.setColumnHidden(2, True)

        # Store the sample ID for later use
        self.sample_id = sample_id

    def on_sample_selection_changed(self, current, previous):
        """Handle sample selection changes with unsaved data check"""
        if not current.isValid():
            return

        if getattr(self, '_changing_sample_selection', False):
            return

        if getattr(self, 'samples_detail_data_modified', False):
            self._changing_sample_selection = True
            try:
                reply = QMessageBox.question(
                    self,
                    "Neuložené změny",
                    "Máte neuložené změny ve vzorku. Chcete je uložit?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self.save_samples_changes()
                elif reply == QMessageBox.StandardButton.Cancel:
                    self.samples_table_view.selectionModel().blockSignals(True)
                    if previous.isValid():
                        self.samples_table_view.selectionModel().setCurrentIndex(
                            previous,
                            self.samples_table_view.selectionModel().SelectionFlag.SelectCurrent
                        )
                    self.samples_table_view.selectionModel().blockSignals(False)
                    return
                else:
                    self.samples_detail_data_modified = False
            finally:
                self._changing_sample_selection = False

        self.load_sample_details(current)

    def save_samples_changes(self):
        """Uložení ručních úprav v detailu vzorku.

        Zatím neimplementováno. Detail vzorku (`samples_detail_table_view`)
        zobrazuje seznam taxonů přes QSqlQueryModel, který je jen ke čtení;
        editace jednotlivých záznamů bude řešena zvlášť.

        Původní verze této metody byla nefunkční hned v několika ohledech
        a mohla poškodit data, proto byla odstraněna:

          * otevírala si vlastní spojení na natvrdo zapsanou cestu
            "dtb/LULAN_dtb_001.db" - obcházela tím pracovní kopii databáze
            i volbu jiného souboru, a při jiném pracovním adresáři si
            vyrobila prázdnou databázi
          * všechny hodnoty převáděla na float, takže SAMPLE_ID, LOC_ID,
            TYP i DATE by se do databáze zapsaly jako NULL
          * podmínka `WHERE KOD = ?` odkazovala na sloupec, který tabulka
            `samples` nemá (sloupce jsou ID, SAMPLE_ID, TYP, INTERMITTENT,
            DATE, LOC_ID, DTCH)
          * volala `self.save_samples_changes_button`, který se nikde
            nevytváří - metoda tedy spadla na AttributeError dřív,
            než k zápisu vůbec došlo
        """
        self.samples_detail_data_modified = False
        QMessageBox.information(
            self, "Zatím nedostupné",
            "Úpravy záznamů vzorku zatím nejsou implementované.\n\n"
            "Data vzorku lze upravit v tabulce vzorků nebo importem z CSV.",
        )

    def add_new_sample(self):
        # Generování unikátního KOD
        id_value = self.generate_unique_kod_sample()
        sample_id_value = ""
        loc_id_value = ""
        typ_value = ""
        int_value = ""
        date_value = ""
        dtch_value = datetime.datetime.now()

        # Použití QSqlQuery pro práci s databází přes QSqlDatabase
        query = QSqlQuery(self.db)
        query.prepare("""
            INSERT INTO samples (ID, SAMPLE_ID, TYP, INTERMITTENT, DATE, LOC_ID, DTCH)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """)
        query.addBindValue(id_value)
        query.addBindValue(sample_id_value)
        query.addBindValue(typ_value)
        query.addBindValue(int_value)
        query.addBindValue(date_value)
        query.addBindValue(loc_id_value)
        query.addBindValue(dtch_value)
        

        if not query.exec():
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se přidat nový vzorek: {query.lastError().text()}")
            return

        # Obnovení zobrazení tabulky a nastavení výběru na nový vzorek.
        # samples_model je QSqlQueryModel, takže se obnovuje znovuspuštěním
        # dotazu, ne select() (ten na něm neexistuje).
        self.apply_sample_filter()
        for row in range(self.samples_model.rowCount()):
            if self.samples_model.record(row).value("ID") == id_value:
                self.samples_table_view.selectRow(row)
                break
    
    def delete_selected_samples(self):
        selected_indexes = self.samples_table_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(self, "Info", "Nevybrán žádný vzorek ke smazání.")
            return

        # column 1 is SAMPLE_ID
        sample_ids = [self.samples_model.index(index.row(), 1).data() for index in selected_indexes]

        confirm = QMessageBox.question(self, "Potvrzení",
                                       f"Opravdu chcete smazat {len(sample_ids)} vzorků?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        query = QSqlQuery(self.db)
        for sample_id in sample_ids:
            query.prepare("DELETE FROM data WHERE SAMPLE = ?")
            query.addBindValue(sample_id)
            query.exec()

            query.prepare("DELETE FROM samples WHERE SAMPLE_ID = ?")
            query.addBindValue(sample_id)
            query.exec()

        self.apply_sample_filter()

    def generate_unique_kod_sample(self):
        index = 11000001
        kod = f"{index}"

        while any(self.samples_model.record(row).value("SAMPLE_ID") == kod for row in range(self.samples_model.rowCount())):
            index += 1
            kod = f"{index}"

        return kod

    def initTab3(self):
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # Levá část - tabulka s výběrem typu taxonu
        left_layout = QVBoxLayout()
        
        # Výběr taxonomického seznamu. Názvy tabulek se srovnají
        # s databází, ať na velikosti písmen nezáleží.
        self.taxon_table_selector = PrepinacMoznosti(
            [(popis, nazev_tabulky(self.db, tabulka))
             for popis, tabulka in TAXALISTY_NABIDKA],
            popisek="Taxonomický seznam:",
        )
        self.current_taxon_table = self.taxon_table_selector.hodnota()
        self.taxon_table_selector.zmenen.connect(self.on_taxon_table_changed)
        left_layout.addWidget(self.taxon_table_selector)

        # Label pro přehled
        left_label = QLabel("Přehled taxonů")
        left_layout.addWidget(left_label)

        # Use QSqlTableModel for editing + custom filter method
        self.taxon_model = ModelTaxalistu(self, self.db)
        self.taxon_model.setTable(self.current_taxon_table)
        self.taxon_model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        self.taxon_model.dataChanged.connect(self.on_taxon_table_data_changed)
        self.taxon_model.select()
        
        self.taxon_table_view = QTableView()
        self.taxon_table_view.setModel(self.taxon_model)
        self.taxon_table_view.verticalHeader().setVisible(False)
        self.taxon_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.taxon_table_view.setAlternatingRowColors(True)
        
        # Enable editing
        self.taxon_table_view.setEditTriggers(QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.EditKeyPressed)
        
        # Simple click handler for loading details
        self.taxon_table_view.selectionModel().currentRowChanged.connect(self.on_taxon_selection_changed)

        # Skutečné pozice, popisky a názvy sloupců doplní
        # setup_taxon_columns() podle toho, co daný taxalist opravdu má.
        self.taxon_visible_columns = [1, 2, 3, 4, 5]
        self.taxon_headers = [p for p, _ in SLOUPCE_PREHLEDU]
        self.taxon_filter_columns = [v[0] for _, v in SLOUPCE_PREHLEDU]

        # Filtrovací řádek. Sloupce se dopočítají v setup_taxon_columns(),
        # do té doby platí pořadí ze SLOUPCE_PREHLEDU.
        filter_widget = RadekFiltru(
            self.taxon_table_view, self.taxon_visible_columns,
            self.taxon_headers)
        filter_widget.zmenen.connect(self.apply_taxon_filter)
        self.taxon_filters = filter_widget

        # Stacked layout for filters and table
        stacked_layout = QVBoxLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        stacked_layout.addWidget(filter_widget)
        # Faktor 1 dá tabulce všechen volný prostor, takže se protáhne
        # až ke spodnímu okraji okna a zobrazí co nejvíc řádků.
        stacked_layout.addWidget(self.taxon_table_view, 1)

        stacked_container = QWidget()
        stacked_container.setLayout(stacked_layout)
        left_layout.addWidget(stacked_container, 1)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Pravá část - detail taxonu. Nahoře prázdné místo o výšce
        # přepínače, aby detail začínal ve stejné výšce jako tabulka vlevo.
        right_layout = QVBoxLayout()
        odsazeni = QWidget()
        odsazeni.setFixedHeight(self.taxon_table_selector.sizeHint().height())
        right_layout.addWidget(odsazeni)

        zahlavi_detailu = QHBoxLayout()
        zahlavi_detailu.setContentsMargins(0, 0, 0, 0)
        zahlavi_detailu.addWidget(QLabel("Detail taxonu"))
        zahlavi_detailu.addStretch(1)
        zahlavi_detailu_widget = QWidget()
        zahlavi_detailu_widget.setLayout(zahlavi_detailu)
        zahlavi_detailu_widget.setFixedHeight(VYSKA_ZAHLAVI)
        right_layout.addWidget(zahlavi_detailu_widget)

        self.taxon_detail_model = QStandardItemModel(0, 2)
        self.taxon_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
        
        # Connect to data changed signal to track modifications
        self.taxon_detail_model.dataChanged.connect(self.on_taxon_detail_data_changed)
        
        self.taxon_detail_table_view = QTableView()
        self.taxon_detail_table_view.setModel(self.taxon_detail_model)
        self.taxon_detail_table_view.verticalHeader().setVisible(False)
        self.taxon_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.taxon_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.taxon_detail_table_view.setAlternatingRowColors(True)
        self.taxon_detail_table_view.setColumnWidth(1, 100)

        self.taxon_detail_table_view.setMinimumHeight(200)
        # Faktor 1: detail si vezme všechen volný prostor a sahá až
        # k tlačítku pod ním.
        right_layout.addWidget(self.taxon_detail_table_view, 1)

        # Save button
        self.save_taxon_changes_button = QPushButton("Uložit změny")
        self.save_taxon_changes_button.clicked.connect(self.save_taxon_changes_button_click_handler)
        right_layout.addWidget(self.save_taxon_changes_button)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        # Popisy vlastností jsou dlouhé věty ("Ellenbergovy indikační
        # hodnoty pro živiny…"), proto širší panel než dřív.
        right_widget.setFixedWidth(460)

        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([750, 460])

        main_layout.addWidget(splitter)
        self.tab3.setLayout(main_layout)

        # Initialize flags
        self.taxon_table_data_modified = False
        self.taxon_detail_data_modified = False
        self.current_taxon_id = None
        self._changing_taxon_selection = False

        # Setup initial table
        self.setup_taxon_columns()
        self.apply_taxon_filter()

    def pouzij_filtr_lokalit(self):
        """Filtruje lokality podle všech vyplněných polí naráz."""
        self._filtruj_pohled(
            self.loc_table_view, self.loc_proxy_model, self.loc_model,
            self.loc_filters)

    def _filtruj_pohled(self, pohled, proxy, model, filtry):
        """Skryje řádky, které neodpovídají všem vyplněným polím.

        `QSortFilterProxyModel` porovnává jen jeden sloupec, proto se
        filtruje ručně přes všechny naráz.

        Model se nejdřív dočte do konce. Řádky totiž chodí po dávkách
        po 256 a `rowCount()` zná jen ty už načtené — filtr proto dřív
        procházel jen začátek tabulky a hledaný záznam se objevil až
        ve chvíli, kdy k němu uživatel doroloval. Tabulky lokalit
        a útvarů mají stovky řádků, takže je načtení celé levné.

        Taxony tímhle neduhem netrpí, protože filtrují v databázi
        (`setFilter()`); tady se filtruje nad zobrazenými hodnotami,
        aby u útvarů šlo hledat podle popisků z číselníku a ne podle
        uložených kódů.
        """
        self._docti_model(model)
        podminky = [(sl, t.lower())
                    for sl, t in zip(filtry.sloupce, filtry.texty()) if t]
        for radek in range(proxy.rowCount()):
            if not podminky:
                pohled.setRowHidden(radek, False)
                continue
            zdroj = proxy.mapToSource(proxy.index(radek, 0))
            skryt = any(
                hledany not in str(
                    model.data(model.index(zdroj.row(), sloupec)) or "").lower()
                for sloupec, hledany in podminky)
            pohled.setRowHidden(radek, skryt)

    def pouzij_filtr_utvaru(self):
        """Filtruje útvary podle všech vyplněných polí naráz.

        `QSortFilterProxyModel` umí porovnávat jen jeden sloupec, takže
        se filtruje ručně: řádek projde, jen když každé vyplněné pole
        odpovídá své buňce.
        """
        self._filtruj_pohled(
            self.utvary_table_view, self.utvary_proxy_model,
            self.utvary_model, self.utvary_filters)

    def apply_taxon_filter(self):
        """Apply filters using QSqlTableModel.setFilter() for database-level filtering"""
        filters = []
        headers = getattr(self, "taxon_filter_columns", None) or [
            v[0] for _, v in SLOUPCE_PREHLEDU]

        for i, text in enumerate(self.taxon_filters.texty()):
            if i >= len(headers):
                continue
            if text:
                # Apostrof v hledaném textu by dotaz rozbil - zdvojením
                # se z něj stane obyčejný znak.
                bezpecny = text.replace("'", "''")
                filters.append(f"{headers[i]} LIKE '%{bezpecny}%'")
        
        # Create WHERE clause
        where_clause = " AND ".join(filters) if filters else ""
        
        # Apply filter to model - this filters at DATABASE level
        self.taxon_model.setFilter(where_clause)
        
        # Setup columns after filtering
        self.setup_taxon_columns()

    def setup_taxon_columns(self):
        """Set up visible columns and headers for taxon table - handle different column orders"""
        # Get all field names from the current table to find column positions
        current_table = self.taxon_table_selector.hodnota()
        table_info_query = QSqlQuery(self.db)
        table_info_query.exec(f"PRAGMA table_info({current_table})")
        
        field_positions = {}
        while table_info_query.next():
            col_index = table_info_query.value(0)  # Column index
            col_name = table_info_query.value(1)   # Column name
            field_positions[col_name] = col_index
        
        # Sloupce přehledu. Autor se napříč taxalisty jmenuje jednou
        # AUTOR (MZB, FB) a jednou AUTHOR (MF, RYBY), proto se u každého
        # sloupce zkouší víc názvů - viz SLOUPCE_PREHLEDU.
        actual_visible_columns, popisky, nazvy = [], [], []
        for popisek, varianty in SLOUPCE_PREHLEDU:
            for nazev in varianty:
                if nazev in field_positions:
                    actual_visible_columns.append(field_positions[nazev])
                    popisky.append(popisek)
                    nazvy.append(nazev)
                    break
            else:
                print(f"[taxony] {current_table}: sloupec {popisek} "
                      f"({' / '.join(varianty)}) v tabulce není")

        # Update the visible columns list
        self.taxon_visible_columns = actual_visible_columns
        self.taxon_headers = popisky
        # Filtr musí dotazovat skutečný název sloupce, ne popisek.
        self.taxon_filter_columns = nazvy
        if hasattr(self, "taxon_filters"):
            self.taxon_filters.sloupce = list(actual_visible_columns)
            self.taxon_filters._srovnej()

        # Set headers for the actual column positions
        for idx, col_position in enumerate(actual_visible_columns):
            self.taxon_model.setHeaderData(
                col_position, Qt.Orientation.Horizontal, popisky[idx])
        
        # Hide columns not in visible_columns
        total_columns = self.taxon_model.columnCount()
        for col in range(total_columns):
            if col not in actual_visible_columns:
                self.taxon_table_view.setColumnHidden(col, True)
            else:
                self.taxon_table_view.setColumnHidden(col, False)
        
        # Set column widths - NAME column should stretch
        self.taxon_table_view.resizeColumnsToContents()
        
        # Šířky sloupců. Jméno taxonu bývalo roztažené přes celý zbytek
        # tabulky, zatímco rodič a autor se mačkali na 80 px. Teď má
        # každý sloupec šířku podle toho, co v něm reálně bývá:
        # nejdelší jméno má kolem 65 znaků, rodič a autor jsou delší
        # než 80 px skoro vždycky. Poslední sloupec (platné jméno) si
        # bere zbytek šířky.
        header = self.taxon_table_view.horizontalHeader()
        header.setStretchLastSection(True)
        for popisek, col_position in zip(popisky, actual_visible_columns):
            header.setSectionResizeMode(
                col_position, QHeaderView.ResizeMode.Interactive)
            self.taxon_table_view.setColumnWidth(
                col_position, SIRKY_SLOUPCU_TAXONU.get(popisek, 120))

    def on_taxon_table_data_changed(self):
        """Track when main taxon table data is modified"""
        self.taxon_table_data_modified = True

    def on_taxon_detail_data_changed(self):
        """Track when taxon detail data is modified"""
        self.taxon_detail_data_modified = True

    def load_taxon_details(self, index):
        """Load taxon details with improved error handling"""
        try:
            record = self.taxon_model.record(index.row())
            taxon_id = record.value("ID")
            
            # Get current table name
            current_table = self.taxon_table_selector.hodnota()

            # Query all fields for this taxon
            query = QSqlQuery(self.db)
            query.prepare(f"SELECT * FROM {current_table} WHERE ID = ?")
            query.addBindValue(taxon_id)
            
            if not query.exec():
                QMessageBox.warning(self, "Chyba", f"Nepodařilo se načíst detaily: {query.lastError().text()}")
                return
                
            if not query.next():
                QMessageBox.warning(self, "Chyba", f"Nepodařilo se načíst detaily pro taxon s ID: {taxon_id}")
                return

            # Get field names from the table
            table_info_query = QSqlQuery(self.db)
            table_info_query.exec(f"PRAGMA table_info({current_table})")
            
            field_names = []
            while table_info_query.next():
                field_names.append(table_info_query.value(1))  # Column name is at index 1
            
            # Sloupce, které do detailu nepatří: buď už jsou vidět
            # v řádkovém přehledu vlevo (jméno, autor, synonymum), nebo
            # jde o vnitřní identifikátory, se kterými uživatel nepracuje.
            # Detail tak zůstane jen pro autekologické charakteristiky.
            visible_fields = SLOUPCE_MIMO_TRAITY
            
            # Disconnect the dataChanged signal temporarily to avoid triggering during loading
            self.taxon_detail_model.dataChanged.disconnect()
            
            try:
                # Clear model and load new values
                self.taxon_detail_model.clear()
                self.taxon_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
                
                # Reset query to beginning
                query.first()
                
                for i, field_name in enumerate(field_names):
                    if field_name.upper() in visible_fields:
                        continue
                    field_value = query.value(i)
                    # Popisek je český název charakteristiky, zkratka
                    # zůstává v závorce - podle ní se hledá v metodikách.
                    label_item = QStandardItem(
                        ciselnik_traits.PREKLADAC.popisek(
                            field_name, current_table))
                    label_item.setEditable(False)
                    # Zkratka se schová do dat řádku, aby při ukládání
                    # bylo jasné, který sloupec se mění.
                    label_item.setData(field_name, Qt.ItemDataRole.UserRole)
                    value_item = QStandardItem(
                        str(field_value) if field_value is not None else "")
                    value_item.setEditable(True)
                    self.taxon_detail_model.appendRow([label_item, value_item])
                        
            finally:
                # Reconnect the signal and reset modification flag
                self.taxon_detail_model.dataChanged.connect(self.on_taxon_detail_data_changed)
                self.taxon_detail_data_modified = False

            # Store current taxon ID for saving changes
            self.current_taxon_id = taxon_id

            # Set column widths
            self.taxon_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.taxon_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.taxon_detail_table_view.setColumnWidth(1, 100)
            
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Neočekávaná chyba při načítání detailů taxonu: {str(e)}")
            # Reconnect signal if it was disconnected
            try:
                self.taxon_detail_model.dataChanged.connect(self.on_taxon_detail_data_changed)
            except TypeError:
                pass  # signál už může být připojený

    def on_taxon_table_changed(self):
        """Handle taxon table selection change"""
        if self.has_unsaved_taxon_changes():
            reply = QMessageBox.question(
                self,
                "Neuložené změny",
                "Máte neuložené změny. Chcete je uložit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if not self.save_all_taxon_changes():
                    # Revert combo box selection
                    self._vrat_vyber_taxalistu()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                # Revert combo box selection
                self._vrat_vyber_taxalistu()
                return
            else:
                # Discard changes
                self.discard_all_taxon_changes()
        
        # Update current table
        self.current_taxon_table = self.taxon_table_selector.hodnota()
        
        # Clear filters
        self.taxon_filters.vycisti()
        
        # Reset flags
        self.taxon_table_data_modified = False
        self.taxon_detail_data_modified = False
        self.current_taxon_id = None
        
        # Clear detail view
        self.taxon_detail_model.clear()
        self.taxon_detail_model.setHorizontalHeaderLabels(["Popis", "Hodnota"])
        
        # Switch to new table
        self.taxon_model.setTable(self.current_taxon_table)
        self.taxon_model.select()
        self.setup_taxon_columns()
        self.apply_taxon_filter()

    def _vrat_vyber_taxalistu(self):
        """Vrátí přepínač na seznam, který je právě načtený.

        Volá se, když uživatel výběr zruší nebo se uložení nezdaří -
        combo už je přepnuté, ale data se nezměnila, takže by si obojí
        neodpovídalo.
        """
        self.taxon_table_selector.nastav(self.current_taxon_table)

    def has_unsaved_taxon_changes(self):
        """Check if there are any unsaved taxon changes"""
        return (hasattr(self, 'taxon_table_data_modified') and self.taxon_table_data_modified) or \
            (hasattr(self, 'taxon_detail_data_modified') and self.taxon_detail_data_modified)

    def on_taxon_selection_changed(self, current, previous):
        """Handle taxon selection changes with proper unsaved data checking"""
        if not current.isValid():
            return
        
        # Prevent recursive calls
        if hasattr(self, '_changing_taxon_selection') and self._changing_taxon_selection:
            return
            
        # Check if there are unsaved changes
        if self.has_unsaved_taxon_changes():
            # Set flag to prevent recursive calls
            self._changing_taxon_selection = True
            
            try:
                changes_text = []
                if hasattr(self, 'taxon_table_data_modified') and self.taxon_table_data_modified:
                    changes_text.append("v hlavní tabulce")
                if hasattr(self, 'taxon_detail_data_modified') and self.taxon_detail_data_modified:
                    changes_text.append("v detailech taxonu")
                
                changes_description = " a ".join(changes_text)
                
                reply = QMessageBox.question(
                    self,
                    "Neuložené změny",
                    f"Máte neuložené změny {changes_description}. Chcete je uložit?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Save changes
                    QTimer.singleShot(0, lambda: self.save_all_taxon_changes(refresh_model=False))
                    return
                elif reply == QMessageBox.StandardButton.Cancel:
                    # Revert selection
                    self.taxon_table_view.selectionModel().blockSignals(True)
                    if previous.isValid():
                        self.taxon_table_view.selectionModel().setCurrentIndex(previous, 
                            self.taxon_table_view.selectionModel().SelectionFlag.SelectCurrent)
                    self.taxon_table_view.selectionModel().blockSignals(False)
                    self._changing_taxon_selection = False
                    return
                else:
                    # Discard changes
                    self.discard_all_taxon_changes()
                
            finally:
                # Always reset the flag
                self._changing_taxon_selection = False
        
        # Load new taxon details
        self.load_taxon_details(current)

    def save_all_taxon_changes(self, refresh_model=True):
        """Save all taxon changes"""
        success = True
        
        # Save main table changes
        if hasattr(self, 'taxon_table_data_modified') and self.taxon_table_data_modified:
            try:
                if not self.taxon_model.submitAll():
                    error_msg = self.taxon_model.lastError().text()
                    QMessageBox.critical(self, "Chyba", f"Nepodařilo se uložit změny v tabulce: {error_msg}")
                    return False
                
                self.taxon_table_data_modified = False
                
            except Exception as e:
                QMessageBox.critical(self, "Chyba", f"Neočekávaná chyba při ukládání tabulky: {str(e)}")
                return False
        
        # Save detail changes if they exist
        if hasattr(self, 'taxon_detail_data_modified') and self.taxon_detail_data_modified:
            success = self.save_taxon_detail_changes(refresh_model=False)
            if not success:
                return False
        
        # Refresh model only if requested and all saves were successful
        if refresh_model and success:
            self.taxon_model.select()
            self.taxon_table_view.clearSelection()
            QMessageBox.information(self, "Úspěch", "Změny byly úspěšně uloženy.")
        
        return success

    def save_taxon_detail_changes(self, refresh_model=True):
        """Uloží ručně upravené hodnoty traitů zpět do taxalistu.

        Název sloupce se bere z dat řádku (`UserRole`), ne z popisku —
        ten je český název charakteristiky, ne jméno sloupce.

        Prázdná hodnota se ukládá jako NULL. U traitů to je významový
        rozdíl: nula znamená "vlastnost taxon nemá", prázdno "nevíme".
        """
        if not getattr(self, "current_taxon_id", None):
            self.taxon_detail_data_modified = False
            return True

        tabulka = self.taxon_table_selector.hodnota()
        zmeny = {}
        for radek in range(self.taxon_detail_model.rowCount()):
            popisek = self.taxon_detail_model.item(radek, 0)
            hodnota = self.taxon_detail_model.item(radek, 1)
            if popisek is None or hodnota is None:
                continue
            sloupec = popisek.data(Qt.ItemDataRole.UserRole)
            if sloupec:
                zmeny[sloupec] = hodnota.text().strip()

        if not zmeny:
            self.taxon_detail_data_modified = False
            return True

        dotaz = QSqlQuery(self.db)
        dotaz.prepare(
            f"UPDATE {tabulka} SET "
            + ", ".join(f"[{s}] = ?" for s in zmeny)
            + " WHERE ID = ?"
        )
        for text in zmeny.values():
            dotaz.addBindValue(text if text != "" else None)
        dotaz.addBindValue(self.current_taxon_id)

        if not dotaz.exec():
            QMessageBox.critical(
                self, "Chyba",
                f"Nepodařilo se uložit vlastnosti taxonu:\n"
                f"{dotaz.lastError().text()}")
            return False

        self.taxon_detail_data_modified = False
        if refresh_model:
            self.taxon_model.select()
        return True

    def discard_all_taxon_changes(self):
        """Discard all unsaved taxon changes"""
        # Discard table changes
        if hasattr(self, 'taxon_table_data_modified') and self.taxon_table_data_modified:
            self.taxon_model.revertAll()
            self.taxon_table_data_modified = False
        
        # Detail changes will be discarded when new data is loaded
        self.taxon_detail_data_modified = False

    def save_taxon_changes_button_click_handler(self):
        """Handle save button click - save all taxon changes"""
        success = self.save_all_taxon_changes(refresh_model=True)
        if success:
            self.taxon_table_view.clearSelection()
            self.taxon_table_data_modified = False
            self.taxon_detail_data_modified = False

    def initTab4(self):
        """Tab Výsledky - s přepínáním mezi vzorky a ročními výsledky"""
        from PyQt6.QtWidgets import QStackedWidget
        
        main_layout = QVBoxLayout()
        
        # Přepínač pohledů
        view_selector_layout = QHBoxLayout()
        view_selector_label = QLabel("Zobrazit:")
        view_selector_layout.addWidget(view_selector_label)
        
        # Hodnotou je index pohledu ve QStackedWidget níže.
        self.results_view_selector = PrepinacMoznosti(
            [("Výsledky vzorků", 0), ("Roční výsledky útvarů", 1)]
        )
        self.results_view_selector.zmenen.connect(
            lambda: self.on_results_view_changed(
                self.results_view_selector.hodnota())
        )
        view_selector_layout.addWidget(self.results_view_selector)
        view_selector_layout.addStretch()
        
        main_layout.addLayout(view_selector_layout)
        
        # Stacked widget
        self.results_stacked_widget = QStackedWidget()
        
        # POHLED 1: Výsledky vzorků
        samples_view_widget = QWidget()
        samples_view_layout = QHBoxLayout()
        splitter_samples = QSplitter()
        
        # Levá část
        left_layout = QVBoxLayout()
        left_label = QLabel("Přehled vzorků")
        left_layout.addWidget(left_label)
        
        self.results_samples_model = QSqlQueryModel(self)
        self.results_samples_table_view = QTableView()
        self.results_samples_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.results_samples_table_view.setAlternatingRowColors(True)
        self.results_samples_table_view.verticalHeader().setVisible(False)
        self.results_samples_table_view.clicked.connect(self.load_results_details)
        
        visible_columns = [1, 2, 3, 4, 5, 8, 9]
        headers = ["SAMPLE_ID", "TYP", "INTERMITTENT", "DATE", "LOC_ID", "TOK", "PROFIL"]
        
        filter_widget = RadekFiltru(
            self.results_samples_table_view, visible_columns, headers)
        filter_widget.zmenen.connect(self.apply_results_sample_filter)
        self.results_samples_filters = filter_widget
        
        stacked_layout = QVBoxLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        stacked_layout.addWidget(filter_widget)
        stacked_layout.addWidget(self.results_samples_table_view, 1)
        
        stacked_container = QWidget()
        stacked_container.setLayout(stacked_layout)
        left_layout.addWidget(stacked_container)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        # Pravá část
        right_layout = QVBoxLayout()
        right_label = QLabel("Výsledky vzorku")
        right_layout.addWidget(right_label)
        
        self.results_detail_model = QStandardItemModel(self)
        self.results_detail_model.setHorizontalHeaderLabels(["Metrika", "Hodnota", "EQR", "Třída"])
        self.results_detail_table_view = QTableView()
        self.results_detail_table_view.setModel(self.results_detail_model)
        
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        
        self.results_detail_table_view.setColumnWidth(1, 80)
        self.results_detail_table_view.setColumnWidth(2, 80)
        self.results_detail_table_view.setColumnWidth(3, 60)
        self.results_detail_table_view.setAlternatingRowColors(True)
        self.results_detail_table_view.verticalHeader().setVisible(False)
        self.results_detail_table_view.setMinimumHeight(200)

        # Faktor 1: přehled výsledků sahá až k tlačítkům pod ním.
        right_layout.addWidget(self.results_detail_table_view, 1)
        
        results_button_layout = QVBoxLayout()
        
        calculate_indexes_button = QPushButton("Výpočet indexů")
        calculate_indexes_button.clicked.connect(self.calculate_indexes)
        calculate_indexes_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        results_button_layout.addWidget(calculate_indexes_button)
        
        export_results_button = QPushButton("Exportovat výsledky")
        export_results_button.clicked.connect(self.exportuj_vysledky)
        results_button_layout.addWidget(export_results_button)
        
        # Tlačítka jsou pod tabulkou; volné místo si bere tabulka
        # (faktor 1 výše), ne mezera pod tlačítky.
        results_button_layout.setContentsMargins(0, 6, 0, 0)
        right_layout.addLayout(results_button_layout)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        right_widget.setFixedWidth(450)
        
        splitter_samples.addWidget(left_widget)
        splitter_samples.addWidget(right_widget)
        QTimer.singleShot(0, lambda: splitter_samples.setSizes([400, 500]))
        
        samples_view_layout.addWidget(splitter_samples)
        samples_view_widget.setLayout(samples_view_layout)
        
        # POHLED 2: Roční výsledky
        yearly_view_widget = QWidget()
        yearly_view_layout = QVBoxLayout()
        
        yearly_label = QLabel("Roční výsledky po vodních útvarech")
        yearly_view_layout.addWidget(yearly_label)
        
        self.results_yearly_model = QStandardItemModel(self)
        self.results_yearly_model.setHorizontalHeaderLabels([
            "Útvar", "Rok",
            "MZB EQR", "MZB Třída",
            "FB EQR", "FB Třída",
            "FP EQR", "FP Třída",
            "MF EQR", "MF Třída",
            "Ryby EQR", "Ryby Třída",
            "Fyzchem"
        ])
        
        self.results_yearly_table_view = QTableView()
        self.results_yearly_table_view.setModel(self.results_yearly_model)
        self.results_yearly_table_view.setAlternatingRowColors(True)
        self.results_yearly_table_view.verticalHeader().setVisible(False)
        self.results_yearly_table_view.setSortingEnabled(True)
        
        self.results_yearly_table_view.setColumnWidth(0, 120)
        self.results_yearly_table_view.setColumnWidth(1, 60)
        for i in range(2, 13):
            if i % 2 == 0:
                self.results_yearly_table_view.setColumnWidth(i, 80)
            else:
                self.results_yearly_table_view.setColumnWidth(i, 70)
        
        yearly_view_layout.addWidget(self.results_yearly_table_view)
        
        refresh_yearly_button = QPushButton("Obnovit roční výsledky")
        refresh_yearly_button.clicked.connect(self.load_yearly_results)
        yearly_view_layout.addWidget(refresh_yearly_button)
        
        yearly_view_widget.setLayout(yearly_view_layout)
        
        self.results_stacked_widget.addWidget(samples_view_widget)
        self.results_stacked_widget.addWidget(yearly_view_widget)
        
        main_layout.addWidget(self.results_stacked_widget)
        self.tab4.setLayout(main_layout)
        
        self.apply_results_sample_filter()
        self.results_samples_table_view.selectionModel().currentRowChanged.connect(
            self.on_results_sample_selection_changed
        )

    def apply_results_sample_filter(self):
        """Apply filters for results samples table (same logic as initTab2)"""
        filters = []
        visible_columns = [1, 2, 3, 4, 5, 7, 8]
        headers = ["SAMPLE_ID", "TYP", "INTERMITTENT", "DATE", "LOC_ID", "TOK", "PROFIL"]
        for i, text in enumerate(self.results_samples_filters.texty()):
            if text:
                bezpecny = text.replace("'", "''")
                filters.append(f"{headers[i]} LIKE '%{bezpecny}%'")
        where_clause = " AND ".join(filters)
        # Same query as initTab2 with LEFT JOIN loc
        query = """
            SELECT samples.*, loc.TOK AS TOK_NAME, loc.PROFIL AS PROFIL_NAME
            FROM samples
            LEFT JOIN loc ON samples.LOC_ID = loc.KOD
        """
        if where_clause:
            query += f" WHERE {where_clause}"
        self.results_samples_model.setQuery(query, self.db)
        self.results_samples_table_view.setModel(self.results_samples_model)
        # Nastavit šířky sloupců automaticky
        self.results_samples_table_view.resizeColumnsToContents()
        # Stretch last column (PROFIL)
        self.results_samples_table_view.horizontalHeader().setStretchLastSection(True)
        # Hide columns not in visible_columns
        total_columns = self.results_samples_model.columnCount()
        for col in range(total_columns):
            if col not in visible_columns:
                self.results_samples_table_view.setColumnHidden(col, True)
            else:
                self.results_samples_table_view.setColumnHidden(col, False)
        # Set headers if results exist
        for idx, header in enumerate(headers):
            self.results_samples_model.setHeaderData(visible_columns[idx], Qt.Orientation.Horizontal, header)
        # Šířky si RadekFiltru srovná sám podle sloupců tabulky.
        self.results_samples_filters.sloupce = list(visible_columns)
        self.results_samples_filters._srovnej()

    def load_results_details(self, index):
        """Load results details for selected sample - one row per metric with VALUE, EQR, CLASS columns"""
        sample_id = self.results_samples_model.record(index.row()).value("SAMPLE_ID")
        
        # Create a standard item model with 3 columns
        self.results_detail_model = QStandardItemModel(0, 3)
        self.results_detail_model.setHorizontalHeaderLabels(["Metrika", "Hodnota", "EQR", "Třída"])
        
        # Query all results for this sample
        results_query = QSqlQuery(self.db)
        results_query.prepare("""
            SELECT METRIC, VAL, VAL_EQR, CLASS, POZN
            FROM results
            WHERE SAMPLE_ID = ?
            ORDER BY METRIC
        """)
        results_query.addBindValue(sample_id)
        
        if not results_query.exec():
            QMessageBox.warning(self, "Chyba", f"Nepodařilo se načíst výsledky: {results_query.lastError().text()}")
            return
        
        # Process each result row
        row_count = 0
        while results_query.next():
            metric = results_query.value(0)
            val = results_query.value(1)
            val_eqr = results_query.value(2)
            class_val = results_query.value(3)
            pozn = results_query.value(4)

            if ciselnik_metrik.je_zastarala(metric):
                # Zbytek po starší verzi výpočtu; žádná platná metodika
                # takovou metriku nezná.
                continue


            # Název metriky. Kód zůstává v závorce - uživatel podle něj
            # hledá metriku v metodice a v exportech.
            metric_item = QStandardItem(
                ciselnik_metrik.PREKLADAC.popisek(metric)
                if metric is not None else "")
            metric_item.setEditable(False)
            
            # Create value item (VAL column)
            if val is not None:
                if isinstance(val, (int, float)):
                    value_text = f"{val:.3f}" if isinstance(val, float) else str(val)
                else:
                    value_text = str(val)
            else:
                value_text = ""
            value_item = QStandardItem(value_text)
            value_item.setEditable(False)
            
            # Create EQR item (VAL_EQR column)
            if val_eqr is not None:
                if isinstance(val_eqr, (int, float)):
                    eqr_text = f"{val_eqr:.3f}" if isinstance(val_eqr, float) else str(val_eqr)
                else:
                    eqr_text = str(val_eqr)
            else:
                eqr_text = ""
            eqr_item = QStandardItem(eqr_text)
            eqr_item.setEditable(False)
            
            # Create class item (CLASS column) - only for CELKEM metrics
            if class_val is not None and str(class_val).strip() and str(class_val) != "NaN":
                class_text = str(class_val)
            else:
                class_text = ""
            class_item = QStandardItem(class_text)
            class_item.setEditable(False)
            
            # Add conditional color coding for CLASS field based on classification
            if class_text and str(metric).endswith('_CELKEM'):
                
                # Color mapping for classifications
                color_map = {
                    'VD': QColor(0, 100, 255),      # Blue
                    'D': QColor(0, 200, 0),         # Green  
                    'S': QColor(255, 255, 0),       # Yellow
                    'P': QColor(255, 165, 0),       # Orange
                    'Z': QColor(255, 0, 0)          # Red
                }
                
                if class_text in color_map:
                    class_item.setBackground(color_map[class_text])
                    # Set text color to ensure readability
                    if class_text in ['S']:  # Yellow background needs dark text
                        class_item.setForeground(QColor(0, 0, 0))  # Black text
                    else:
                        class_item.setForeground(QColor(255, 255, 255))  # White text
            
            # Add the row
            self.results_detail_model.appendRow([metric_item, value_item, eqr_item, class_item])
            row_count += 1
        
        # If no data found, show a message
        if row_count == 0:
            no_data_item = QStandardItem("Žádné výsledky nenalezeny")
            no_data_item.setEditable(False)
            empty_item1 = QStandardItem("")
            empty_item1.setEditable(False)
            empty_item2 = QStandardItem("")
            empty_item2.setEditable(False)
            empty_item3 = QStandardItem("")
            empty_item3.setEditable(False)
            self.results_detail_model.appendRow([no_data_item, empty_item1, empty_item2, empty_item3])
        
        # Set the model to the table view
        self.results_detail_table_view.setModel(self.results_detail_model)
        
        # Set column widths for 4 columns
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Metrika
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Hodnota
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # EQR
        self.results_detail_table_view.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Třída
        
        # Set fixed widths for the last three columns
        self.results_detail_table_view.setColumnWidth(1, 80)  # Hodnota
        self.results_detail_table_view.setColumnWidth(2, 80)  # EQR
        self.results_detail_table_view.setColumnWidth(3, 60)  # Třída
        
        # Store the sample ID for later use
        self.results_sample_id = sample_id

    def on_results_sample_selection_changed(self, current, previous):
        """Handle results sample selection changes (simplified - no unsaved data tracking needed)"""
        if not current.isValid():
            return
        
        self.load_results_details(current)

    def calculate_indexes(self):
        """Vypočítá indexy (agregace se provede automaticky).

        Výsledky se zapisují spojením Qt, takže to musí zůstat otevřené.
        Zámky z modelů se přesto uvolnit musí: B-index si během výpočtu
        otevírá vlastní spojení a zapisuje do pomocných tabulek. Dokud
        se zámky neuvolňovaly, jeho zápis končil hláškou „database is
        locked“ — a protože je volání obalené v try/except, metrika se
        bez jediného slova nespočítala.
        """
        from calc_indexes import run_index_calculation

        chyba = None
        with self.databaze_pro_zapis():
            try:
                run_index_calculation(self, self.db)
            except ImportError as e:
                chyba = f"Nelze načíst modul:\n{e}"
            except Exception as e:  # noqa: BLE001 - hlásí se uživateli
                chyba = f"Chyba při výpočtu:\n{e}"

        if chyba is not None:
            QMessageBox.critical(self, "Chyba", chyba)
            return

        vybrany = self.results_samples_table_view.currentIndex()
        if vybrany.isValid():
            self.load_results_details(vybrany)

    # --- Umístění databáze ---

    def zkontroluj_uloziste(self, cesta_db):
        """Ověří, na jakém úložišti databáze leží, a případně varuje.

        SQLite si neporadí se zamykáním souborů na síťových discích ani
        ve složkách synchronizovaných cloudovými klienty (ownCloud, OneDrive,
        Dropbox…). Projevuje se to chybami „disk I/O error“ nebo
        „database is locked“ a v horším případě poškozením databáze.

        Pokud takové úložiště zjistíme, nabídneme práci z lokální kopie,
        která se při ukončení aplikace uloží zpátky.

        Returns:
            cesta k databázi, se kterou se má pracovat, nebo None, když
            uživatel práci s ní odmítl
        """
        try:
            import uloziste
        except ImportError:
            return cesta_db  # bez modulu prostě pokračujeme beze změny

        misto = uloziste.zjisti(cesta_db)
        if not misto.rizikove:
            return cesta_db

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Riziko poškození databáze")
        dialog.setText(uloziste.text_varovani(misto))

        pracovni = uloziste.doporucene_umisteni(os.path.basename(cesta_db))
        dialog.setInformativeText(
            "Aplikace může pracovat s kopií na místním disku a při ukončení "
            f"ji uložit zpět.\n\nMístní kopie: {pracovni}"
        )

        tlacitko_kopie = dialog.addButton(
            "Pracovat z místní kopie", QMessageBox.ButtonRole.AcceptRole
        )
        tlacitko_presto = dialog.addButton(
            "Pokračovat i tak", QMessageBox.ButtonRole.DestructiveRole
        )
        dialog.addButton("Ukončit", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(tlacitko_kopie)
        dialog.exec()

        stisknuto = dialog.clickedButton()

        if stisknuto is tlacitko_presto:
            print(f"[uloziste] Práce přímo na rizikovém úložišti: {misto!r}")
            return cesta_db

        if stisknuto is not tlacitko_kopie:
            # Dřív se tu volalo sys.exit(0). Teď se databáze dá přepnout
            # i za běhu, takže odmítnutí ukončí jen otevírání souboru -
            # rozdělaná práce v jiné databázi tím nepřijde vniveč.
            return None

        try:
            self.pracovni_kopie = uloziste.PracovniKopie(cesta_db, pracovni)
            nova_cesta = self.pracovni_kopie.priprav()
        except Exception as e:
            self.pracovni_kopie = None
            QMessageBox.critical(
                self, "Chyba",
                f"Nepodařilo se vytvořit místní kopii databáze:\n{e}\n\n"
                "Aplikace bude pokračovat s původním umístěním."
            )
            return cesta_db

        self.setWindowTitle(
            f"LULAN — místní kopie (originál: {cesta_db})"
        )
        return nova_cesta

    def uloz_databazi_zpet(self):
        """Uloží pracovní kopii databáze zpět na původní místo."""
        if self.pracovni_kopie is None:
            return True

        if self.pracovni_kopie.je_novejsi_original():
            odpoved = QMessageBox.warning(
                self, "Původní databáze se mezitím změnila",
                "Soubor na síťovém úložišti je novější než místní kopie — "
                "nejspíš do něj zapsal někdo jiný nebo synchronizační klient.\n\n"
                "Přepsat ho vaší verzí? Původní soubor se předtím zazálohuje.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if odpoved != QMessageBox.StandardButton.Yes:
                QMessageBox.information(
                    self, "Databáze neuložena",
                    "Vaše změny zůstávají v místní kopii:\n"
                    f"{self.pracovni_kopie.pracovni_cesta}"
                )
                return True

        uspech, zprava = self.pracovni_kopie.uloz_zpet()
        if not uspech:
            QMessageBox.critical(self, "Chyba při ukládání", zprava)
            return False
        print(f"[uloziste] {zprava}")
        return True

    def closeEvent(self, event):
        """Při ukončení uložit pracovní kopii zpět na síťové úložiště."""
        if self.db.isOpen():
            self.db.close()
        self.uloz_databazi_zpet()
        super().closeEvent(event)

    def export_results_placeholder(self):
        """Placeholder for export results functionality"""
        self.exportuj_vysledky()

    # --- Abiotické parametry lokalit ---

    def _dialog_zdroju(self, chybi):
        """Dialog se zdroji dat, licencemi a upozorněním před dopočtem.

        Uživatel musí vidět, odkud hodnoty pocházejí a za jakých podmínek
        jsou podklady poskytovány, ještě než dopočet spustí — u DIBAVOD
        nejde o otevřená data a licence ČÚZK i ČHMÚ (CC BY 4.0) vyžadují
        uvedení zdroje. Zároveň je to místo, kde se přizná, že jde
        o pomocnou funkci bez záruky.

        Returns:
            True, pokud uživatel dopočet potvrdil
        """
        import abiotic_params

        dialog = QDialog(self)
        dialog.setWindowTitle("Doplnit abiotické parametry")
        dialog.resize(720, 620)

        rozvrzeni = QVBoxLayout(dialog)

        text = QTextBrowser(dialog)
        text.setOpenExternalLinks(True)
        seznam = "".join(f"<li>{radek}</li>" for radek in chybi)
        text.setHtml(
            f"<h3>Chybějící hodnoty</h3><ul>{seznam}</ul>"
            f"<h3>Zdroje dat a licence</h3>"
            f"{abiotic_params.popis_zdroju_html()}"
            f"<p style='color:#555'>Nadmořská výška a sklon se stahují "
            f"z online služby ČÚZK, dopočet proto vyžaduje připojení "
            f"k internetu a může trvat několik minut.</p>"
        )
        rozvrzeni.addWidget(text)

        tlacitka = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        tlacitka.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Rozumím, spustit dopočet"
        )
        tlacitka.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        # Výchozí je Zrušit — potvrzení má být vědomé, ne omylem přes Enter.
        tlacitka.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        tlacitka.accepted.connect(dialog.accept)
        tlacitka.rejected.connect(dialog.reject)
        rozvrzeni.addWidget(tlacitka)

        return dialog.exec() == QDialog.DialogCode.Accepted

    def fill_abiotic_params(self):
        """Dopočítá chybějící abiotické parametry lokalit.

        Souřadnice S-42 jsou vstupem predikčního modelu B-index (metrika
        MB07); bez nich se B-index nedá spočítat. Nadmořská výška a sklon
        se stahují z online služby ČÚZK, takže výpočet vyžaduje připojení
        k internetu a chvíli trvá.

        Před spuštěním se zobrazí přehled zdrojů, licencí a upozornění, že
        jde o pomocnou funkci bez záruky — viz `_dialog_zdroju()`.
        """
        try:
            import abiotic_params
        except ImportError as e:
            QMessageBox.critical(
                self, "Chyba",
                f"Nelze načíst modul abiotic_params:\n{e}\n\n"
                "Zkontrolujte, že jsou nainstalované knihovny "
                "pyproj a requests."
            )
            return

        db_path = self.db.databaseName()
        prehled = abiotic_params.prehled_naplnenosti(db_path)
        chybi = [
            f"{sloupec}: chybí {celkem - n} z {celkem}"
            for sloupec, (n, celkem) in prehled.items()
            if n < celkem
        ]

        if not chybi:
            QMessageBox.information(
                self, "Abiotické parametry",
                "Všechny abiotické parametry jsou již vyplněné."
            )
            return

        if not self._dialog_zdroju(chybi):
            return

        dialog = QProgressDialog(
            "Doplňuji abiotické parametry…", "Zrušit", 0, 0, self
        )
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.show()

        def progress(aktualni, celkem, popis):
            dialog.setLabelText(f"{popis} ({aktualni}/{celkem})")
            QApplication.processEvents()

        # Dopočet zapisuje vlastním spojením, takže databáze musí být
        # na tu dobu z Qt uvolněná - stejný důvod jako u importu CSV.
        vysledek = {}
        chyba = None
        with self.databaze_pro_zapis() as cesta_db:
            try:
                vysledek = abiotic_params.doplnit_parametry(
                    cesta_db, jen_chybejici=True, progress=progress
                )
            except Exception as e:  # noqa: BLE001 - hlásí se uživateli
                chyba = str(e)

        dialog.close()
        if chyba is not None:
            QMessageBox.critical(self, "Chyba", f"Chyba při dopočtu:\n{chyba}")
            return

        radky = []
        for parametr, info in vysledek.items():
            if info["chyba"]:
                radky.append(f"  {parametr}: {info['chyba']}")
            elif info["lokalit"]:
                radky.append(
                    f"  {parametr}: doplněno {info['doplneno']} "
                    f"z {info['lokalit']}"
                )
        souhrn = QMessageBox(self)
        souhrn.setWindowTitle("Abiotické parametry")
        souhrn.setIcon(QMessageBox.Icon.Information)
        souhrn.setText(
            "Dopočet dokončen.\n\n"
            + ("\n".join(radky) or "Nebylo co doplnit.")
            + "\n\nHodnoty jsou odvozené automaticky — zkontrolujte je "
              "před použitím pro hodnocení."
        )
        souhrn.setDetailedText(
            "Zdroje dat:\n"
            + "\n".join(
                f"  {nazev}\n    {spravce}\n    licence: {licence}\n    {url}"
                for nazev, spravce, licence, url, _ in abiotic_params.ZDROJE_DAT
            )
            + f"\n\nCitace DIBAVOD:\n  {abiotic_params.CITACE_DIBAVOD}"
        )
        souhrn.exec()
        # Zobrazení obnovovat netřeba - `databaze_pro_zapis` modely
        # načetla znovu hned po zápisu.

    # --- Tab0 (Utvary) Supporting Methods ---
    
    def on_utvary_data_changed(self, topLeft, bottomRight, roles):
        """Validate data when it changes in the table"""
        # Get the column that was changed
        for col in range(topLeft.column(), bottomRight.column() + 1):
            column_name = self.utvary_model.headerData(col, Qt.Orientation.Horizontal)
            
            # If this column requires validation
            if column_name in self.utvary_allowed_values:
                for row in range(topLeft.row(), bottomRight.row() + 1):
                    index = self.utvary_model.index(row, col)
                    value = self.utvary_model.data(index)
                    
                    # Validate the value
                    if value and value not in self.utvary_allowed_values[column_name]:
                        QMessageBox.warning(
                            self,
                            "Neplatná hodnota",
                            f"Hodnota '{value}' není povolená pro sloupec {column_name}.\n"
                            f"Povolené hodnoty jsou: {', '.join(self.utvary_allowed_values[column_name])}"
                        )
                        # Revert the change
                        self.utvary_model.revertAll()
                        return

    def validate_utvary_before_submit(self, row, record):
        """Poslední kontrola kódovaných sloupců před zápisem do databáze.

        Rozbalovací nabídka i model už neplatnou hodnotu odmítnou, tohle je
        pojistka pro data, která se do modelu dostala jinudy (import, ruční
        zásah do databáze).
        """
        zaznam = {
            sloupec: record.value(sloupec)
            for sloupec in ciselniky_modul.UTVARY
            if record.indexOf(sloupec) >= 0
        }
        chyby = ciselniky_modul.zkontroluj_utvar(zaznam)
        if chyby:
            QMessageBox.critical(
                self, "Neplatná hodnota",
                "Záznam nelze uložit:\n\n"
                + "\n".join(f"  • {c}" for c in chyby),
            )
            return False
        return True

    def save_utvary_changes(self):
        """Save changes in the utvary table with validation"""
        if not self.utvary_model.submitAll():
            error_msg = self.utvary_model.lastError().text()
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se uložit změny: {error_msg}")
            self.utvary_model.revertAll()
        else:
            QMessageBox.information(self, "Úspěch", "Změny byly úspěšně uloženy.")
            self.utvary_model.select()

    def add_new_utvar(self):
        """Add a new water body (utvar) to the database"""
        # Generate unique KOD
        kod_value = self.generate_unique_utvar_kod()
        
        # Use QSqlQuery to insert without ID_UTVARU (let database auto-generate it)
        query = QSqlQuery(self.db)
        
        # Explicit INSERT without ID_UTVARU - database will auto-generate it
        query.prepare("""
            INSERT INTO utvary (ID_UTVARU, NAZ_UTVARU, DILCI_POVODI, KATEGORIE, HMWB, VYSYCHAVY, BROD)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """)
        
        vychozi = ciselniky_modul.vychozi_utvar()
        query.addBindValue(kod_value)              # ID_UTVARU
        query.addBindValue("Nový útvar")           # NAZ_UTVARU
        query.addBindValue("")                     # DILCI_POVODI
        query.addBindValue(vychozi["KATEGORIE"])   # ŘEKA
        query.addBindValue(vychozi["HMWB"])        # PŘIROZENÝ
        query.addBindValue(vychozi["VYSYCHAVY"])   # PERENIÁLNÍ
        query.addBindValue(vychozi["BROD"])        # BRODITELNÝ
        
        if not query.exec():
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se přidat nový útvar: {query.lastError().text()}")
            return
        
        # Refresh model to show the new row
        self.utvary_model.select()
        
        # Find and select the new row (search in source model, then map to proxy)
        for row in range(self.utvary_model.rowCount()):
            if self.utvary_model.record(row).value("ID_UTVARU") == kod_value:
                # Map source index to proxy index
                source_index = self.utvary_model.index(row, 0)
                proxy_index = self.utvary_proxy_model.mapFromSource(source_index)
                if proxy_index.isValid():
                    self.utvary_table_view.selectRow(proxy_index.row())
                break

    def generate_unique_utvar_kod(self):
        """Generate a unique KOD for a new water body"""
        base_kod = "New_Utvar"
        index = 1
        kod = f"{base_kod}_{index}"

        # Check existing KODs
        existing_kods = set()
        for row in range(self.utvary_model.rowCount()):
            existing_kods.add(self.utvary_model.record(row).value("ID_UTVARU"))

        while kod in existing_kods:
            index += 1
            kod = f"{base_kod}_{index}"

        return kod

    def delete_selected_utvary(self):
        """Delete selected water bodies from the database"""
        selected_rows = self.utvary_table_view.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Žádný výběr", "Nejsou vybrány žádné útvary ke smazání.")
            return

        count = len(selected_rows)
        reply = QMessageBox.question(
            self,
            "Potvrzení smazání",
            f"Opravdu chcete smazat {count} útvarů?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Map proxy indices to source model indices and delete rows in reverse order
        source_rows = []
        for proxy_index in selected_rows:
            source_index = self.utvary_proxy_model.mapToSource(proxy_index)
            source_rows.append(source_index.row())
        
        # Delete in reverse order to maintain valid indices
        for row in sorted(source_rows, reverse=True):
            self.utvary_model.removeRow(row)

        # Submit changes
        if not self.utvary_model.submitAll():
            error_msg = self.utvary_model.lastError().text()
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se smazat útvary: {error_msg}")
            self.utvary_model.revertAll()
        else:
            QMessageBox.information(self, "Úspěch", f"Úspěšně smazáno {count} útvarů.")
            self.utvary_model.select()

    def import_utvary_from_csv(self):
        """Import vodnich utvaru z CSV - viz menu Import."""
        self.importuj_csv("utvary")

    def on_results_view_changed(self, index):
        """Handler pro změnu zobrazení"""
        try:
            self.results_stacked_widget.setCurrentIndex(index)
            if index == 1:  # Roční výsledky
                self.load_yearly_results()
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při přepínání pohledu:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def load_yearly_results(self):
        """Načte roční výsledky s robustním error handlingem"""
        try:
            from calc_indexes import get_yearly_results_summary
            
            results = get_yearly_results_summary(self.db)
            
            # Vymazat stávající data
            self.results_yearly_model.removeRows(0, self.results_yearly_model.rowCount())
            
            if not results:
                # Žádná data - zobrazit prázdnou tabulku
                print("Žádné roční výsledky k zobrazení")
                return
            
            # Přidat řádky
            for result in results:
                try:
                    row = []
                    
                    # Útvar
                    utvar = result.get('UTVAR_POV', '')
                    row.append(QStandardItem(str(utvar) if utvar else ""))
                    
                    # Rok
                    rok = result.get('ROK', 0)
                    row.append(QStandardItem(str(rok) if rok else ""))
                    
                    # MZB
                    mzb_eqr = result.get('MZB_EQR')
                    row.append(QStandardItem(f"{mzb_eqr:.3f}" if mzb_eqr is not None and isinstance(mzb_eqr, (int, float)) else ""))
                    mzb_class = result.get('MZB_CLASS', '')
                    row.append(QStandardItem(str(mzb_class) if mzb_class else ""))
                    
                    # FB
                    fb_eqr = result.get('FB_EQR')
                    row.append(QStandardItem(f"{fb_eqr:.3f}" if fb_eqr is not None and isinstance(fb_eqr, (int, float)) else ""))
                    fb_class = result.get('FB_CLASS', '')
                    row.append(QStandardItem(str(fb_class) if fb_class else ""))
                    
                    # FP
                    fp_eqr = result.get('FP_EQR')
                    row.append(QStandardItem(f"{fp_eqr:.3f}" if fp_eqr is not None and isinstance(fp_eqr, (int, float)) else ""))
                    fp_class = result.get('FP_CLASS', '')
                    row.append(QStandardItem(str(fp_class) if fp_class else ""))
                    
                    # MF
                    mf_eqr = result.get('MF_EQR')
                    row.append(QStandardItem(f"{mf_eqr:.3f}" if mf_eqr is not None and isinstance(mf_eqr, (int, float)) else ""))
                    mf_class = result.get('MF_CLASS', '')
                    row.append(QStandardItem(str(mf_class) if mf_class else ""))
                    
                    # RYBY
                    ryby_eqr = result.get('RYBY_EQR')
                    row.append(QStandardItem(f"{ryby_eqr:.3f}" if ryby_eqr is not None and isinstance(ryby_eqr, (int, float)) else ""))
                    ryby_class = result.get('RYBY_CLASS', '')
                    row.append(QStandardItem(str(ryby_class) if ryby_class else ""))
                    
                    # FYZCHEM
                    fyzchem = result.get('FYZCHEM_CLASS', '')
                    row.append(QStandardItem(str(fyzchem) if fyzchem else ""))
                    
                    self.results_yearly_model.appendRow(row)
                    
                except Exception as e:
                    print(f"Chyba při zpracování řádku: {e}")
                    continue
                    
        except ImportError as e:
            QMessageBox.critical(self, "Chyba", f"Nelze načíst modul calc_indexes:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při načítání ročních výsledků:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Ikona se nastavuje i na aplikaci, ne jen na okno - Windows podle ni
    # sdruzuje okna v listě a nekterá prostredi na Linuxu ji berou odtud.
    app.setWindowIcon(ikona_aplikace())
    if sys.platform == "win32":
        # Bez vlastniho AppUserModelID Windows povazuji proces za "python"
        # a v listě ukazou ikonu Pythonu misto ikony aplikace.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "cz.muni.lulan")
        except Exception:  # noqa: BLE001 - jen kosmetika, nesmi shodit start
            pass
    window = LULANApp()
    window.show()
    sys.exit(app.exec())