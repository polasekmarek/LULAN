"""
Dopocet abiotickych parametru pro libovolny bod na vodnim toku.

Pracuje nad odvozenou databazi `dtb/ricni_sit.db`, kterou sestavuje
`_tools/gen_ricni_sit.py` ze tri zdrojovych vrstev (DIBAVOD A02, DIBAVOD
Strahler, CHMU rozvodnice 5G). Aplikace tak nepotrebuje zadnou GIS knihovnu
ani samotne shapefily - jen jeden soubor.

Postup:
  1. souradnice se prevedou do S-JTSK (EPSG:5514)
  2. R-tree najde useky v okoli, spocita se kolma vzdalenost k ose
  3. z nejblizsiho useku se odectou hodnoty; velicin zavisejicich na poloze
     podel useku (vzdalenost od pramene, plocha povodi) se lineárne
     interpoluje mezi zacatkem a koncem useku

Pouziti:
    from ricni_sit import RicniSit
    with RicniSit() as sit:
        udaje = sit.popis_bodu(49.5804, 18.0831)
"""

from __future__ import annotations

import math
import os
import sqlite3
import struct

from cesty import v_korenu

VYCHOZI_DB = v_korenu("dtb", "ricni_sit.db")

#: Do jake vzdalenosti od osy toku se bod jeste povazuje za lezici na toku [m].
#: Vetsi odsazeni obvykle znamena, ze souradnice miri mimo vodni tok.
MEZ_ODSAZENI = 150.0

#: O kolik metru se rozsiri hledaci obdelnik kolem bodu.
KROK_HLEDANI = (100.0, 500.0, 2000.0)

POPIS_UMORI = {1: "Labe (Severní moře)", 2: "Odra (Baltské moře)",
               3: "Dunaj (Černé moře)"}


class RicniSit:
    """Pristup k odvozene ricni siti."""

    def __init__(self, cesta=None):
        self.cesta = cesta or VYCHOZI_DB
        if not os.path.exists(self.cesta):
            raise FileNotFoundError(
                f"Databáze říční sítě nenalezena: {self.cesta}\n"
                f"Sestavte ji příkazem: python _tools/gen_ricni_sit.py"
            )
        self.conn = sqlite3.connect(self.cesta)
        self.conn.row_factory = sqlite3.Row
        self._prevod = None

    def __enter__(self):
        return self

    def __exit__(self, *chyba):
        self.zavri()

    def zavri(self):
        self.conn.close()

    # -- souradnice ----------------------------------------------------

    def _do_sjtsk(self, lat, lon):
        """WGS84 -> S-JTSK (EPSG:5514)."""
        if self._prevod is None:
            from pyproj import Transformer
            self._prevod = Transformer.from_crs(
                "EPSG:4326", "EPSG:5514", always_xy=True)
        return self._prevod.transform(lon, lat)

    # -- hledani useku -------------------------------------------------

    def najdi_usek(self, x, y):
        """Najde nejblizsi usek k bodu v S-JTSK.

        Returns:
            (radek, odsazeni_m, podil_delky) nebo (None, None, None)
        """
        for okoli in KROK_HLEDANI:
            dotaz = """
                SELECT u.* FROM useky u
                JOIN useky_idx i ON i.id = u.id
                WHERE i.xmax >= ? AND i.xmin <= ? AND i.ymax >= ? AND i.ymin <= ?
            """
            radky = self.conn.execute(
                dotaz, (x - okoli, x + okoli, y - okoli, y + okoli)).fetchall()
            nejlepsi = None
            for r in radky:
                body = self._rozbal(r["geom"])
                if len(body) < 2:
                    continue
                odsazeni, podil = self._vzdalenost_k_ose(x, y, body)
                if nejlepsi is None or odsazeni < nejlepsi[1]:
                    nejlepsi = (r, odsazeni, podil)
            if nejlepsi is not None and nejlepsi[1] <= okoli:
                return nejlepsi
        return None, None, None

    @staticmethod
    def _rozbal(blob):
        n = len(blob) // 8
        h = struct.unpack(f"<{2 * n}f", blob)
        return list(zip(h[0::2], h[1::2]))

    @staticmethod
    def _vzdalenost_k_ose(x, y, body):
        """Kolma vzdalenost bodu k lomene care a podil delky od zacatku."""
        celkem = sum(math.dist(body[i], body[i + 1])
                     for i in range(len(body) - 1)) or 1.0
        nejblize, podil, ujeto = float("inf"), 0.0, 0.0
        for i in range(len(body) - 1):
            (x1, y1), (x2, y2) = body[i], body[i + 1]
            dx, dy = x2 - x1, y2 - y1
            n = dx * dx + dy * dy
            t = 0.0 if n == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / n))
            d = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
            if d < nejblize:
                nejblize = d
                podil = (ujeto + t * math.hypot(dx, dy)) / celkem
            ujeto += math.hypot(dx, dy)
        return nejblize, podil

    # -- popis bodu ----------------------------------------------------

    def popis_bodu(self, lat=None, lon=None, x=None, y=None):
        """Vrati abioticke parametry bodu.

        Args:
            lat, lon: WGS84 ve stupnich
            x, y: alternativne primo S-JTSK

        Returns:
            dict s klici tok, idvt, strahler, km_od_pramene, plocha_povodi,
            umori, chp, odsazeni a poznamka; pri neuspechu dict s poznamkou
        """
        if x is None or y is None:
            if lat is None or lon is None:
                return {"poznamka": "Chybí souřadnice"}
            x, y = self._do_sjtsk(lat, lon)

        usek, odsazeni, podil = self.najdi_usek(x, y)
        if usek is None:
            return {"poznamka": "V okolí bodu není žádný vodní tok"}

        # hodnoty jsou vedene ke KONCI useku, dopocitame k poloze bodu
        km_konec = usek["km_konec"]
        delka_km = (usek["delka"] or 0) / 1000.0
        km = km_konec - delka_km * (1.0 - podil)

        plocha = usek["plocha_konec"]
        if plocha is not None and delka_km > 0:
            # plocha roste podel useku jen o prispevek jeho vlastniho okoli;
            # linearni interpolace je pro delku radove stovek metru dostatecna
            plocha_zacatek = self._plocha_predchoziho(usek["id"], plocha)
            plocha = plocha_zacatek + (plocha - plocha_zacatek) * podil

        poznamka = []
        if odsazeni > MEZ_ODSAZENI:
            poznamka.append(
                f"bod leží {odsazeni:.0f} m od osy toku - ověřte souřadnice")
        if usek["nazev"] in OFFSET_ZAHRANICI_NAZVY:
            poznamka.append("tok pramení v zahraničí, vzdálenost je kalibrovaná")

        return {
            "tok": usek["nazev"] or None,
            "tok_id": usek["tok_id"] or None,
            "idvt": usek["idvt"] or None,
            "usek_id": usek["id"],
            "strahler": usek["strahler"],
            "km_od_pramene": round(km, 3) if km is not None else None,
            "plocha_povodi": round(plocha, 3) if plocha is not None else None,
            "umori": usek["umori"],
            "umori_popis": POPIS_UMORI.get(usek["umori"]),
            "chp": usek["chp"],
            "odsazeni": round(odsazeni, 1),
            "poznamka": "; ".join(poznamka) or None,
        }

    def _plocha_predchoziho(self, usek_id, vychozi):
        """Plocha povodi na zacatku useku = SOUCET prispevku nad nim.

        Souctem, ne maximem: do zacatku useku vteka vsechno, co je nad nim,
        vcetne bocnich pritoku. Maximum by pod soutokem zahodilo mensi
        z ramen - napr. Bystry potok pod soutokem vychazel 1,84 misto 2,60.
        """
        r = self.conn.execute(
            "SELECT SUM(plocha_konec) FROM useky WHERE nasl = ?",
            (usek_id,)).fetchone()
        if r and r[0] is not None and r[0] <= vychozi:
            return r[0]
        return min(r[0], vychozi) if r and r[0] is not None else vychozi

    # -- osa toku pro vypocet sklonu -----------------------------------

    def osa_okolo(self, lat, lon, delka=400.0, vzorku=9):
        """Body na ose toku v okoli lokality - podklad pro podelny sklon.

        Jde proti proudu i po proudu podel navazujicich useku, dokud
        nenasbira `delka/2` metru na kazdou stranu, a vysledek rozdeli na
        `vzorku` stejne vzdalenych bodu.

        Prechod mezi useky se ridi sloupcem `nasl` (po proudu) a proti
        proudu se vybira predchudce s nejvetsi plochou povodi, aby se cesta
        drzela hlavniho toku a neuhnula do bocniho pritoku.

        Returns:
            list [(vzdalenost_po_proudu_m, x_sjtsk, y_sjtsk), ...]
            serazeny od nejvyssiho bodu k nejnizsimu; prazdny seznam,
            kdyz bod k siti nesedi
        """
        x, y = self._do_sjtsk(lat, lon)
        usek, _odsazeni, podil = self.najdi_usek(x, y)
        if usek is None:
            return []

        body = self._rozbal(usek["geom"])
        if len(body) < 2:
            return []

        # osa slozena z useku: nejdriv proti proudu, pak po proudu
        osa = list(body)
        pozice = self._delka_lomene(body) * podil

        dosah = delka / 2.0
        nahoru = pozice
        aktualni = usek["id"]
        while nahoru < dosah:
            pred = self.conn.execute(
                "SELECT geom, plocha_konec FROM useky WHERE nasl = ? "
                "ORDER BY plocha_konec DESC LIMIT 1", (aktualni,)).fetchone()
            if pred is None:
                break
            b = self._rozbal(pred["geom"])
            if len(b) < 2:
                break
            osa = b[:-1] + osa
            pridano = self._delka_lomene(b)
            nahoru += pridano
            pozice += pridano
            aktualni = self.conn.execute(
                "SELECT id FROM useky WHERE nasl = ? "
                "ORDER BY plocha_konec DESC LIMIT 1", (aktualni,)).fetchone()[0]

        dolu = self._delka_lomene(osa) - pozice
        aktualni = usek["nasl"]
        while dolu < dosah and aktualni:
            dalsi = self.conn.execute(
                "SELECT id, nasl, geom FROM useky WHERE id = ?",
                (aktualni,)).fetchone()
            if dalsi is None:
                break
            b = self._rozbal(dalsi["geom"])
            if len(b) < 2:
                break
            osa = osa + b[1:]
            dolu += self._delka_lomene(b)
            aktualni = dalsi["nasl"]

        od = max(0.0, pozice - dosah)
        do = min(self._delka_lomene(osa), pozice + dosah)
        if do - od < 10:
            return []
        krok = (do - od) / (vzorku - 1)
        return [(od + i * krok - pozice,) + self._bod_na_ose(osa, od + i * krok)
                for i in range(vzorku)]

    @staticmethod
    def _delka_lomene(body):
        return sum(math.dist(body[i], body[i + 1]) for i in range(len(body) - 1))

    @staticmethod
    def _bod_na_ose(body, vzdalenost):
        """Souradnice bodu v dane vzdalenosti od zacatku lomene cary."""
        ujeto = 0.0
        for i in range(len(body) - 1):
            d = math.dist(body[i], body[i + 1])
            if ujeto + d >= vzdalenost or i == len(body) - 2:
                t = 0.0 if d == 0 else min(1.0, (vzdalenost - ujeto) / d)
                return (body[i][0] + t * (body[i + 1][0] - body[i][0]),
                        body[i][1] + t * (body[i + 1][1] - body[i][1]))
            ujeto += d
        return body[-1]

    # -- pomocne -------------------------------------------------------

    def statistika(self):
        r = self.conn.execute(
            "SELECT COUNT(*) n, MAX(km_konec) km, MAX(plocha_konec) p, "
            "MAX(strahler) s FROM useky").fetchone()
        return {"useku": r["n"], "nejdelsi_tok_km": r["km"],
                "nejvetsi_povodi_km2": r["p"], "nejvyssi_strahler": r["s"]}


#: Nazvy toku s kalibrovanym offsetem - jen pro poznamku ve vysledku.
OFFSET_ZAHRANICI_NAZVY = {
    "Ohře", "Studená Vltava", "Divoká Orlice", "Malše", "Dračice",
}


def popis_bodu(lat, lon, cesta=None):
    """Jednorazovy dotaz bez drzeni spojeni."""
    with RicniSit(cesta) as sit:
        return sit.popis_bodu(lat, lon)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        lat, lon = float(sys.argv[1]), float(sys.argv[2])
        with RicniSit() as s:
            for k, v in s.popis_bodu(lat, lon).items():
                print(f"  {k:16s} {v}")
    else:
        with RicniSit() as s:
            print(s.statistika())
