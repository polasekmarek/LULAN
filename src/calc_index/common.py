"""
Sdilene stavebni kameny pro vypocet indexu ekologickeho stavu.

Obsahuje:
  * nacitani a cachovani taxonomickych seznamu (taxalist_*)
  * praci se synonymy a taxonomickou hierarchii
  * aplikaci adjustacnich pravidel (D / T / R)
  * genericky prevod metrik na EQR podle datove tabulky
  * klasifikaci EQR do trid ekologickeho stavu / potencialu
  * pomocne funkce pro zapis vysledku do tabulky `results`

Vsechny vypocetni moduly v balicku calc_index stavi na tomto modulu.
"""

from __future__ import annotations

import math
from math import log

from PyQt6.QtSql import QSqlQuery


# ---------------------------------------------------------------------------
# Tridy ekologickeho stavu / potencialu
# ---------------------------------------------------------------------------

#: Hranice trid pro hodnoceni STAVU (HMWB = 'P', prirozeny utvar).
#: Seznam dvojic (dolni_mez, trida), serazeny sestupne.
HRANICE_STAV = [
    (0.8, "VD"),   # velmi dobry
    (0.6, "D"),    # dobry
    (0.4, "S"),    # stredni
    (0.2, "P"),    # poskozeny
    (float("-inf"), "Z"),  # znicený
]

#: Hranice trid pro hodnoceni POTENCIALU silne ovlivnenych utvaru (HMWB = 'S').
#:
#: Zdroj: Opatrilova a kol. (2013), Metoda pro hodnoceni ekologickeho
#: potencialu silne ovlivnenych a umelych vodnich utvaru, Tab. 8.
#: Tridy jsou ctyri, ne pet - u potencialu se nerozlisuje velmi dobry stav
#: a nejlepsi trida je "dobry a lepsi potencial" (D/L).
#:
#: Metodika pouziva ostrou nerovnost: dobry a lepsi je 0,6 < MMI,
#: stredni 0,4 < MMI <= 0,6 atd. Proto se klasifikuje s ostrym porovnanim.
HRANICE_POTENCIAL = [
    (0.6, "D/L"),   # dobry a lepsi potencial
    (0.4, "S"),     # stredni
    (0.2, "P"),     # poskozeny
    (float("-inf"), "Z"),  # zniceny
]

#: Tridy potencialu se podle Tab. 8 urcuji ostrou nerovnosti (MMI > mez),
#: zatimco u stavu se pouziva MMI >= mez.
POTENCIAL_OSTRE = True


def klasifikuj(eqr, potencial=False, hranice=None, ostre=None):
    """Zaradi hodnotu EQR do tridy ekologickeho stavu / potencialu.

    Args:
        eqr: hodnota EQR, nebo None / NaN
        potencial: True = pouzit hranice pro potencial, False = pro stav
        hranice: volitelne vlastni seznam dvojic (dolni_mez, trida);
                 pouziva se u metodik s vlastnimi hranicemi (napr. MF)
        ostre: True = porovnavat ostre (eqr > mez), False = eqr >= mez;
               None = podle toho, zda jde o potencial

    Returns:
        str s oznacenim tridy, nebo None pokud EQR neni k dispozici
    """
    if eqr is None or (isinstance(eqr, float) and math.isnan(eqr)):
        return None
    if hranice is None:
        hranice = HRANICE_POTENCIAL if potencial else HRANICE_STAV
    if ostre is None:
        ostre = potencial and POTENCIAL_OSTRE

    for mez, trida in hranice:
        if (eqr > mez) if ostre else (eqr >= mez):
            return trida
    return None


# ---------------------------------------------------------------------------
# Bezpecne prevody hodnot
# ---------------------------------------------------------------------------

def to_float(value, default=None):
    """Prevede hodnotu z databaze na float; pri neuspechu vrati `default`.

    Prijima i retezec s desetinnou carkou ("412,5") - tak muze hodnota
    prijit z CSV nebo z rucniho zapisu v GUI.
    """
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if value == "":
            return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def je_platna(value):
    """True prave tehdy, kdyz je hodnota cislo a neni NaN."""
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def safe_log(value):
    """Prirozeny logaritmus; pro nekladne hodnoty vraci 0.0 misto vyjimky.

    Pouziva se tam, kde metodika predepisuje ciste ln - napriklad
    ve jmenovateli Margalefova indexu (S-1)/ln(N).
    """
    v = to_float(value, 0.0)
    if v is None or v <= 0:
        return 0.0
    return log(v)


def log_abundance(value):
    """Logaritmovana abundance pouzita pri vazeni metrik: ln(x + 1).

    Metriky kvantitativniho zastoupeni i metriky odvozene z ekologickych
    charakteristik pracuji podle metodiky se "souctem logaritmovanych
    abundanci". Pouziva se pritom transformace ln(x+1), ktera je robustnejsi
    a hlavne nevyrazuje taxony zastoupene jedinym jedincem - u ln(1) = 0
    by takovy taxon do metriky neprispel vubec.

    Metodika velkych nebroditelnych rek (Nemejcova a kol. 2019, kap. 4) to
    uvadi vyslovne: "Pro vypocet metrik zalozenych na abundancich jednotlivych
    taxonu byla pouzita logaritmovana data - ln(x+1)".

    Overeno i proti oficialnim hodnotam metrik: s ln(x+1) sedi medianovy
    rozdil u EPT Abu a metriky metaritralu presne na nulu, s ln(x) nikoli.
    """
    v = to_float(value, 0.0)
    if v is None or v <= 0:
        return 0.0
    return log(v + 1.0)


# ---------------------------------------------------------------------------
# Nacitani taxonomickeho seznamu
# ---------------------------------------------------------------------------

#: Hodnota PARENT_ID oznacujici korenovy taxon seznamu (nema nadrazeny taxon).
KOREN_PARENT_ID = -1

#: Cache nactenych taxonomickych seznamu a adjustacnich sad.
#:
#: Taxonomicke seznamy maji desetitisice radku a behem davkoveho vypoctu
#: se nemeni, takze nema smysl je nacitat znovu pro kazdy vzorek. Cache je
#: nutne vyprazdnit po kazde uprave taxalistu nebo adjustaci - o to se
#: stara vycisti_cache(), kterou vola runner pred zahajenim vypoctu.
_CACHE = {}


def vycisti_cache():
    """Vyprazdni cache taxonomickych seznamu a adjustacnich sad."""
    _CACHE.clear()


def cache_ziskej(klic, vyrob):
    """Vrati hodnotu z cache, nebo ji vyrobi a ulozi.

    Pouzivaji moduly, ktere pocitaji spolecny mezivysledek pro vice vzorku
    (napr. sezonni prumery metrik fytoplanktonu pro lokalitu a rok).

    Args:
        klic: libovolny hashovatelny klic
        vyrob: funkce bez parametru, ktera hodnotu spocita
    """
    if klic not in _CACHE:
        _CACHE[klic] = vyrob()
    return _CACHE[klic]


def nacti_taxalist(db_connection, tabulka, trait_sloupce):
    """Nacte taxonomicky seznam vcetne pozadovanych trait sloupcu.

    Vysledek se cachuje - opakovane volani se stejnymi parametry uz
    databazi nedotazuje. Viz vycisti_cache().

    Args:
        db_connection: QSqlDatabase
        tabulka: nazev tabulky, napr. 'taxalist_mzb'
        trait_sloupce: seznam nazvu trait sloupcu k nacteni

    Returns:
        dict {'by_name': {NAME: info}, 'by_id': {ID: info},
              'children': {PARENT_ID: [ID, ...]}}
        kde info je dict s klici ID, name, PARENT, PARENT_ID, SYN, LEVEL
        a dale vsemi trait sloupci prevedenymi na float (nebo None).
    """
    klic = ("taxalist", db_connection.databaseName(), tabulka, tuple(trait_sloupce))
    if klic in _CACHE:
        return _CACHE[klic]

    zakladni = ["ID", "NAME", "PARENT", "PARENT_ID", "SYN", "LEVEL"]
    sloupce = zakladni + list(trait_sloupce)

    by_name, by_id, children = {}, {}, {}
    bez_id = 0

    query = QSqlQuery(db_connection)
    query.exec(f"SELECT {', '.join(sloupce)} FROM {tabulka}")
    while query.next():
        jmeno = query.value(1)
        taxon_id = query.value(0)

        # Cast taxonu ma v seznamu prazdne ID. Bez nahradniho klice by se
        # vsechny takove taxony v cache slily do jednoho zaznamu (by_id[None])
        # a prebiraly traity od naposledy nacteneho radku. Pouzijeme proto
        # nahradni klic odvozeny od jmena, ktere je v seznamu jedinecne.
        if taxon_id is None or taxon_id == "":
            taxon_id = f"NAME:{jmeno}"
            bez_id += 1

        info = {
            "ID": taxon_id,
            "name": jmeno,
            "PARENT": query.value(2),
            "PARENT_ID": query.value(3),
            "SYN": query.value(4),
            "LEVEL": query.value(5),
        }
        for i, trait in enumerate(trait_sloupce, start=len(zakladni)):
            info[trait] = to_float(query.value(i))

        by_name[info["name"]] = info
        by_id[info["ID"]] = info

    if bez_id:
        print(
            f"[common] {tabulka}: {bez_id} taxonu nema vyplnene ID - "
            f"pouzity nahradni klice odvozene od jmena"
        )

    # Druhy pruchod: dohledat klic rodice.
    #
    # Cast taxonu ma prazdne PARENT_ID, ale vyplnene jmeno rodice ve sloupci
    # PARENT. Bez dohledani podle jmena by se taxonomicky rodokmen u takoveho
    # taxonu predcasne pretrhl a metriky zalozene na prislusnosti ke skupine
    # (EPT, Chironomidae, pocet celedi) by ho neuvidely.
    bez_rodice = []
    for info in by_name.values():
        rodic = info["PARENT_ID"]
        if rodic == KOREN_PARENT_ID:
            # korenovy taxon seznamu - nadrazeny taxon uz neexistuje
            rodic = None
        elif rodic is None or rodic not in by_id:
            cil = by_name.get(info["PARENT"])
            rodic = cil["ID"] if cil is not None else None
            if rodic is None and info["PARENT"]:
                bez_rodice.append(info["name"])
        info["PARENT_KEY"] = rodic
        if rodic is not None:
            children.setdefault(rodic, []).append(info["ID"])

    if bez_rodice:
        print(
            f"[common] {tabulka}: u {len(bez_rodice)} taxonu se nepodarilo "
            f"dohledat nadrazeny taxon ({', '.join(bez_rodice[:5])})"
        )

    vysledek = {"by_name": by_name, "by_id": by_id, "children": children}
    _CACHE[klic] = vysledek
    return vysledek


def nacti_chemicke_kody(db_connection):
    """Nacte kody chemickych parametru z ciselniku.

    Tabulka `data` micha dohromady taxony a chemicka mereni - obojí je
    ulozene jako dvojice (nazev, hodnota). Kody chemickych parametru je
    proto potreba pri praci s taxony vyradit, jinak by se napriklad
    koncentrace chlorofylu zapocitala mezi jedince ve vzorku.

    Returns:
        set kodu (napr. {'IC0000', 'CB0050', ...})
    """
    klic = ("chem_kody", db_connection.databaseName())
    if klic in _CACHE:
        return _CACHE[klic]

    kody = set()
    query = QSqlQuery(db_connection)
    for sql in ("SELECT kod FROM chem_params", "SELECT KOD FROM taxalist_chem"):
        if query.exec(sql):
            while query.next():
                if query.value(0):
                    kody.add(query.value(0))

    _CACHE[klic] = kody
    return kody


def nacti_data_vzorku(db_connection, sample_id, bez_chemie=True):
    """Nacte taxonomicka data vzorku z tabulky `data`.

    Args:
        bez_chemie: True = vynechat radky, jejichz nazev je kodem
            chemickeho parametru (viz nacti_chemicke_kody)

    Returns:
        list dictu {'taxon_name': str, 'abundance': float}
    """
    chemicke = nacti_chemicke_kody(db_connection) if bez_chemie else set()

    query = QSqlQuery(db_connection)
    query.prepare("SELECT d.name, d.val FROM data d WHERE d.sample = ?")
    query.addBindValue(sample_id)

    taxa = []
    if query.exec():
        while query.next():
            name = query.value(0)
            abundance = to_float(query.value(1))
            if name and abundance is not None and name not in chemicke:
                taxa.append({"taxon_name": name, "abundance": abundance})
    return taxa


def nacti_adjustaci(db_connection, con_id):
    """Nacte adjustacni pravidla pro dany typ (METR_J, PRED_P, ...).

    Vysledek se cachuje - viz vycisti_cache().

    Returns:
        dict {TAXON_SEQ_FROM: {'STATE': str, 'TAXON_SEQ_TO': id}}
    """
    klic = ("adjustace", db_connection.databaseName(), con_id)
    if klic in _CACHE:
        return _CACHE[klic]

    cache = {}
    query = QSqlQuery(db_connection)
    query.prepare(
        "SELECT TAXON_SEQ_FROM, STATE, TAXON_SEQ_TO FROM adjustace WHERE CON_ID = ?"
    )
    query.addBindValue(con_id)
    if query.exec():
        while query.next():
            cache[query.value(0)] = {
                "STATE": query.value(1),
                "TAXON_SEQ_TO": query.value(2),
            }
    _CACHE[klic] = cache
    return cache


# ---------------------------------------------------------------------------
# Taxonomicka hierarchie
# ---------------------------------------------------------------------------

def taxonomicka_cesta(taxon_id, by_id, max_hloubka=20):
    """Vrati cestu od taxonu k jeho nejvyssimu predkovi.

    Returns:
        list dictu {'ID', 'NAME', 'LEVEL'} od nejnizsi urovne nahoru
    """
    cesta = []
    aktualni = taxon_id
    videne = set()
    for _ in range(max_hloubka):
        if aktualni is None or aktualni not in by_id or aktualni in videne:
            break
        videne.add(aktualni)
        info = by_id[aktualni]
        cesta.append({"ID": aktualni, "NAME": info["name"], "LEVEL": info["LEVEL"]})
        # PARENT_KEY dohledava nacti_taxalist i pro taxony s prazdnym PARENT_ID
        aktualni = info.get("PARENT_KEY", info["PARENT_ID"])
    return cesta


#: Pripony, kterymi taxonomicky seznam odlisuje zastupny zaznam pro vyssi
#: taxon ("Chironomidae Gen. sp." je celed Chironomidae).
ZASTUPNE_PRIPONY = (" Gen. sp.", " gen. sp.", " Gen.sp.")


#: Pripony oznacujici vyvojove stadium (dospelec / larva). Tyz taxon je
#: v seznamu vedeny zvlast pro obe stadia, napr. "Elmidae Gen. sp. Ad."
#: a "Elmidae Gen. sp. Lv." - pri poctu celedi jde ale o jednu celed.
STADIA_PRIPONY = (" Ad.", " Lv.", " Ad", " Lv")


#: Podrod v zapisu "Rod (Podrod) druh" - zavorka hned za rodovym jmenem,
#: jejiz obsah zacina velkym pismenem.
#:
#: Zamerne se NEodstranuji zavorky jinde v nazvu; u nekterych taxonu totiz
#: znaci formu nebo poddruh a jde o odlisne taxony, napr.
#: "Rhithrogena aurantiaca (beskidensis)" vs "... (savoiensis)".
_PODROD = None


def _bez_podrodu(nazev):
    """Sjednoti zapis podrodu.

    U DRUHU se oznaceni podrodu odstranuje, protoze druhove jmeno taxon
    urcuje jednoznacne:

        Simulium (Simulium) noelleri   ->  Simulium noelleri

    U zaznamu na urovni PODRODU ("Rod (Podrod) sp.") se ale postupuje
    obracene - vezme se jmeno PODRODU:

        Cricotopus (Paratrichocladius) sp.  ->  Paratrichocladius sp.

    Takovy zaznam totiz neznamena "nejaky zastupce rodu", ale konkretni
    podrod, ktery byl drive samostatnym rodem - a prave pod tim starym
    rodovym jmenem ho zna predikcni model indexu B. Odstranenim zavorky
    by splynul s rodem: vzorek s jedinym nalezem
    "Cricotopus (Paratrichocladius) sp." by pak chybne odpovidal
    predikovanemu "Cricotopus sp.", ackoli oba taxony predikcni model
    rozlisuje (a Paratrichocladius predikuje s pravdepodobnosti pod 1 %).
    """
    global _PODROD
    if _PODROD is None:
        import re
        _PODROD = re.compile(r"^(\S+)\s+\(([A-Z][^)]*)\)\s+(.*)$")

    m = _PODROD.match(nazev.strip())
    if m is None:
        return nazev.strip()

    rod, podrod, zbytek = m.group(1), m.group(2), m.group(3)
    if zbytek.lower().startswith("sp."):
        return f"{podrod} {zbytek}"
    return f"{rod} {zbytek}"


#: Nazvy, ktere predikcni model pise jinak, nez jak zni v taxonomickem
#: seznamu, a rozdil nelze odvodit pravidlem - preklepy a zmeny zarazeni.
#: Klic i hodnota se porovnavaji po prevodu na mala pismena.
NAZVOVE_OPRAVY = {
    "eunapis fragilis": "eunapius fragilis",          # preklep v rodovem jmene
    "cordulegaster boltoni": "cordulegaster boltonii",  # pravopis druhoveho jmena
    "nematoda f. g. sp.": "nematoda",                 # v seznamu jen "Nematoda"
}

#: Taxony, ktere v seznamu zamerne nejsou a pri porovnani se vynechavaji.
IGNOROVANE_TAXONY = {"stenelmis canaliculata lv."}


def normalizuj_pro_porovnani(nazev):
    """Sjednoti zapis nazvu taxonu pro porovnavani mezi tabulkami.

    Predikcni model B-index drzi jmena taxonu v jinem zapisu nez taxonomicky
    seznam:

        Elmis sp. lv.                 vs.  Elmis sp. Lv.
        Hydraena sp. im.              vs.  Hydraena sp. Ad.  (imago = dospelec)
        Limnephilidae g. sp.          vs.  Limnephilidae Gen. sp.
        Chrysomelidae g. sp. lv.      vs.  Chrysomelidae Gen. sp. Lv.
        Simulium noelleri             vs.  Simulium (Simulium) noelleri
        Bythinella austriaca agg.     vs.  Bythinella austriaca

    Bez sjednoceni se takove taxony pri porovnani pozorovaneho a
    predikovaneho spolecenstva nikdy nesparuji, cimz klesa citatel indexu B
    a cely index vychazi nizsi, nez ma.

    Returns:
        nazev prevedeny na mala pismena se sjednocenymi priponami
        a bez oznaceni podrodu; prazdny retezec u ignorovanych taxonu
    """
    import re

    if not nazev:
        return ""

    s = _bez_podrodu(nazev).lower().strip()
    s = re.sub(r"\s+", " ", s)

    # Rucni oprava se zkousi jeste pred pravidly - nektere nazvy by pravidla
    # prepsala do podoby, pod kterou uz je v tabulce nenajdeme
    # (napr. "Nematoda f. g. sp." -> "nematoda gen. sp.").
    if s in NAZVOVE_OPRAVY:
        return NAZVOVE_OPRAVY[s]
    if s in IGNOROVANE_TAXONY:
        return ""

    # oznaceni agregatu druhu se pro porovnani nerozlisuje
    s = re.sub(r"\s+agg\.$", "", s)

    # vyvojove stadium je az na konci, proto se odstranuje jako prvni -
    # teprve pak lze sjednotit priponu zastupneho zaznamu ("g. sp.")
    stadium = ""
    m = re.search(r"\s+(lv|im|ad)\.$", s)
    if m:
        stadium = " lv." if m.group(1) == "lv" else " ad."
        s = s[: m.start()]

    s = re.sub(r"\s+f\.\s*g\.\s*sp\.$", " gen. sp.", s)
    s = re.sub(r"\s+(g|gen)\.\s*sp\.$", " gen. sp.", s)

    s = re.sub(r"\s+", " ", s).strip()
    s = NAZVOVE_OPRAVY.get(s, s) + stadium

    if s in IGNOROVANE_TAXONY:
        return ""
    return s


def mapa_synonym(taxalist):
    """Sestavi prevod {normalizovane jmeno: normalizovane PLATNE jmeno}.

    Predikcni model indexu B drzi jmena taxonu ve stavu, v jakem byla
    podkladova databaze porizena. Cast z nich je dnes v taxonomickem seznamu
    vedena jako SYNONYMUM noveho jmena:

        Lasiocephala basalis   ->  Lepidostoma basale
        Serratella ignita      ->  Ephemerella ignita
        Oreodytes sanmarkii    ->  Nectoporus sanmarkii

    Data vzorku prochazi vyres_synonyma(), a jsou tedy uz pod platnymi jmeny.
    Predikce ne - bez teto mapy se takovy taxon nikdy nesparuje a index B
    vychazi systematicky nizsi.

    Vysledek se drzi primo v nactenem seznamu, takze se pocita jednou
    a zaroven zanikne spolu s nim (vycisti_cache).

    Returns:
        dict {normalizovane jmeno: normalizovane platne jmeno}
    """
    if "_mapa_synonym" in taxalist:
        return taxalist["_mapa_synonym"]

    by_name = taxalist["by_name"]
    mapa = {}
    for jmeno, info in by_name.items():
        cil = info
        if info.get("SYN"):
            nalezeny = by_name.get(info.get("SYN")) or by_name.get(info.get("PARENT"))
            if nalezeny is not None:
                cil = nalezeny
        mapa[normalizuj_pro_porovnani(jmeno)] = normalizuj_pro_porovnani(cil["name"])

    taxalist["_mapa_synonym"] = mapa
    return mapa


def normalizuj_nazev(nazev, i_stadium=False):
    """Odstrani zastupnou priponu z nazvu taxonu.

    Celedi a vyssi taxony jsou v seznamu vedene jako "Chironomidae Gen. sp.",
    zatimco metodika o nich mluvi jako o "Chironomidae". Bez normalizace
    by porovnani nazvu nikdy nesedelo - metrika poctu taxonu pakomaru
    tak vychazela vzdy nula.

    Args:
        i_stadium: odstranit take oznaceni vyvojoveho stadia (Ad. / Lv.)
    """
    if not nazev:
        return nazev

    if i_stadium:
        for pripona in STADIA_PRIPONY:
            if nazev.endswith(pripona):
                nazev = nazev[: -len(pripona)]
                break

    for pripona in ZASTUPNE_PRIPONY:
        if nazev.endswith(pripona):
            nazev = nazev[: -len(pripona)]
            break

    return nazev.strip()


def spocitej_celedi(data, by_id):
    """Spocita pocet celedi zastoupenych ve vzorku.

    Dve upresneni proti prostemu poctu ruznych nazvu:

    * dospelci a larvy teze celedi jsou v seznamu dva zaznamy
      ("Elmidae Gen. sp. Ad." a "... Lv."), ale jde o jednu celed
    * cast zaznamu na urovni CEL jsou ve skutecnosti PODCELEDI
      (konci na -inae, napr. "Ceratopogoninae"); ty se nepocitaji,
      protoze celed uz je zastoupena jinym zaznamem

    Returns:
        pocet celedi
    """
    celedi = set()
    for taxon_id in data:
        for taxon in taxonomicka_cesta(taxon_id, by_id):
            if taxon["LEVEL"] != "CEL":
                continue
            jmeno = normalizuj_nazev(taxon["NAME"], i_stadium=True)
            if not jmeno.endswith("inae"):
                celedi.add(jmeno)
            break
    return len(celedi)


def patri_do_skupiny(taxon_id, nazvy_skupin, by_id, cache=None):
    """Zjisti, zda taxon patri do nektere ze zadanych taxonomickych skupin.

    Nazvy se porovnavaji po odstraneni zastupne pripony, takze skupinu lze
    zadat jak "Chironomidae", tak "Chironomidae Gen. sp.".

    Args:
        nazvy_skupin: iterovatelne s nazvy, napr. ('Ephemeroptera', 'Plecoptera')
        cache: volitelny dict pro memoizaci vysledku v ramci jednoho vzorku
    """
    klic = (taxon_id, tuple(nazvy_skupin))
    if cache is not None and klic in cache:
        return cache[klic]

    skupiny = {normalizuj_nazev(n) for n in nazvy_skupin}
    vysledek = any(
        normalizuj_nazev(t["NAME"]) in skupiny
        for t in taxonomicka_cesta(taxon_id, by_id)
    )

    if cache is not None:
        cache[klic] = vysledek
    return vysledek


def vyres_synonyma(taxa_data, by_name, puvodni_id=None):
    """Nahradi synonyma platnymi jmeny a agreguje abundance podle taxon_id.

    Jednotlive taxonomicke seznamy kodují synonyma ruzne:

      * taxalist_mzb - sloupec SYN je pouhy priznak s hodnotou 'SYNONYM'
        a platne jmeno je ve sloupci PARENT
      * taxalist_fb / _mf / _ryby - sloupec SYN obsahuje primo platne jmeno,
        zatimco PARENT je nadrazeny rod

    Funkce proto nejprve zkusi pouzit SYN jako jmeno; pokud takove jmeno
    v seznamu neexistuje (pripad MZB), pouzije PARENT. Puvodni kod pouzival
    vzdy PARENT, cimz u fytobentosu slucoval druhy do rodu.

    Args:
        puvodni_id: volitelny dict, do ktereho se zapise mapovani
            {platne_id: id_pod_kterym_byl_taxon_zapsan}. Adjustacni predpisy
            vznikly nad starsi verzi seznamu a odkazuji casto jeste na stara
            jmena (Pisidium personatum, Serratella ignita, Oreodytes
            sanmarkii), takze bez tohoto mapovani by na prejmenovane taxony
            zadne pravidlo nesedlo - viz aplikuj_adjustace().

    Returns:
        dict {taxon_id: abundance}
    """
    vysledek = {}
    for zaznam in taxa_data:
        info = by_name.get(zaznam["taxon_name"])
        if info is None:
            continue

        taxon_id = info["ID"]
        if info["SYN"]:
            cil = by_name.get(info["SYN"]) or by_name.get(info["PARENT"])
            if cil is not None:
                taxon_id = cil["ID"]

        vysledek[taxon_id] = vysledek.get(taxon_id, 0) + zaznam["abundance"]
        if puvodni_id is not None and taxon_id != info["ID"]:
            puvodni_id.setdefault(taxon_id, info["ID"])
    return vysledek


#: Dvojice (taxalist, jeho zaloha) pro kontrolu trait hodnot.
ZALOHY_TAXALISTU = {
    "taxalist_mzb": "taxalist_mzb_zaloha",
    "taxalist_fb": "taxalist_fb_zaloha",
    "taxalist_mf": "taxalist_mf_zaloha",
    "taxalist_ryby": "taxalist_ryby_zaloha",
}

#: Sloupce, jejichz zmena proti zaloze se ma hlasit.
#: Jde o trait hodnoty, ktere primo vstupuji do vypoctu metrik.
KONTROLOVANE_TRAITY = {
    "taxalist_mzb": ["SZS", "SZG", "HLI", "ZER", "ZMR", "ZHR", "ZEP",
                     "SZA", "SZP", "SPEAR_ORG"],
    "taxalist_fb": ["MSZS", "MSZG", "SAL", "O2"],
    "taxalist_mf": ["MTV"],
    "taxalist_ryby": [],
}


def zkontroluj_traity(db_connection, tabulka):
    """Porovna trait hodnoty taxalistu se zalohou.

    Hlida pripad, kdy se pri importu zmeni saprobni nebo jina trait hodnota
    u taxonu, ktery se ve vzorcich bezne vyskytuje. Vypocet takovou zmenu
    nijak neohlasi - vzorec je porad spravny, jen dostane jina vstupni data.

    Hlasi se pouze taxony, ktere se skutecne vyskytuji v tabulce `data`;
    u ostatnich by upozorneni jen zbytecne slo.

    Krome zmenenych hodnot se hlida i to, ze taxon v jedne z tabulek
    uplne chybi. Prave takovy rozdil zpusobil odchylku fytobentosu proti
    ARROW: *Pinnularia neomaior* je v zaloze (a v ARROW) se saprobnim
    indexem 0,6 a vahou 4, v zivem taxalistu vubec neni, takze do vypoctu
    nevstupovala. Pouhy JOIN by na to neprisel.

    Returns:
        list dictu {taxon, sloupec, nyni, zaloha, vzorku}
    """
    zaloha = ZALOHY_TAXALISTU.get(tabulka)
    sloupce = KONTROLOVANE_TRAITY.get(tabulka, [])
    if not zaloha or not sloupce:
        return []

    query = QSqlQuery(db_connection)
    tabulky = set()
    if query.exec("SELECT name FROM sqlite_master WHERE type='table'"):
        while query.next():
            tabulky.add((query.value(0) or "").lower())
    if tabulka.lower() not in tabulky or zaloha.lower() not in tabulky:
        return []

    dostupne = set()
    if query.exec(f"PRAGMA table_info({zaloha})"):
        while query.next():
            dostupne.add(query.value(1))

    # Trojice (popis, tabulka vlevo, tabulka vpravo). Prvni dotaz resi
    # taxony v obou tabulkach, druhy a treti ty, ktere jsou jen v jedne
    # z nich - LEFT JOIN se hledanou stranou prazdnou.
    varianty = (
        (f"FROM {tabulka} a JOIN {zaloha} b ON a.NAME = b.NAME", False),
        (f"FROM {tabulka} a LEFT JOIN {zaloha} b ON a.NAME = b.NAME "
         f"WHERE b.NAME IS NULL", False),
        (f"FROM {zaloha} b LEFT JOIN {tabulka} a ON a.NAME = b.NAME "
         f"WHERE a.NAME IS NULL", True),
    )

    rozdily, videno = [], set()
    for sl in sloupce:
        if sl not in dostupne:
            continue
        for zdroj, ze_zalohy in varianty:
            jmeno = "b.NAME" if ze_zalohy else "a.NAME"
            spojka = "AND" if "WHERE" in zdroj else "WHERE"
            sql = f"""
                SELECT {jmeno}, a.[{sl}], b.[{sl}],
                       (SELECT COUNT(DISTINCT sample) FROM data
                         WHERE name = {jmeno})
                {zdroj}
                {spojka} IFNULL(TRIM(CAST(a.[{sl}] AS TEXT)), '#')
                      <> IFNULL(TRIM(CAST(b.[{sl}] AS TEXT)), '#')
                  AND EXISTS (SELECT 1 FROM data WHERE name = {jmeno})
            """
            if not query.exec(sql):
                continue
            while query.next():
                klic = (query.value(0), sl)
                if klic in videno:
                    continue
                videno.add(klic)
                rozdily.append({
                    "taxon": query.value(0),
                    "sloupec": sl,
                    "nyni": query.value(1),
                    "zaloha": query.value(2),
                    "vzorku": query.value(3) or 0,
                })
    return rozdily


def popis_zmen_traitu(rozdily):
    """Prevede vysledek zkontroluj_traity() na citelnou zpravu, nebo None."""
    if not rozdily:
        return None

    def hodnota(x):
        return "—" if x in (None, "") else str(x)

    radky = [
        f"  {r['taxon']} — {r['sloupec']}: {hodnota(r['zaloha'])} → "
        f"{hodnota(r['nyni'])} ({r['vzorku']} vzorků)"
        for r in sorted(rozdily, key=lambda x: -x["vzorku"])[:10]
    ]
    zprava = (
        "Trait hodnoty v taxonomickém seznamu se liší od zálohy u taxonů, "
        "které se vyskytují ve vzorcích:\n\n" + "\n".join(radky)
    )
    if len(rozdily) > 10:
        zprava += f"\n  … a dalších {len(rozdily) - 10}"
    return zprava


def nezname_taxony(taxa_data, by_name):
    """Vrati taxony vzorku, ktere nejsou v taxonomickem seznamu.

    Takove taxony pri reseni synonym tise vypadnou z vypoctu. Pokud jde
    o pocetne druhy, muze to vysledek znatelne posunout - proto je vhodne
    na ne upozornit misto tichého ignorovani.

    Returns:
        list dvojic (jmeno, abundance) serazeny sestupne podle abundance
    """
    chybejici = [
        (z["taxon_name"], z["abundance"])
        for z in taxa_data
        if z["taxon_name"] not in by_name
    ]
    return sorted(chybejici, key=lambda x: -x[1])


def ohlas_nezname(chybejici, taxa_data, kontext, tabulka):
    """Vypise upozorneni na taxony chybejici v seznamu.

    Returns:
        kratky text do poznamky vysledku, nebo prazdny retezec
    """
    if not chybejici:
        return ""

    celkem = sum(z["abundance"] for z in taxa_data) or 1
    ztraceno = sum(a for _, a in chybejici)
    podil = ztraceno / celkem * 100

    nazvy = ", ".join(f"{jm} ({ab:.0f})" for jm, ab in chybejici[:5])
    print(
        f"[taxony] {kontext}: {len(chybejici)} taxonu neni v {tabulka} "
        f"({podil:.1f} % jedincu) - {nazvy}"
    )
    return (
        f"; POZOR: {len(chybejici)} taxonu ({podil:.1f} % jedincu) "
        f"neni v {tabulka}"
    )


#: Co s taxonem, ktery v adjustacnim predpisu vubec neni?
#:
#: "ponechat" - taxon zustane beze zmeny. VYCHOZI, odpovida oficialnimu
#:              hodnoceni: predpis neni uzavreny seznam hodnocenych taxonu,
#:              ale seznam POTREBNYCH UPRAV. Co upravu nepotrebuje, v nem
#:              proste neni.
#: "vyradit"   - taxon se z hodnoceni vypusti, jako by mel stav 'D'.
#:
#: Overeno na 539 vzorcich s oficialnimi hodnotami: pri "vyradit" spadne
#: shoda multimetriky z 98 % na 91 % trid a u metrik poctu taxonu z ~90 %
#: na jednotky procent (MB13 EPT Tax medianove o 2 taxony nize, MB04 a MB08
#: o 2 procentni body nize). Vyrazuji se totiz i pocetne druhove agregaty
#: typu "Baetis fuscatus/scambus" nebo "Rhithrogena carpatoalpina/iridina/
#: picteti", ktere do hodnoceni jednoznacne patri - v predpisu chybi jen
#: proto, ze u nich neni co adjustovat.
TAXON_BEZ_PRAVIDLA = "ponechat"

def aplikuj_adjustace(resolved_data, pravidla, children, puvodni_id=None):
    """Aplikuje adjustacni pravidla na vyresena data vzorku.

    Pravidla (sloupec STATE v tabulce `adjustace`):
        D - VYRADIT taxon z vypoctu
        T - presunout abundanci na taxon TAXON_SEQ_TO
        R - rozdelit abundanci mezi potomky pritomne ve vzorku,
            v pomeru jejich abundanci; pokud potomci chybi, ponechat

    Taxon, ktery v predpisu vubec neni, zustava beze zmeny.

    Poznamka ke stavu 'D': puvodni kod ho vykladal jako "ponechat", coz je
    obracene. Pravidla 'D' nemaji vyplneny cil a v jarni sade jsou to
    vyhradne vysoke taxony (Arthropoda, Crustacea, Diptera, Gastropoda,
    Insecta, Araneida...), tedy zaznamy urcene jen do vysoke urovne, ze
    kterych nelze pocitat traity. V podzimni sade k nim navic pribyvaji
    vsichni pakomari - proto oficialni hodnoceni podzimnich vzorku vykazuje
    nulovy pocet taxonu pakomaru.

    Args:
        puvodni_id: mapovani {platne_id: id_pod_kterym_byl_taxon_zapsan}
            z vyres_synonyma(). Adjustacni predpisy vznikly nad starsi verzi
            taxonomickeho seznamu, takze u prejmenovanych taxonu odkazuji na
            stare ID. Bez teto zaslepky by na ne zadne pravidlo nesedlo a
            taxon by zustal na druhove urovni - napr. "Pisidium personatum"
            se v seznamu jmenuje "Euglesa personata" a predpis ho ma slucovat
            na rod "Pisidium sp.", coz je zaroven jmeno, pod kterym ho ceka
            predikcni model indexu B.

    Returns:
        dict {taxon_id: abundance}
    """
    vysledek = {}

    def pridej(taxon_id, abundance):
        vysledek[taxon_id] = vysledek.get(taxon_id, 0) + abundance

    for taxon_id, abundance in resolved_data.items():
        pravidlo = pravidla.get(taxon_id)
        if pravidlo is None and puvodni_id:
            pravidlo = pravidla.get(puvodni_id.get(taxon_id))
        if pravidlo is None:
            if TAXON_BEZ_PRAVIDLA == "vyradit":
                continue
            pridej(taxon_id, abundance)
            continue
        if pravidlo["STATE"] == "D":
            continue

        if pravidlo["STATE"] == "T":
            pridej(pravidlo["TAXON_SEQ_TO"] or taxon_id, abundance)
            continue

        if pravidlo["STATE"] == "R":
            potomci = {
                cid: resolved_data[cid]
                for cid in children.get(taxon_id, [])
                if cid in resolved_data and resolved_data[cid] > 0
            }
            celkem = sum(potomci.values())
            if celkem > 0:
                for cid, ab in potomci.items():
                    pridej(cid, abundance * ab / celkem)
            else:
                pridej(taxon_id, abundance)
            continue

        # neznamy stav - chovat se jako 'D'
        pridej(taxon_id, abundance)

    return vysledek


# ---------------------------------------------------------------------------
# Prevod metrik na EQR podle datove tabulky
# ---------------------------------------------------------------------------

#: Orezavat vysledne EQR do intervalu <0, 1>?
#:
#: True  - hodnota metriky mimo referencni rozsah da EQR presne 0 nebo 1.
#:         Odpovida tomu, ze EQR je z definice pomer vuci referencnimu stavu.
#: False - EQR muze vyjit zaporne nebo nad 1 (chovani puvodniho kodu).
OREZAVAT_EQR = True

#: Jak nalozit s metrikou, kterou se nepodarilo spocitat?
#:
#: "vynechat" - metrika nevstoupi do citatele ani jmenovatele; multimetrika
#:              se spocita z ostatnich metrik. Chybejici merení tedy vysledek
#:              nesnizuje.
#: "nula"     - metrika vstoupi do vypoctu s hodnotou EQR 0, ale plnou vahou
#:              ve jmenovateli (chovani puvodniho kodu). Kazda nespocitana
#:              metrika vysledek vyrazne strhne dolu.
CHYBEJICI_METRIKA = "vynechat"


def preved_na_eqr(metriky, tabulka_radek, orezat=None):
    """Prevede hodnoty metrik na EQR podle radku prevodni tabulky.

    Args:
        metriky: dict {nazev_metriky: hodnota}
        tabulka_radek: dict {nazev_metriky: (dolni_mez, horni_mez, invertovat, vaha)}
        orezat: True = vysledne EQR orezat do intervalu <0, 1>;
                None = pouzit globalni nastaveni OREZAVAT_EQR

    Returns:
        dict {'<METRIKA>_EQR': hodnota} pouze pro metriky, ktere maji
        platnou vstupni hodnotu.
    """
    if orezat is None:
        orezat = OREZAVAT_EQR
    eqr = {}
    for metrika, (dolni, horni, invertovat, _vaha) in tabulka_radek.items():
        hodnota = metriky.get(metrika)
        if not je_platna(hodnota):
            continue
        rozsah = horni - dolni
        if rozsah == 0:
            continue
        v = (hodnota - dolni) / rozsah
        if invertovat:
            v = 1 - v
        if orezat:
            v = min(1.0, max(0.0, v))
        eqr[f"{metrika}_EQR"] = round(v, 4)
    return eqr


def vazeny_prumer(eqr_hodnoty, tabulka_radek, desetinnych=3, chybejici=None):
    """Spocita multimetriku jako vazeny prumer EQR jednotlivych metrik.

    Args:
        chybejici: "vynechat" nebo "nula"; None = pouzit CHYBEJICI_METRIKA

    Returns:
        (multimetrika, pouzite_metriky) - multimetrika je None, pokud
        nebyla k dispozici zadna metrika
    """
    if chybejici is None:
        chybejici = CHYBEJICI_METRIKA

    citatel = 0.0
    jmenovatel = 0.0
    pouzite = []

    for metrika, (_d, _h, _i, vaha) in tabulka_radek.items():
        if not vaha:
            continue
        hodnota = eqr_hodnoty.get(f"{metrika}_EQR")
        if je_platna(hodnota):
            citatel += vaha * hodnota
            jmenovatel += vaha
            pouzite.append(metrika)
        elif chybejici == "nula":
            jmenovatel += vaha

    if jmenovatel == 0:
        return None, []
    return round(citatel / jmenovatel, desetinnych), sorted(pouzite)


def prosty_prumer(eqr_hodnoty, odmocnina=False, desetinnych=3):
    """Multimetrika jako prosty prumer vsech platnych EQR.

    Args:
        odmocnina: True = na vysledek jeste aplikovat druhou odmocninu
                   (pouziva se u FB a MZB intermittent)
    """
    platne = [v for v in eqr_hodnoty.values() if je_platna(v)]
    if not platne:
        return None, 0
    prumer = round(sum(platne) / len(platne), desetinnych)
    if odmocnina:
        prumer = round(math.sqrt(max(0.0, prumer)), desetinnych)
    return prumer, len(platne)


# ---------------------------------------------------------------------------
# Zapis vysledku
# ---------------------------------------------------------------------------

def smaz_vysledky(db_connection, sample_id, metriky=None):
    """Smaze vysledky vzorku z tabulky `results`.

    Args:
        metriky: pokud None, smazou se vsechny zaznamy vzorku;
                 jinak jen zaznamy s METRIC v zadanem seznamu
    """
    query = QSqlQuery(db_connection)
    if metriky is None:
        query.prepare("DELETE FROM results WHERE SAMPLE_ID = ?")
        query.addBindValue(sample_id)
        query.exec()
        return

    zastupne = ", ".join("?" for _ in metriky)
    query.prepare(
        f"DELETE FROM results WHERE SAMPLE_ID = ? AND METRIC IN ({zastupne})"
    )
    query.addBindValue(sample_id)
    for m in metriky:
        query.addBindValue(m)
    query.exec()


def zapis_vysledky(db_connection, sample_id, radky):
    """Zapise seznam vysledku do tabulky `results`.

    Args:
        radky: iterovatelne s dicty {'metric', 'val', 'eqr', 'class', 'pozn'}
    """
    query = QSqlQuery(db_connection)
    query.prepare(
        "INSERT INTO results (SAMPLE_ID, METRIC, VAL, VAL_EQR, CLASS, POZN) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    for radek in radky:
        val = radek.get("val")
        eqr = radek.get("eqr")
        query.addBindValue(sample_id)
        query.addBindValue(radek["metric"])
        query.addBindValue(float(val) if je_platna(val) else None)
        query.addBindValue(float(eqr) if je_platna(eqr) else None)
        query.addBindValue(radek.get("class"))
        query.addBindValue(radek.get("pozn"))
        query.exec()


def urci_sezonu(datum_str):
    """Urci sezonu ze data vzorku ve formatu DD.MM.RRRR.

    Returns:
        'J' pro jaro (leden-srpen), 'P' pro podzim (zari-prosinec),
        nebo None pri nerozpoznatelnem datu.
    """
    from datetime import datetime

    try:
        mesic = datetime.strptime(datum_str, "%d.%m.%Y").month
    except (TypeError, ValueError):
        return None
    return "J" if 1 <= mesic <= 8 else "P"
