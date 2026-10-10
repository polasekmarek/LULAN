"""
Ryby - toky, ekologicky stav (cesky multimetricky index CZI).

Metodika:
    Janac M. a kol. (2019): Metodika hodnoceni ekologickeho stavu utvaru
    povrchovych vod tekoucich (kategorie reka) pomoci biologicke slozky ryby.
    metodiky/OOV_hodnoceni_ryby_20191231.pdf

Princip
-------
Profil se podle umori, nadmorske vysky a Strahlerova radu zaradi do jednoho
ze sedmi typu toku A-G (viz ryby_typologie). Pro kazdy typ ma metodika
vlastni sadu hornich mezi a vah ctyr metrik (Tab. 3):

    TD   pocet typickych taxonu     - klesa se zatizenim
    AR   abundance reofilu          - klesa se zatizenim
    ND1  pocet/pritomnost nezadoucich taxonu  - stoupa se zatizenim
    ND2  podil nezadoucich taxonu             - stoupa se zatizenim

                w1*TD_EQR + w2*AR_EQR + w3*ND1_EQR + w4*ND2_EQR
        CZI =  -------------------------------------------------
                                    4

Jmenovatel je v metodice uveden jako konstanta 4, nikoli jako soucet vah.
Soucet vah je ale v kazdem typu toku presne 4,0, takze jde o totez -
zapisujeme proto delenim souctem vah, aby vzorec zustal spravny
i pri odlisnych vahach pri hodnoceni potencialu.

Zvlastnosti proti makrozoobentosu
---------------------------------
* Vzorky se NEadjustuji - adjustacni predpisy jsou jen pro MZB.
* Hodnotici jednotkou je jeden vzorek; metodika (kap. 4) uvadi, ze vysledne
  hodnoceni profilu je dano jednou hodnotou CZI v danem roce a lokalite,
  sezonni prumerovani se tedy nedela.
* Tridy stavu se urcuji OSTROU nerovnosti (0,8 < CZI pro prvni tridu,
  Tab. 5), zatimco u makrozoobentosu plati CZI >= mez.
* Prazdny vzorek dava CZI = 0 (5. trida) - viz kap. 3.
* Toky 1.-3. Strahlerova radu se nehodnoti vubec.
"""

from __future__ import annotations

from .common import (
    HRANICE_STAV,
    klasifikuj,
    smaz_vysledky,
    zapis_vysledky,
)
from .ryby_metriky import eqr, nacti_vzorek, spocitej_metriky
from .ryby_typologie import popis_typu, urci_typ

try:
    from PyQt6.QtSql import QSqlQuery
except ImportError:  # pragma: no cover
    QSqlQuery = None


#: Metriky CZI v poradi, v jakem se zapisuji do vysledku.
VSECHNY_METRIKY = ["RY_TD", "RY_AR", "RY_ND1", "RY_ND2"]

#: Metriky, ktere stoupaji se zatizenim - EQR = 1 - X/max.
PENALIZUJICI = ("RY_ND1", "RY_ND2")

#: Horni meze a vahy metrik podle typu toku (Janac a kol. 2019, Tab. 3).
#:
#: {typ: {metrika: (horni_mez, vaha, transformace)}}
#:
#: Dolni mez je u vsech metrik a typu nula, proto se neuvadi.
EQR_TABLE = {
    "A": {
        "RY_TD":  (2,   1.6, "ln5"),
        "RY_AR":  (50,  1.2, None),
        "RY_ND1": (4,   0.8, "ln10"),
        "RY_ND2": (0.5, 0.4, "ln100"),
    },
    "B": {
        "RY_TD":  (4,   1.6, None),
        "RY_AR":  (100, 1.2, None),
        "RY_ND1": (4,   0.8, "ln10"),
        "RY_ND2": (0.5, 0.4, "ln100"),
    },
    "C": {
        "RY_TD":  (5,   1.6, None),
        "RY_AR":  (100, 1.2, None),
        "RY_ND1": (4,   0.8, "ln10"),
        "RY_ND2": (0.5, 0.4, "ln100"),
    },
    "D": {
        "RY_TD":  (5,     1.8, None),
        "RY_AR":  (50,    1.2, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.6, "ln100"),
    },
    "E": {
        "RY_TD":  (6,     2.2, None),
        "RY_AR":  (200,   1.0, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.4, "ln100"),
    },
    "F": {
        "RY_TD":  (8,     2.2, None),
        "RY_AR":  (200,   1.0, None),
        "RY_ND1": (1,     0.4, None),
        "RY_ND2": (1 / 3, 0.4, "ln100"),
    },
    "G": {
        "RY_TD":  (12,    2.6, None),
        "RY_AR":  (150,   0.8, None),
        "RY_ND1": (1,     0.2, None),
        "RY_ND2": (1 / 3, 0.4, "ln100"),
    },
}


def nacti_kontext(sample_id, db_connection):
    """Nacte datum odberu, kod lokality, umori, nadm. vysku a Strahleruv rad."""
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT s.DATE, s.LOC_ID, l.UMORI, l.MNM, l.STRAHLER
        FROM samples s
        LEFT JOIN loc l ON s.LOC_ID = l.KOD
        WHERE s.SAMPLE_ID = ?
        """
    )
    query.addBindValue(sample_id)
    if not query.exec() or not query.next():
        return None
    return {
        "date": query.value(0),
        "loc_id": query.value(1),
        "umori": query.value(2),
        "mnm": query.value(3),
        "strahler": query.value(4),
    }


def spocitej_czi(metriky, radek):
    """Prevede metriky na EQR a slozi je do indexu CZI.

    Args:
        metriky: vysledek spocitej_metriky()
        radek: {metrika: (horni_mez, vaha, transformace)}

    Returns:
        (eqr_hodnoty, czi) - eqr_hodnoty je dict {metrika_EQR: hodnota}
    """
    eqr_hodnoty = {}
    citatel = 0.0
    jmenovatel = 0.0

    for metrika, (mez, vaha, transformace) in radek.items():
        hodnota = eqr(
            metriky.get(metrika), mez,
            penalizujici=metrika in PENALIZUJICI,
            transformace=transformace,
        )
        if hodnota is None:
            continue
        eqr_hodnoty[f"{metrika}_EQR"] = round(hodnota, 5)
        citatel += vaha * hodnota
        jmenovatel += vaha

    czi = round(citatel / jmenovatel, 5) if jmenovatel > 0 else None
    return eqr_hodnoty, czi


def hodnoceni(sample_id, db_connection, potencial=False,
              tabulka=None, typ_toku=None, popis="Ekologicky stav"):
    """Vypocte hodnoceni vzorku ryb podle ceskeho multimetrickeho indexu.

    Args:
        sample_id: ID vzorku
        db_connection: QSqlDatabase
        potencial: False = ekologicky stav, True = ekologicky potencial
            (lisi se pouze hranicemi trid; meze a vahy dodava `tabulka`)
        tabulka: prevodni tabulka {metrika: (mez, vaha, transformace)};
            None = tabulka pro dany typ toku podle Tab. 3
        typ_toku: vynuceny typ toku - modul ryby_potencial jim prerazuje
            profily nekterych kategorii HMWB (napr. sekundarni pstruhova
            pasma se hodnoti jako typ A)
        popis: text do poznamky

    Returns:
        dict s hodnotami metrik, jejich EQR, RYBY_CELKEM, RYBY_CLASS
        a RYBY_POZN
    """
    try:
        ctx = nacti_kontext(sample_id, db_connection)
        if ctx is None:
            return {"RYBY_POZN": "Vzorek nebo lokalita nenalezena"}
        if not ctx["loc_id"]:
            return {"RYBY_POZN": "Vzorek nema prirazenou lokalitu"}

        typ = typ_toku
        if typ is None:
            typ, duvod = urci_typ(ctx["umori"], ctx["mnm"], ctx["strahler"])
            if typ is None:
                # duvod uz predponu "Nehodnoceno:" obsahuje - viz urci_typ()
                return {"RYBY_POZN": duvod}

        radek = tabulka if tabulka is not None else EQR_TABLE.get(typ)
        if radek is None:
            return {"RYBY_POZN": f"Pro typ toku {typ} neni prevodni tabulka"}

        data, taxalist = nacti_vzorek(db_connection, sample_id)

        # "V pripade, ze vzorek neobsahuje zadne ryby, CZI neni mozno
        #  matematicky vypocitat a index automaticky nabyva hodnoty 0."
        if not data:
            czi, metriky, eqr_hodnoty = 0.0, {}, {}
            pozn_prazdny = ", vzorek bez ryb - CZI = 0"
        else:
            metriky = spocitej_metriky(data, taxalist, typ)
            eqr_hodnoty, czi = spocitej_czi(metriky, radek)
            pozn_prazdny = ""

        trida = klasifikuj(
            czi, potencial=potencial,
            hranice=None if potencial else HRANICE_STAV,
            ostre=True,   # Tab. 5 pouziva ostrou nerovnost i u stavu
        )

        pozn = (
            f"{popis}. Typ toku: {typ} ({popis_typu(typ)}), "
            f"metrik pouzito: {len(eqr_hodnoty)}/{len(radek)}"
        )
        if data:
            pozn += f", nezadouci taxony: {metriky['_nezadouci']}"
        # Taxon bez priznaku R/EL/I nevstoupi do zadne metriky, ale do
        # celkove abundance ano - u ND1 a ND2 tak tise zvysuje skore.
        # Viz ryby_metriky.bez_priznaku().
        neznane = metriky.get("_bez_priznaku") or []
        if neznane:
            pozn += (f"; POZOR: metodika neskoruje "
                     f"{', '.join(neznane)} - do metrik nevstupuje")
        pozn += pozn_prazdny

        _zapis(db_connection, sample_id, metriky, eqr_hodnoty,
               czi, trida, pozn, typ)

        vysledek = {
            m: metriky[m] for m in VSECHNY_METRIKY if m in metriky
        }
        vysledek.update(eqr_hodnoty)
        vysledek["RYBY_CELKEM"] = czi
        vysledek["RYBY_CLASS"] = trida
        vysledek["RYBY_TYP"] = typ
        vysledek["RYBY_POZN"] = pozn
        vysledek["RYBY_TYP_HODNOCENI"] = "POTENCIAL" if potencial else "STAV"
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"RYBY_POZN": f"Kriticka chyba: {e}"}


def _zapis(db_connection, sample_id, metriky, eqr_hodnoty,
           czi, trida, pozn, typ):
    """Zapise metriky a multimetriku do tabulky `results`."""
    smaz_vysledky(
        db_connection, sample_id,
        VSECHNY_METRIKY + ["RY_TA", "RYBY_CELKEM"],
    )

    radky = [
        {
            "metric": m,
            "val": metriky[m],
            "eqr": eqr_hodnoty.get(f"{m}_EQR"),
            "class": None,
            "pozn": f"Typ toku: {typ}",
        }
        for m in VSECHNY_METRIKY + ["RY_TA"]
        if m in metriky
    ]
    radky.append(
        {
            "metric": "RYBY_CELKEM",
            "val": czi,
            "eqr": czi,
            "class": trida,
            "pozn": pozn,
        }
    )
    zapis_vysledky(db_connection, sample_id, radky)
