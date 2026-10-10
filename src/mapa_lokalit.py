"""
Mapovy nahled polohy lokality v ramci hranic CR.

Widget vykresli obrys statni hranice ze shapefilu `src/GIS/hrcr_S42.shp`,
sit hlavnich toku CR z `src/GIS/hlavni_toky_S42.shp` a cervenou teckou
polohu vybrane lokality. Reky jsou tam kvuli orientaci - samotny obrys
statu je na odhad polohy bodu prilis prazdny.

Souradnicovy system
-------------------
Shapefile je v Pulkovo 1942 / Gauss-Kruger pasmo 3 (EPSG:28403), tedy
v temze systemu jako sloupce `loc.S42_X` a `loc.S42_Y`. Body se proto
vykresluji primo, bez jakehokoli prepoctu. Kdyz lokalita souradnice S-42
nema, dopocitaji se z WGS84 pres pyproj (stejne jako v abiotic_params).

Cteni shapefilu
---------------
Zamerne bez geopandas - format ESRI shapefile je pro polygony natolik
jednoduchy, ze staci ~50 radku se `struct`. Aplikace tak nema dalsi
tezkou zavislost a mapa funguje i tam, kde geopandas neni.
"""

from __future__ import annotations

import os
import struct

from cesty import v_korenu

#: Typy geometrie v hlavicce shapefilu.
TYP_POLYGON = 5
TYP_POLYLINE = 3

#: Umisteni vrstev vuci korenu projektu.
VRSTVA_HRANICE = os.path.join("src", "GIS", "hrcr_S42.shp")

#: Hlavni toky CR. Vrstvu vyrabi `_tools/vyber_hlavni_toky.py` z hrubeho
#: cleneni vodnich toku. Bez rek je obrys statu na odhad polohy bodu
#: prilis prazdny - podle toku se uzivatel zorientuje o poznani snadneji.
VRSTVA_TOKY = os.path.join("src", "GIS", "hlavni_toky_S42.shp")


def cesta_k_hranicim():
    return v_korenu(VRSTVA_HRANICE)


def cesta_k_tokum():
    return v_korenu(VRSTVA_TOKY)


# ---------------------------------------------------------------------------
# Cteni shapefilu
# ---------------------------------------------------------------------------

def nacti_polygony(cesta):
    """Nacte polygony ze shapefilu.

    Returns:
        (casti, rozsah) kde
          casti  - list seznamu bodu [(x, y), ...], kazdy je jeden uzavreny
                   prstenec (stat, enklava, jezero uvnitr...)
          rozsah - (xmin, ymin, xmax, ymax) z hlavicky souboru

    Raises:
        OSError: soubor nelze precist
        ValueError: soubor neni shapefile s polygony
    """
    with open(cesta, "rb") as f:
        hlavicka = f.read(100)
        if len(hlavicka) < 100:
            raise ValueError("Soubor je kratší než hlavička shapefilu.")
        (kod,) = struct.unpack(">i", hlavicka[0:4])
        if kod != 9994:
            raise ValueError("Soubor není ESRI shapefile.")
        (typ,) = struct.unpack("<i", hlavicka[32:36])
        if typ != TYP_POLYGON:
            raise ValueError(
                f"Očekáván polygonový shapefile (typ {TYP_POLYGON}), "
                f"nalezen typ {typ}."
            )
        rozsah = struct.unpack("<4d", hlavicka[36:68])

        casti = []
        while True:
            zaznam = f.read(8)
            if len(zaznam) < 8:
                break
            _cislo, delka = struct.unpack(">ii", zaznam)
            obsah = f.read(delka * 2)
            if len(obsah) < delka * 2:
                break
            (typ_zaznamu,) = struct.unpack("<i", obsah[0:4])
            if typ_zaznamu != TYP_POLYGON:
                continue  # prazdna geometrie

            pocet_casti, pocet_bodu = struct.unpack("<ii", obsah[36:44])
            zacatky = struct.unpack(
                f"<{pocet_casti}i", obsah[44:44 + 4 * pocet_casti]
            )
            posun = 44 + 4 * pocet_casti
            body = struct.unpack(
                f"<{2 * pocet_bodu}d", obsah[posun:posun + 16 * pocet_bodu]
            )
            souradnice = list(zip(body[0::2], body[1::2]))
            for i, zacatek in enumerate(zacatky):
                konec = zacatky[i + 1] if i + 1 < pocet_casti else pocet_bodu
                if konec - zacatek >= 3:
                    casti.append(souradnice[zacatek:konec])

    if not casti:
        raise ValueError("Shapefile neobsahuje žádné polygony.")
    return casti, rozsah


def nacti_linie(cesta):
    """Nacte polylinie ze shapefilu.

    Struktura zaznamu je stejna jako u polygonu, lisi se jen kod typu -
    u linie se nepredpoklada, ze je prstenec uzavreny.

    Returns:
        list seznamu bodu [(x, y), ...]; kazdy je jedna souvisla cara

    Raises:
        OSError: soubor nelze precist
        ValueError: soubor neni shapefile s liniemi
    """
    with open(cesta, "rb") as f:
        hlavicka = f.read(100)
        if len(hlavicka) < 100:
            raise ValueError("Soubor je kratší než hlavička shapefilu.")
        if struct.unpack(">i", hlavicka[0:4])[0] != 9994:
            raise ValueError("Soubor není ESRI shapefile.")
        (typ,) = struct.unpack("<i", hlavicka[32:36])
        if typ != TYP_POLYLINE:
            raise ValueError(
                f"Očekáván liniový shapefile (typ {TYP_POLYLINE}), "
                f"nalezen typ {typ}.")

        cary = []
        while True:
            zahlavi = f.read(8)
            if len(zahlavi) < 8:
                break
            _cislo, delka = struct.unpack(">ii", zahlavi)
            obsah = f.read(delka * 2)
            if len(obsah) < delka * 2:
                break
            if struct.unpack("<i", obsah[0:4])[0] != TYP_POLYLINE:
                continue

            pocet_casti, pocet_bodu = struct.unpack("<ii", obsah[36:44])
            zacatky = struct.unpack(
                f"<{pocet_casti}i", obsah[44:44 + 4 * pocet_casti])
            posun = 44 + 4 * pocet_casti
            body = struct.unpack(
                f"<{2 * pocet_bodu}d", obsah[posun:posun + 16 * pocet_bodu])

            for i, zacatek in enumerate(zacatky):
                konec = zacatky[i + 1] if i + 1 < pocet_casti else pocet_bodu
                if konec - zacatek >= 2:
                    cary.append([
                        (body[2 * j], body[2 * j + 1])
                        for j in range(zacatek, konec)
                    ])
    return cary


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
    from PyQt6.QtWidgets import QWidget
except ImportError:  # pragma: no cover - modul jde pouzit i bez Qt
    QWidget = object
    QPointF = Qt = QBrush = QColor = QPainter = QPainterPath = QPen = None


class MapaLokalit(QWidget):
    """Obrys ČR s červenou tečkou na pozici vybrané lokality."""

    BARVA_VYPLNE = "#eef3f7"
    BARVA_HRANICE = "#5a7387"
    BARVA_BODU = "#d62828"
    #: Reky maji byt orientacni sit, ne hlavni sdeleni - proto svetlejsi
    #: modra a tenci cara nez u hranice statu.
    BARVA_TOKU = "#7ba4cf"

    #: Svisle zarovnani obrysu: "nahoru" | "stred".
    #: Widget byva vyssi nez obrys CR, ktery je siroky a nizky; pri
    #: zarovnani na stred by pod nim zustal velky prazdny pas.
    ZAROVNANI = "nahoru"

    def __init__(self, parent=None, cesta=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        # Pozadi maluje rodic. Staci na to `setAutoFillBackground(False)`:
        # widget si pak pozadi nevyplnuje vubec a prosvita skrz nej to,
        # co nakreslil rodic.
        #
        # Drive tu bylo jeste `WA_TranslucentBackground`. Ten atribut je
        # ale urceny pro okna, ne pro widgety uvnitr nich - Qt kvuli nemu
        # prepne cele hlavni okno do pruhledneho rezimu. Vedlejsim
        # ucinkem je, ze se prestanou zobrazovat vyskakovaci nabidky
        # (`QComboBox`, `QMenu`), protoze to jsou samostatna okna.
        # V LULANu se tim rozbily oba rozbalovaci seznamy, aniz by mapa
        # s taxony nebo vysledky cokoli spolecneho mela.
        self.setAutoFillBackground(False)
        # Vyska se ridi sirkou podle pomeru stran vrstvy, aby pod mapou
        # nezustaval prazdny pas.
        zasady = self.sizePolicy()
        zasady.setHeightForWidth(True)
        self.setSizePolicy(zasady)
        self._casti = []
        self._toky = []
        self._rozsah = None
        self._bod = None          # (S42_X, S42_Y)
        self._popis = ""
        self._chyba = None
        self.nacti_vrstvu(cesta or cesta_k_hranicim())
        self.nacti_toky(cesta_k_tokum())

    # -- rozmery -------------------------------------------------------

    def _pomer_stran(self):
        """Vyska ku sirce podle rozsahu vrstvy."""
        if not self._rozsah:
            return 0.6
        xmin, ymin, xmax, ymax = self._rozsah
        if xmax - xmin <= 0:
            return 0.6
        return (ymax - ymin) / (xmax - xmin)

    def hasHeightForWidth(self):  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, sirka):  # noqa: N802 - Qt API
        return int(sirka * self._pomer_stran()) + 16

    def sizeHint(self):  # noqa: N802 - Qt API
        from PyQt6.QtCore import QSize

        sirka = max(self.width(), 260)
        return QSize(sirka, self.heightForWidth(sirka))

    # -- data ----------------------------------------------------------

    def nacti_vrstvu(self, cesta):
        """Nacte vrstvu hranic; pri neuspechu widget zobrazi hlasku."""
        try:
            self._casti, self._rozsah = nacti_polygony(cesta)
            self._chyba = None
        except (OSError, ValueError, struct.error) as e:
            self._casti, self._rozsah = [], None
            self._chyba = f"Mapu nelze zobrazit:\n{e}"
        self.update()

    def nacti_toky(self, cesta):
        """Nacte vrstvu hlavnich toku.

        Je to jen orientacni podklad - kdyz vrstva chybi nebo se nacist
        neda, mapa se vykresli bez rek a nic se nehlasi. Obrys statu je
        podstatny, reky pomahaji.
        """
        try:
            self._toky = nacti_linie(cesta)
        except (OSError, ValueError, struct.error):
            self._toky = []
        self.update()

    def zobraz_lokalitu(self, x, y, popis=""):
        """Nastavi polohu tecky v souradnicich S-42 (EPSG:28403).

        Hodnoty None teckou pohnou pryc - lokalita bez souradnic se jen
        nevykresli, mapa zustane.
        """
        self._bod = None
        if x is not None and y is not None:
            try:
                self._bod = (float(x), float(y))
            except (TypeError, ValueError):
                self._bod = None
        self._popis = popis or ""
        self.update()

    def vycisti(self):
        self.zobraz_lokalitu(None, None)

    # -- vykresleni ----------------------------------------------------

    def _prepocet(self):
        """Vrati funkci prevadejici souradnice S-42 na pixely widgetu."""
        xmin, ymin, xmax, ymax = self._rozsah
        okraj = 8
        sirka = max(self.width() - 2 * okraj, 1)
        vyska = max(self.height() - 2 * okraj, 1)
        rozpeti_x = max(xmax - xmin, 1e-6)
        rozpeti_y = max(ymax - ymin, 1e-6)
        # stejne meritko v obou osach, ať se tvar státu nedeformuje
        meritko = min(sirka / rozpeti_x, vyska / rozpeti_y)
        posun_x = okraj + (sirka - rozpeti_x * meritko) / 2
        posun_y = okraj
        if self.ZAROVNANI != "nahoru":
            posun_y += (vyska - rozpeti_y * meritko) / 2

        def preved(x, y):
            # osa Y roste na sever, v okně dolů - proto obraceně
            return QPointF(
                posun_x + (x - xmin) * meritko,
                posun_y + (ymax - y) * meritko,
            )

        return preved

    def paintEvent(self, event):  # noqa: N802 - Qt API
        malir = QPainter(self)
        malir.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._chyba or not self._rozsah:
            malir.setPen(QPen(QColor("#888888")))
            malir.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._chyba or "Mapa není k dispozici",
            )
            return

        preved = self._prepocet()

        cesta = QPainterPath()
        for cast in self._casti:
            if not cast:
                continue
            cesta.moveTo(preved(*cast[0]))
            for x, y in cast[1:]:
                cesta.lineTo(preved(x, y))
            cesta.closeSubpath()

        malir.setBrush(QBrush(QColor(self.BARVA_VYPLNE)))
        malir.setPen(QPen(QColor(self.BARVA_HRANICE), 1.2))
        malir.drawPath(cesta)

        # Reky se kresli az po vyplni statu, aby nezmizely pod ni, ale
        # jeste pred teckou lokality, ktera ma zustat nahore.
        if self._toky:
            reky = QPainterPath()
            for cara in self._toky:
                reky.moveTo(preved(*cara[0]))
                for x, y in cara[1:]:
                    reky.lineTo(preved(x, y))
            malir.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            malir.setPen(QPen(QColor(self.BARVA_TOKU), 0.9))
            malir.drawPath(reky)

        if self._bod is not None:
            # Popisek se zámerne nekresli - ktera lokalita je vybrana,
            # je videt ze zvyrazneneho radku v tabulce.
            stred = preved(*self._bod)
            malir.setBrush(QBrush(QColor(self.BARVA_BODU)))
            malir.setPen(QPen(QColor("#ffffff"), 1.4))
            malir.drawEllipse(stred, 5.0, 5.0)
        # Kdyz lokalita souradnice nema, tecka se proste nevykresli.
        # Drive tu byla hlaska "lokalita nema vyplnene souradnice", ale
        # v panelu je hned nad mapou tabulka, kde je prazdna souradnice
        # videt primo - text tedy jen opakoval, co uz uzivatel vidi.


# ---------------------------------------------------------------------------
# Prevod souradnic
# ---------------------------------------------------------------------------

def s42_z_wgs84(lat, lon):
    """Prepocte WGS84 na S-42 pasmo 3; bez pyproj vrati (None, None)."""
    try:
        from pyproj import Transformer
    except ImportError:
        return None, None
    if lat is None or lon is None:
        return None, None
    try:
        prevod = Transformer.from_crs("EPSG:4326", "EPSG:28403",
                                      always_xy=True)
        x, y = prevod.transform(float(lon), float(lat))
        return x, y
    except (ValueError, TypeError):
        return None, None


def souradnice_lokality(radek):
    """Vrati (x, y) v S-42 z jednoho radku tabulky `loc`.

    Args:
        radek: dict se sloupci S42_X, S42_Y, WGS84_LAT, WGS84_LON
    """
    x, y = radek.get("S42_X"), radek.get("S42_Y")
    if x not in (None, "") and y not in (None, ""):
        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            pass
    return s42_z_wgs84(radek.get("WGS84_LAT"), radek.get("WGS84_LON"))
