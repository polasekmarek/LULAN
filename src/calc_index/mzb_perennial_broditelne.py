"""
MZB - staletekouci (perennial) broditelne toky, ekologicky stav / potencial.

Postup vypoctu:
    1. urceni sezony a typu adjustace podle data odberu
    2. urceni typu lokality podle nadmorske vysky a Strahlerova radu
    3. nacteni a adjustace dat vzorku (METR pro metriky, PRED pro B-index)
    4. vypocet metrik MB01-MB15
    5. prevod metrik na EQR podle tabulky v mzb_perennial_broditelne_table.py
    6. vypocet multimetriky jako vazeneho prumeru
    7. klasifikace a zapis do tabulky `results`
"""

from __future__ import annotations

from PyQt6.QtSql import QSqlQuery

from .common import (
    klasifikuj,
    preved_na_eqr,
    smaz_vysledky,
    to_float,
    urci_sezonu,
    vazeny_prumer,
    zapis_vysledky,
    je_platna,
)
from .mzb_metrics import priprav_data, spocitej_metriky
from .mzb_perennial_broditelne_table import EQR_TABLE

#: Vsechny metriky, ktere se mohou objevit ve vysledcich.
VSECHNY_METRIKY = [f"MB{i:02d}" for i in range(1, 19)]


#: Pocitat s hornimi mezemi, ktere u typu 2-1 jaro pouziva IS ARROW?
#:
#: ARROW u tohoto jednoho typu pouziva pro RETI a Margalefovu diverzitu
#: horni meze typu 3-1 (0,86 a 8,4) misto hodnot z Tab. 3 (0,81 a 7,7).
#:
#: Metodika ma pritom pravdu - jeji radek pro typ 2-1 je vnitrne
#: konzistentni. Hranicni hodnoty trid vychazeji presne z mezi 0,81 a 7,7:
#:
#:     Margalef:  0,4 + 0,8 * (7,7 - 0,4) = 6,24   (Tab. 3 uvadi 6,24)
#:                0,4 + 0,6 * (7,7 - 0,4) = 4,78   (Tab. 3 uvadi 4,78)
#:     s mezi 8,4 by vysly 6,80 a 5,20, coz jsou hodnoty radku 3-1
#:
#: Vychozi je proto metodika. Prepnutim na True se LULAN srovna s ARROW -
#: hodi se pri porovnavani vysledku, ne pri ostrem hodnoceni.
MEZE_DLE_ARROW = False

#: Horni meze, ktere ARROW u typu 2-1 pouziva misto hodnot z Tab. 3.
MEZE_ARROW_2_1 = {"MB03": 0.86, "MB05": 8.4}


def _uprav_meze_dle_arrow(radek, typ_lokality, sezona):
    """Vrati radek prevodni tabulky s mezemi podle IS ARROW.

    Meni se pouze typ 2-1 na jare; ostatni skupiny maji meze shodne
    (overeno zpetnou regresi EQR na hodnotu metriky, R2 = 1,000000).
    """
    if not MEZE_DLE_ARROW or typ_lokality != "2-1" or sezona != "J":
        return radek

    upraveny = dict(radek)
    for metrika, mez in MEZE_ARROW_2_1.items():
        if metrika in upraveny:
            dolni, _horni, invertovat, vaha = upraveny[metrika]
            upraveny[metrika] = (dolni, mez, invertovat, vaha)
    return upraveny


def urci_typ_lokality(mnm, strahler):
    """Urci typ lokality podle nadmorske vysky [m n.m.] a Strahlerova radu.

    Hodnoty se prevadi na cislo - z databaze i z GUI mohou prijit jako
    retezec (napr. "4" nebo "412,5"), coz by pri porovnani spadlo na
    TypeError: '<=' not supported between 'int' and 'str'.

    Returns:
        retezec typu ('2-1', '3-1', '1-2', '2-2', '3-2', '12-3'),
        nebo None pokud kombinace neodpovida zadnemu typu
    """
    mnm = to_float(mnm)
    strahler = to_float(strahler)
    if mnm is None or strahler is None:
        return None

    if 1 <= strahler <= 3:
        if 200 <= mnm < 500:
            return "2-1"
        if 500 <= mnm < 800:
            return "3-1"
    elif 4 <= strahler <= 6:
        if 0 <= mnm < 200:
            return "1-2"
        if 200 <= mnm < 500:
            return "2-2"
        if 500 <= mnm < 800:
            return "3-2"
    elif 7 <= strahler <= 9:
        if 0 <= mnm < 500:
            return "12-3"
    return None


def urci_adjustace(sezona, typ_lokality):
    """Urci nazvy adjustacnich sad pro metriky (METR) a pro B-index (PRED)."""
    if sezona == "J":
        return "METR_J", "PRED_J"
    # podzim: typ 12-3 ma vlastni podzimni adjustaci
    metr = "METR_P_12_3" if typ_lokality == "12-3" else "METR_P"
    return metr, "PRED_P"


def _nacti_kontext(sample_id, db_connection):
    """Nacte datum odberu, kod lokality, nadmorskou vysku a Strahleruv rad."""
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT s.DATE, s.LOC_ID, l.MNM, l.STRAHLER
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
        "mnm": query.value(2),
        "strahler": query.value(3),
    }


def hodnoceni(sample_id, db_connection, potencial=False,
              tabulka=None, popis="Ekologicky stav"):
    """Vypocte MZB hodnoceni pro staletekouci broditelny tok.

    Args:
        sample_id: ID vzorku
        db_connection: QSqlDatabase
        potencial: False = ekologicky stav, True = ekologicky potencial
        tabulka: prevodni tabulka EQR; None = tabulka pro hodnoceni stavu.
            Modul mzb_potencial_broditelne.py sem predava tabulku
            s mezemi maximalniho ekologickeho potencialu.
        popis: text do poznamky, odlisujici stav od potencialu

    Returns:
        dict s hodnotami metrik, EQR, MZB_CELKEM, MZB_CLASS a MZB_POZN
    """
    if tabulka is None:
        tabulka = EQR_TABLE
    try:
        ctx = _nacti_kontext(sample_id, db_connection)
        if ctx is None:
            return {"MZB_POZN": "Vzorek nebo lokalita nenalezena"}
        if not ctx["date"] or not ctx["loc_id"]:
            return {"MZB_POZN": "Chybi datum odberu nebo kod lokality"}

        sezona = urci_sezonu(ctx["date"])
        if sezona is None:
            return {"MZB_POZN": f"Neplatny format data: {ctx['date']}"}

        typ_lokality = urci_typ_lokality(ctx["mnm"], ctx["strahler"])
        if typ_lokality is None:
            # Rozlisit chybejici data od kombinace mimo typologii - je to
            # rozdil mezi "doplnte parametry" a "metodika tenhle tok
            # nehodnoti".
            chybi = [
                nazev for nazev, hodnota in
                (("nadmořská výška", ctx["mnm"]), ("Strahlerův řád",
                                                   ctx["strahler"]))
                if to_float(hodnota) is None
            ]
            if chybi:
                duvod = ("Nehodnoceno: chybí abiotické parametry lokality ("
                         + ", ".join(chybi) + ")")
            else:
                duvod = (
                    f"Nehodnoceno: kombinace {ctx['mnm']} m n. m. a "
                    f"{ctx['strahler']}. Strahlerova řádu neodpovídá žádnému "
                    f"typu lokality podle metodiky"
                )
            return {"MZB_POZN": duvod}

        metr_adj, pred_adj = urci_adjustace(sezona, typ_lokality)

        # klic do prevodni tabulky - u typu 2-1 a 3-1 se Strahler nerozlisuje
        klic = (typ_lokality, sezona, ctx["strahler"])
        if klic not in tabulka:
            klic = (typ_lokality, sezona, None)
        radek = tabulka.get(klic)
        if radek is None:
            return {
                "MZB_POZN": (
                    f"Pro typ {typ_lokality}, sezonu {sezona} a Strahler "
                    f"{ctx['strahler']} neni definovana prevodni tabulka"
                )
            }
        radek = _uprav_meze_dle_arrow(radek, typ_lokality, sezona)

        priprava = priprav_data(db_connection, sample_id, metr_adj, pred_adj)
        if priprava is None:
            return {"MZB_POZN": "Ve vzorku nejsou pouzitelna taxonomicka data"}

        metriky = spocitej_metriky(
            priprava, db_connection, ctx["loc_id"], sezona
        )

        eqr_hodnoty = preved_na_eqr(metriky, radek)
        multimetrika, pouzite = vazeny_prumer(eqr_hodnoty, radek)
        trida = klasifikuj(multimetrika, potencial)

        pozn = (
            f"{popis}. Typ: {typ_lokality}, Sezona: {sezona}, "
            f"METR: {metr_adj}, PRED: {pred_adj}, "
            f"metrik pouzito: {len(pouzite)}/{len(radek)}"
        )
        chybejici = sorted(set(radek) - set(pouzite))
        if chybejici:
            pozn += f", chybi: {','.join(chybejici)}"
        pozn += priprava.get("poznamka", "")

        _zapis(
            db_connection, sample_id, metriky, eqr_hodnoty,
            multimetrika, trida, pozn, typ_lokality, sezona,
        )

        vysledek = {m: metriky.get(m) for m in VSECHNY_METRIKY if m in metriky}
        vysledek.update(eqr_hodnoty)
        vysledek["MZB_CELKEM"] = multimetrika
        vysledek["MZB_CLASS"] = trida
        vysledek["MZB_POZN"] = pozn
        vysledek["MZB_TYP_HODNOCENI"] = "POTENCIAL" if potencial else "STAV"
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"MZB_POZN": f"Kriticka chyba: {e}"}


def _zapis(db_connection, sample_id, metriky, eqr_hodnoty,
           multimetrika, trida, pozn, typ_lokality, sezona):
    """Zapise metriky a multimetriku do tabulky `results`."""
    smaz_vysledky(db_connection, sample_id, VSECHNY_METRIKY + ["MZB_CELKEM"])

    radky = [
        {
            "metric": m,
            "val": metriky[m],
            "eqr": eqr_hodnoty.get(f"{m}_EQR"),
            "class": None,
            "pozn": f"Skupina: {typ_lokality}, Sezona: {sezona}",
        }
        for m in VSECHNY_METRIKY
        if je_platna(metriky.get(m))
    ]
    radky.append(
        {
            "metric": "MZB_CELKEM",
            "val": multimetrika,
            "eqr": multimetrika,
            "class": trida,
            "pozn": pozn,
        }
    )
    zapis_vysledky(db_connection, sample_id, radky)
