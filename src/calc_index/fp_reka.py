"""
Fytoplankton (FP) - toky, ekologicky stav i potencial.

Metodika:
    Desortova B. a kol. (2019): Metodika hodnoceni ekologickeho stavu utvaru
    povrchovych vod tekoucich pomoci biologicke slozky fytoplankton. VUV TGM.
    metodiky/OOV-metodika-FP_aktualizace-20191014.pdf

    Opatrilova L. a kol. (2013): Metoda pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie reka, Tab. 9.

Princip
-------
Vsechny nalezene taxony se agreguji do tri taxonomickych trid a spocita se
jejich podil na celkovem poctu jedincu ve vzorku. Ctvrtou metrikou je
koncentrace chlorofylu-a jako miry celkove biomasy.

    FP01  % Bacillariophyceae (rozsivky)   - klesa se zatizenim
    FP02  % Cyanophyceae (sinice)          - stoupa se zatizenim
    FP03  % Chlorophyceae (zelene rasy)    - stoupa se zatizenim
    FP04  chlorofyl-a [ug/l]               - stoupa se zatizenim

Podily se vyjadruji jako zlomek 0-1 (0,85 = 85 %), stejne jako meze
v tabulkach metodiky.

Poradi vypoctu
--------------
Metodika (kap. 3): "Pro hodnoceni fytoplanktonu jsou pouzity prumery
jednotlivych hodnot metrik namerenych za vegetacni sezonu od brezna do
rijna."

Nejprve se tedy zprumeruji HODNOTY METRIK pres celou vegetacni sezonu daneho
roku na dane lokalite - vcetne chlorofylu-a - a teprve z techto prumeru se
pocitaji EQR. Poradi je podstatne: EQR se orezava do <0, 1>, takze prumer
EQR z jednotlivych vzorku by dal jiny vysledek nez EQR z prumeru metrik.

Hodnoticí jednotkou proto neni vzorek, ale dvojice lokalita + rok. Vsechny
vzorky teze lokality a roku dostanou shodny vysledek; sezonni prumery se
pocitaji jen jednou a drzi se v cache.

Multimetrika je prosty prumer EQR vsech ctyr metrik, tridy jsou standardni
petistupnove s ostrou nerovnosti (Tab. 3).

Omezeni pouziti
---------------
* pouze toky 7.-9. Strahlerova radu (kategorie 3 dle Langhammera) - v tocich
  nizsiho radu je mnozstvi fytoplanktonu zanedbatelne
* pouze vegetacni sezona brezen-rijen
* vzorek pro stanoveni chlorofylu-a ma byt odebran soubezne se vzorkem
  fytoplanktonu
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtSql import QSqlQuery

from .common import (
    je_platna,
    klasifikuj,
    nacti_data_vzorku,
    nacti_taxalist,
    patri_do_skupiny,
    preved_na_eqr,
    prosty_prumer,
    smaz_vysledky,
    to_float,
    vyres_synonyma,
    zapis_vysledky,
)

#: Fytoplankton se urcuje ze stejneho taxonomickeho seznamu jako fytobentos -
#: obsahuje jak sinice, tak zelene rasy i rozsivky vcetne cele hierarchie.
TAXALIST = "taxalist_fb"

#: Taxonomicke tridy, jejichz podil se pocita.
SKUPINY = {
    "FP01": ("Bacillariophyceae",),
    "FP02": ("Cyanophyceae",),
    "FP03": ("Chlorophyceae",),
}

#: Kod chemickeho parametru pro chlorofyl-a (extrakce ethanolem).
CHLOROFYL_KOD = "IC0000"

METRIKY = ["FP01", "FP02", "FP03", "FP04"]

NAZVY = {
    "FP01": "% Bacillariophyceae",
    "FP02": "% Cyanophyceae",
    "FP03": "% Chlorophyceae",
    "FP04": "chlorofyl-a [ug/l]",
}

#: Strahlerovy rady, pro ktere se fytoplankton hodnoti.
HODNOCENE_RADY = (7, 8, 9)

#: Vegetacni sezona - mesice, ze kterych se vzorky hodnoti.
VEGETACNI_SEZONA = range(3, 11)   # brezen az rijen

#: Prevodni tabulka pro hodnoceni STAVU.
#: Zdroj: metodika FP 2019, Tab. 2.
#:
#: Format {metrika: {Strahleruv rad: (dolni_mez, horni_mez, invertovat, vaha)}}
#:
#: Poznamka k poradi mezi: metodika pouziva pro metriky stoupajici se
#: zatizenim vzorec EQR = (dolni_mez - vysledek) / (dolni_mez - horni_mez).
#: To je totez jako (vysledek - dolni) / (horni - dolni), kde horni mez je
#: mensi nez dolni - proto u techto metrik nasleduje po dolni mezi mensi
#: cislo a invertovat je False.
EQR_TABLE_STAV = {
    "FP01": {  # % Bacillariophyceae - klesa se zatizenim
        7: (0.33, 0.85, False, 1.0),
        8: (0.33, 0.85, False, 1.0),
        9: (0.33, 0.85, False, 1.0),
    },
    "FP02": {  # % Cyanophyceae - stoupa se zatizenim
        7: (0.3, 0.0, False, 1.0),
        8: (0.3, 0.011, False, 1.0),
        9: (0.3, 0.012, False, 1.0),
    },
    "FP03": {  # % Chlorophyceae - stoupa se zatizenim
        7: (0.38, 0.1, False, 1.0),
        8: (0.38, 0.12, False, 1.0),
        9: (0.38, 0.12, False, 1.0),
    },
    "FP04": {  # chlorofyl-a - stoupa se zatizenim
        7: (98.0, 4.8, False, 1.0),
        8: (98.0, 12.0, False, 1.0),
        9: (98.0, 15.0, False, 1.0),
    },
}

#: Prevodni tabulka pro hodnoceni POTENCIALU silne ovlivnenych utvaru.
#: Zdroj: metodika potencialu 2013, Tab. 9.
#:
#: Lisi se pouze u chlorofylu-a: v silne ovlivnenych utvarech se ocekava
#: delsi zdrzeni vody a tim vyssi biomasa, horni mez je proto mirnejsi.
#: Podily taxonomickych skupin zustavaji shodne s hodnocenim stavu.
EQR_TABLE_POTENCIAL = {
    "FP01": dict(EQR_TABLE_STAV["FP01"]),
    "FP02": dict(EQR_TABLE_STAV["FP02"]),
    "FP03": dict(EQR_TABLE_STAV["FP03"]),
    "FP04": {
        7: (98.0, 23.0, False, 1.0),
        8: (98.0, 29.0, False, 1.0),
        9: (98.0, 32.0, False, 1.0),
    },
}


def _tabulka_pro_rad(tabulka, strahler):
    """Vybere z tabulky radek pro dany Strahleruv rad."""
    return {
        metrika: varianty[strahler]
        for metrika, varianty in tabulka.items()
        if strahler in varianty
    }


def _nacti_kontext(sample_id, db_connection):
    """Nacte datum odberu, lokalitu a Strahleruv rad."""
    query = QSqlQuery(db_connection)
    query.prepare(
        """
        SELECT s.DATE, s.LOC_ID, l.STRAHLER
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
        "strahler": query.value(2),
    }


#: Podminka omezujici dotaz na vegetacni sezonu daneho roku.
#: Datum je ulozene jako DD.MM.RRRR, mesic je tedy na pozici 4-5.
_SEZONA_SQL = (
    "s.DATE LIKE ? "
    "AND CAST(substr(s.DATE, 4, 2) AS INTEGER) BETWEEN ? AND ?"
)


def nacti_chlorofyl(db_connection, loc_id, rok):
    """Prumer koncentrace chlorofylu-a za vegetacni sezonu daneho roku.

    Bere v uvahu vsechna mereni kodu IC0000 na dane lokalite, at uz jsou
    navazana na vzorek fytoplanktonu, nebo na samostatny chemicky vzorek.

    Returns:
        (prumer, pocet_mereni) - prumer je None, kdyz nejsou data
    """
    if rok is None:
        return None, 0

    query = QSqlQuery(db_connection)
    query.prepare(
        f"""
        SELECT AVG(CAST(d.val AS REAL)), COUNT(*)
        FROM data d
        JOIN samples s ON d.sample = s.SAMPLE_ID
        WHERE s.LOC_ID = ? AND {_SEZONA_SQL} AND d.name = ?
        """
    )
    query.addBindValue(loc_id)
    query.addBindValue(f"%.{rok}")
    query.addBindValue(VEGETACNI_SEZONA.start)
    query.addBindValue(VEGETACNI_SEZONA.stop - 1)
    query.addBindValue(CHLOROFYL_KOD)

    if query.exec() and query.next():
        return to_float(query.value(0)), query.value(1) or 0
    return None, 0


def vzorky_sezony(db_connection, loc_id, rok):
    """Vrati ID vzorku fytoplanktonu z vegetacni sezony daneho roku."""
    query = QSqlQuery(db_connection)
    query.prepare(
        f"""
        SELECT s.SAMPLE_ID
        FROM samples s
        WHERE s.LOC_ID = ? AND s.TYP = 'FP' AND {_SEZONA_SQL}
        ORDER BY s.SAMPLE_ID
        """
    )
    query.addBindValue(loc_id)
    query.addBindValue(f"%.{rok}")
    query.addBindValue(VEGETACNI_SEZONA.start)
    query.addBindValue(VEGETACNI_SEZONA.stop - 1)

    vzorky = []
    if query.exec():
        while query.next():
            vzorky.append(query.value(0))
    return vzorky


def sezonni_prumery(db_connection, loc_id, rok):
    """Spocita prumery metrik za vegetacni sezonu daneho roku na lokalite.

    Podily taxonomickych skupin se spocitaji pro kazdy vzorek zvlast
    a nasledne zprumeruji; chlorofyl-a se prumeruje ze vsech mereni sezony.

    Vysledek se cachuje, aby se pro kazdy vzorek teze lokality a roku
    nepocital znovu.

    Returns:
        (metriky, prehled) - metriky je dict {metrika: prumer},
        prehled obsahuje pocty vzorku a mereni a nedohledane taxony
    """
    from .common import cache_ziskej

    def spocitej():
        vzorky = vzorky_sezony(db_connection, loc_id, rok)

        po_vzorcich = []
        nedohledane = set()
        celkem_jedincu = 0
        celkem_taxonu = 0

        for sid in vzorky:
            podily, prehled = spocitej_podily(db_connection, sid)
            if podily is None:
                continue
            po_vzorcich.append(podily)
            nedohledane.update(prehled["nedohledane_nazvy"])
            celkem_jedincu += prehled["celkem"]
            celkem_taxonu += prehled["taxonu"]

        metriky = {}
        for metrika in SKUPINY:
            hodnoty = [p[metrika] for p in po_vzorcich if p.get(metrika) is not None]
            metriky[metrika] = (
                round(sum(hodnoty) / len(hodnoty), 4) if hodnoty else None
            )

        chlorofyl, pocet_mereni = nacti_chlorofyl(db_connection, loc_id, rok)
        metriky["FP04"] = round(chlorofyl, 3) if chlorofyl is not None else None

        prehled = {
            "vzorku": len(po_vzorcich),
            "vzorku_celkem": len(vzorky),
            "mereni_chlorofylu": pocet_mereni,
            "jedincu": celkem_jedincu,
            "taxonu": celkem_taxonu,
            "nedohledane_nazvy": sorted(nedohledane),
        }
        return metriky, prehled

    return cache_ziskej(("fp_sezona", loc_id, rok), spocitej)


def spocitej_podily(db_connection, sample_id):
    """Spocita podil jednotlivych taxonomickych trid na poctu jedincu.

    Jmenovatelem je celkovy pocet jedincu ve vzorku, tedy vcetne taxonu,
    ktere se nepodarilo dohledat v taxonomickem seznamu. Kdyby se pocitalo
    jen z dohledanych taxonu, kazda mezera v seznamu by vsechny tri podily
    nafoukla - u rozsivek by stav vychazel lepsi, u sinic a zelenych ras
    horsi, nez ve skutecnosti je.

    Returns:
        (podily, prehled) - podily je dict {metrika: zlomek}, prehled je dict
        s klici celkem, taxonu, nedohledano_jedincu, nedohledano_taxonu;
        podily je None, kdyz vzorek neobsahuje pouzitelna data
    """
    taxa_data = nacti_data_vzorku(db_connection, sample_id)
    if not taxa_data:
        return None, {}

    celkem = sum(z["abundance"] for z in taxa_data)
    if celkem <= 0:
        return None, {}

    taxalist = nacti_taxalist(db_connection, TAXALIST, [])
    by_name = taxalist["by_name"]

    nedohledane = [z for z in taxa_data if z["taxon_name"] not in by_name]
    data = vyres_synonyma(taxa_data, by_name)

    by_id = taxalist["by_id"]
    cache = {}

    podily = {}
    for metrika, skupiny in SKUPINY.items():
        soucet = sum(
            abundance
            for taxon_id, abundance in data.items()
            if patri_do_skupiny(taxon_id, skupiny, by_id, cache)
        )
        podily[metrika] = round(soucet / celkem, 4)

    prehled = {
        "celkem": celkem,
        "taxonu": len(taxa_data),
        "nedohledano_jedincu": sum(z["abundance"] for z in nedohledane),
        "nedohledano_taxonu": len(nedohledane),
        "nedohledane_nazvy": [z["taxon_name"] for z in nedohledane],
    }
    return podily, prehled


def hodnoceni(sample_id, db_connection, potencial=False):
    """Vypocte FP hodnoceni pro tok.

    Args:
        potencial: True u silne ovlivnenych utvaru - pouzije se tabulka
            z metodiky potencialu a ctyrstupnova klasifikace
    """
    try:
        ctx = _nacti_kontext(sample_id, db_connection)
        if ctx is None:
            return {"FP_POZN": "Vzorek nebo lokalita nenalezena"}

        # Strahler muze z databaze prijit jako retezec ("8"), proto prevod -
        # jinak by test `strahler not in HODNOCENE_RADY` vzdy neuspel
        # a fytoplankton by se nespocital nikde.
        strahler = to_float(ctx["strahler"])
        strahler = int(strahler) if strahler is not None else None
        if strahler not in HODNOCENE_RADY:
            return {
                "FP_CELKEM": None,
                "FP_CLASS": None,
                "FP_POZN": (
                    f"Nehodnoceno: fytoplankton se hodnotí pouze v tocích "
                    f"7.–9. Strahlerova řádu, lokalita má řád {strahler}"
                ),
            }

        try:
            datum = datetime.strptime(ctx["date"], "%d.%m.%Y")
            rok, mesic = datum.year, datum.month
        except (TypeError, ValueError):
            return {"FP_POZN": f"Neplatny format data: {ctx['date']}"}

        if mesic not in VEGETACNI_SEZONA:
            return {
                "FP_CELKEM": None,
                "FP_CLASS": None,
                "FP_POZN": (
                    f"Vzorek z {ctx['date']} je mimo vegetacni sezonu "
                    f"(brezen-rijen), nebyl vyhodnocen"
                ),
            }

        # Metriky se prumeruji pres celou vegetacni sezonu daneho roku
        # a teprve z prumeru se pocitaji EQR (viz uvod modulu).
        metriky, prehled = sezonni_prumery(db_connection, ctx["loc_id"], rok)

        if prehled["vzorku"] == 0:
            return {"FP_POZN": "Ve vzorcich sezony nejsou pouzitelna taxonomicka data"}

        tabulka = _tabulka_pro_rad(
            EQR_TABLE_POTENCIAL if potencial else EQR_TABLE_STAV, strahler
        )
        eqr_hodnoty = preved_na_eqr(metriky, tabulka)
        multimetrika, pocet = prosty_prumer(eqr_hodnoty)
        trida = klasifikuj(multimetrika, potencial)

        pozn = (
            f"{'Potencial' if potencial else 'Stav'}, Strahler {strahler}, "
            f"sezona {rok} (brezen-rijen): prumer z {prehled['vzorku']} vzorku, "
            f"metrik pouzito: {pocet}/{len(METRIKY)}"
        )
        if metriky.get("FP04") is None:
            pozn += f"; chybi chlorofyl-a ({CHLOROFYL_KOD})"
        else:
            pozn += (
                f"; chlorofyl-a prumer z {prehled['mereni_chlorofylu']} mereni"
            )

        if prehled["nedohledane_nazvy"]:
            pozn += (
                f"; POZOR: {len(prehled['nedohledane_nazvy'])} taxonu sezony "
                f"neni v {TAXALIST}"
            )
            print(
                f"[FP] {ctx['loc_id']}/{rok}: v {TAXALIST} chybi "
                f"{', '.join(prehled['nedohledane_nazvy'][:5])}"
            )

        smaz_vysledky(db_connection, sample_id, METRIKY + ["FP_CELKEM"])
        radky = [
            {
                "metric": m,
                "val": metriky[m],
                "eqr": eqr_hodnoty.get(f"{m}_EQR"),
                "class": None,
                "pozn": NAZVY[m],
            }
            for m in METRIKY
            if je_platna(metriky.get(m))
        ]
        radky.append(
            {
                "metric": "FP_CELKEM",
                "val": multimetrika,
                "eqr": multimetrika,
                "class": trida,
                "pozn": pozn,
            }
        )
        zapis_vysledky(db_connection, sample_id, radky)

        vysledek = dict(metriky)
        vysledek.update(eqr_hodnoty)
        vysledek["FP_CELKEM"] = multimetrika
        vysledek["FP_CLASS"] = trida
        vysledek["FP_POZN"] = pozn
        vysledek["FP_TYP_HODNOCENI"] = "POTENCIAL" if potencial else "STAV"
        return vysledek

    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return {"FP_POZN": f"Kriticka chyba: {e}"}
