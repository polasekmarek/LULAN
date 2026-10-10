"""
Sestaveni odvozene ricni site pro dopocet abiotickych parametru.

Slouci tri zdrojove vrstvy do jedne tabulky, ve ktere kazdy usek toku nese
vsechno, co aplikace potrebuje k popisu libovolneho bodu na vodnim toku:

    A02_Vodni_tok_JU (DIBAVOD)      topologie site, delky, nazev a ID toku
    U_TOKJ_STRAHLER (DIBAVOD)       Strahleruv rad
    CHMU_rozvodnice5G_4_plus        plocha povodi a umori

Vysledkem je samostatna databaze `dtb/ricni_sit.db` s R-tree indexem, takze
prichyceni bodu k nejblizsimu useku je otazka milisekund a aplikace nepotrebuje
zadnou GIS knihovnu.

Zdroje se od sebe lisi znakovou sadou i souradnicovym systemem - viz
GIS_PROTOTYP.md, kap. 1.

Pouziti:
    python _tools/gen_ricni_sit.py
    python _tools/gen_ricni_sit.py --vystup /tmp/test.db --tolerance 2
"""

import argparse
import collections
import math
import os
import sqlite3
import struct
import sys
import time

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIS = os.path.join(KOREN, "src", "GIS")

A02 = os.path.join(GIS, "external", "vodni_toky_jemne_cleneni", "A02_Vodni_tok_JU")
STRAHLER = os.path.join(GIS, "U_TOKJ_STRAHLER")
ROZVODNICE = os.path.join(
    GIS, "external", "CHMU_rozvodnice5G_4_plus", "CHMU_rozvodnice5G_4_plus")
VYCHOZI_VYSTUP = os.path.join(KOREN, "dtb", "ricni_sit.db")

#: Zjednoduseni geometrie pri ukladani [m]. Pro prichyceni bodu k ose toku
#: staci par metru; usetri to zhruba polovinu velikosti databaze.
TOLERANCE = 3.0

#: Toky, ktere pramení za hranicemi CR. DIBAVOD ma jen ceskou cast, takze
#: vzdalenost od pramene by vysla podhodnocena. Offsety jsou zkalibrovane
#: proti hodnotam z IS ARROW - viz GIS_PROTOTYP.md, kap. 4.
OFFSET_ZAHRANICI = {
    "Ohře": 68.89,
    "Studená Vltava": 8.01,
    "Divoká Orlice": 2.71,
    "Malše": 2.50,
    "Dračice": 20.41,
}

#: Umori podle prvni cislice cisla hydrologickeho poradi.
#: 1 = Labe (Severni more), 2 = Odra (Baltske), 4 = Dunaj (Cerne).
UMORI_Z_CHP = {"1": 1, "2": 2, "4": 3}


# ---------------------------------------------------------------------------
# Cteni zdrojovych vrstev
# ---------------------------------------------------------------------------

def kodovani_dbf(cesta):
    """Odvodi znakovou sadu DBF: nejdriv .cpg, pak pokus-omyl."""
    cpg = cesta[:-4] + ".cpg"
    if os.path.exists(cpg):
        znacka = open(cpg).read().strip().lower().replace("-", "").replace("_", "")
        if znacka in ("utf8",):
            return "utf-8"
        if znacka in ("cp1250", "windows1250"):
            return "cp1250"
    vzorek = open(cesta, "rb").read(200000)
    for k in ("utf-8", "cp1250", "iso-8859-2"):
        try:
            vzorek.decode(k)
            return k
        except UnicodeDecodeError:
            continue
    return "cp1250"


def cti_dbf(cesta, sloupce=None):
    """Sekvencni cteni DBF; vraci generator dictu."""
    kod = kodovani_dbf(cesta)
    with open(cesta, "rb") as f:
        h = f.read(32)
        poc, hlavicka, zaznam = struct.unpack("<I2H", h[4:12])
        pole = []
        while True:
            d = f.read(32)
            if len(d) < 32 or d[0:1] == b"\r":
                break
            pole.append((d[0:11].split(b"\x00")[0].decode("ascii", "replace"), d[16]))
        f.seek(hlavicka)
        for _ in range(poc):
            z = f.read(zaznam)
            if len(z) < zaznam:
                break
            pos = 1
            radek = {}
            for jmeno, sirka in pole:
                if sloupce is None or jmeno in sloupce:
                    radek[jmeno] = z[pos:pos + sirka].decode(kod, "replace").strip()
                pos += sirka
            yield radek


def cti_shp(cesta, typ_geometrie):
    """Sekvencni cteni SHP; vraci (poradi, bbox, casti) pro kazdy zaznam."""
    with open(cesta, "rb") as f:
        f.seek(100)
        i = 0
        while True:
            hlava = f.read(8)
            if len(hlava) < 8:
                break
            _cislo, delka = struct.unpack(">ii", hlava)
            obsah = f.read(delka * 2)
            i += 1
            if len(obsah) < 4:
                break
            (typ,) = struct.unpack("<i", obsah[0:4])
            if typ != typ_geometrie:
                yield i - 1, None, []
                continue
            bbox = struct.unpack("<4d", obsah[4:36])
            pocet_casti, pocet_bodu = struct.unpack("<ii", obsah[36:44])
            zacatky = struct.unpack(f"<{pocet_casti}i",
                                    obsah[44:44 + 4 * pocet_casti])
            pos = 44 + 4 * pocet_casti
            b = struct.unpack(f"<{2 * pocet_bodu}d",
                              obsah[pos:pos + 16 * pocet_bodu])
            souradnice = list(zip(b[0::2], b[1::2]))
            casti = [
                souradnice[zacatky[j]:(zacatky[j + 1] if j + 1 < pocet_casti
                                       else pocet_bodu)]
                for j in range(pocet_casti)
            ]
            yield i - 1, bbox, casti


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------

def zjednodus(body, tolerance):
    """Douglas-Peucker."""
    if len(body) < 3:
        return list(body)
    zacatek, konec = body[0], body[-1]
    dx, dy = konec[0] - zacatek[0], konec[1] - zacatek[1]
    delka2 = dx * dx + dy * dy
    nejdal, nejvzdalenost = 0, 0.0
    for i in range(1, len(body) - 1):
        x, y = body[i]
        if delka2 == 0:
            d = math.hypot(x - zacatek[0], y - zacatek[1])
        else:
            t = max(0.0, min(1.0, ((x - zacatek[0]) * dx + (y - zacatek[1]) * dy) / delka2))
            d = math.hypot(x - (zacatek[0] + t * dx), y - (zacatek[1] + t * dy))
        if d > nejvzdalenost:
            nejdal, nejvzdalenost = i, d
    if nejvzdalenost <= tolerance:
        return [zacatek, konec]
    return (zjednodus(body[:nejdal + 1], tolerance)[:-1]
            + zjednodus(body[nejdal:], tolerance))


def zabal(body):
    """Seznam bodu -> binarni blob (float32 dvojice)."""
    plocha = [s for b in body for s in b]
    return struct.pack(f"<{len(plocha)}f", *plocha)


def bod_v_polygonu(x, y, prsteny):
    uvnitr = False
    for r in prsteny:
        j = len(r) - 1
        for i in range(len(r)):
            if (r[i][1] > y) != (r[j][1] > y):
                if x < (r[j][0] - r[i][0]) * (y - r[i][1]) / (r[j][1] - r[i][1]) + r[i][0]:
                    uvnitr = not uvnitr
            j = i
    return uvnitr


# ---------------------------------------------------------------------------
# Sestaveni
# ---------------------------------------------------------------------------

def nacti_useky():
    """Topologie a atributy useku z A02 + Strahleruv rad."""
    useky = {}
    poradi = []
    for r in cti_dbf(A02 + ".dbf",
                     {"UTOKJ_ID", "UTOKJN_ID", "SHAPE_LENG", "TOK_ID",
                      "NAZ_TOK", "IDVT"}):
        try:
            uid = int(float(r["UTOKJ_ID"]))
        except ValueError:
            poradi.append(None)
            continue
        try:
            nasl = int(float(r["UTOKJN_ID"] or 0))
        except ValueError:
            nasl = 0
        useky[uid] = {
            "nasl": nasl,
            "delka": float(r["SHAPE_LENG"] or 0),
            "tok_id": r.get("TOK_ID", ""),
            "nazev": r.get("NAZ_TOK", "") or "",
            "idvt": r.get("IDVT", "") or "",
        }
        poradi.append(uid)

    strahler = {}
    for r in cti_dbf(STRAHLER + ".dbf", {"UTOKJ_ID", "STRAHLER"}):
        try:
            strahler[int(r["UTOKJ_ID"])] = int(r["STRAHLER"])
        except ValueError:
            continue
    for uid, u in useky.items():
        u["strahler"] = strahler.get(uid)
    return useky, poradi


def km_od_pramene(useky):
    """Vzdalenost od pramene ke KONCI kazdeho useku [m], hybridni varianta.

    Postupuje proti proudu po tomtez pojmenovanem toku (TOK_ID); teprve kdyz
    pojmenovany tok skonci, pokracuje do nejdelsi zdrojnice. Tim se sprane
    zachyti reky, ktere "zacinaji" soutokem dvou jinak pojmenovanych toku
    (Vltava, Otava, Ostravice).
    """
    predchudci = collections.defaultdict(list)
    for uid, u in useky.items():
        if u["nasl"] in useky:
            predchudci[u["nasl"]].append(uid)
    stupen = {uid: len(predchudci.get(uid, [])) for uid in useky}
    fronta = collections.deque(u for u, s in stupen.items() if s == 0)
    km = {}
    while fronta:
        u = fronta.popleft()
        vsichni = [p for p in predchudci.get(u, []) if p in km]
        stejny_tok = [p for p in vsichni if useky[p]["tok_id"] == useky[u]["tok_id"]]
        zdroj = stejny_tok or vsichni
        km[u] = useky[u]["delka"] + max((km[p] for p in zdroj), default=0.0)
        nasl = useky[u]["nasl"]
        if nasl in stupen:
            stupen[nasl] -= 1
            if stupen[nasl] == 0:
                fronta.append(nasl)
    for uid in useky:
        km.setdefault(uid, useky[uid]["delka"])

    # kalibrace toku pramenicich v zahranici
    for uid, u in useky.items():
        offset = OFFSET_ZAHRANICI.get(u["nazev"])
        if offset:
            km[uid] += offset * 1000
    return km, predchudci


def priraz_rozvodnice(useky, poradi, stredy):
    """Ke kazdemu useku priradi rozvodnici (podle jeho stredu)."""
    atributy = list(cti_dbf(ROZVODNICE + ".dbf",
                            {"CHP_14_S", "A_KM2", "ASUM_KM2", "CHP_1", "NAZ_TOK"}))
    # mrizkovy index pres bboxy polygonu
    KROK = 5000.0
    mrizka = collections.defaultdict(list)
    polygony = []
    for i, bbox, casti in cti_shp(ROZVODNICE + ".shp", 5):
        if bbox is None:
            polygony.append(None)
            continue
        polygony.append((bbox, casti))
        xmin, ymin, xmax, ymax = bbox
        for gx in range(int(xmin // KROK), int(xmax // KROK) + 1):
            for gy in range(int(ymin // KROK), int(ymax // KROK) + 1):
                mrizka[(gx, gy)].append(i)

    prirazeni = {}
    for uid, (x, y) in stredy.items():
        for i in mrizka.get((int(x // KROK), int(y // KROK)), ()):
            if polygony[i] is None:
                continue
            bbox, casti = polygony[i]
            if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
                continue
            if bod_v_polygonu(x, y, casti):
                prirazeni[uid] = atributy[i]
                break
    return prirazeni


def plocha_povodi(useky, predchudci, prirazeni):
    """Plocha povodi nad KONCEM kazdeho useku [km2].

    Kotvi se na `ASUM_KM2` z vrstvy rozvodnic, ktera je autoritativni
    (vnitrne konzistentni s medianem odchylky 0,000 %). Dopocitava se pouze
    poloha bodu UVNITR jedne rozvodnice, a to podilem delky site nad nim::

        plocha(u) = Σ ASUM(rozvodnic vtekajicich do teto nad u)
                    + A(rozvodnice) * delka site v rozvodnici nad u / delka site

    V uzaveru rozvodnice vyjde presne ASUM, uvnitr se plocha dopocitava jen
    z jeji VLASTNI plochy, takze se chyba nikde nekumuluje.

    Dve drivejsi verze mely obe svou slabinu:

    * `ASUM - A * (1 - podil site nad usekem)` plati jen pro body na HLAVNIM
      toku rozvodnice - maly pritok uvnitr teze rozvodnice dostal skoro celou
      plochu hlavniho toku (bezejmenny pritok Jizery 830 km2 misto 3,8);
    * rozdeleni vlastnich ploch mezi useky a jejich akumulace odspodu je sice
      bezpecna vsude, ale drobne chyby se scitaji po cele delce toku a male
      toky systematicky podstreluje.

    Tato verze bere z obou to lepsi: ASUM se pouzije tam, kde plati (pritoky
    lezici prokazatelne nad bodem), delkovy podil jen na zbytku.
    """
    povodi = {uid: (prirazeni[uid].get("CHP_14_S") if uid in prirazeni else None)
              for uid in useky}

    # vlastni a kumulovana plocha kazde rozvodnice
    vlastni_plocha, kumulovana = {}, {}
    for a in prirazeni.values():
        chp = a.get("CHP_14_S")
        if not chp or chp in vlastni_plocha:
            continue
        for klic, cil in (("A_KM2", vlastni_plocha), ("ASUM_KM2", kumulovana)):
            try:
                cil[chp] = float(a.get(klic) or 0)
            except ValueError:
                cil[chp] = 0.0

    # celkova delka site v kazde rozvodnici
    delka_site = collections.defaultdict(float)
    for uid, u in useky.items():
        if povodi.get(uid):
            delka_site[povodi[uid]] += u["delka"]

    # Prutok siti odshora dolu. Pro kazdy usek se drzi dvojice:
    #   vnejsi - soucet ASUM rozvodnic, ktere do teto vtekaji nad usekem
    #   delka  - delka site TETO rozvodnice nad koncem useku (vcetne)
    vnejsi = {}
    delka_nad = {}
    stupen = {uid: len([p for p in predchudci.get(uid, []) if p in useky])
              for uid in useky}
    fronta = collections.deque(u for u, s in stupen.items() if s == 0)
    poradi_akumulace = []
    while fronta:
        u = fronta.popleft()
        poradi_akumulace.append(u)
        nasl = useky[u]["nasl"]
        if nasl in stupen:
            stupen[nasl] -= 1
            if stupen[nasl] == 0:
                fronta.append(nasl)

    for u in poradi_akumulace:
        chp = povodi.get(u)
        soucet_vnejsi = 0.0
        soucet_delka = useky[u]["delka"] if chp else 0.0
        zapocteno = set()
        for p in predchudci.get(u, []):
            if p not in useky:
                continue
            if povodi.get(p) == chp:
                soucet_vnejsi += vnejsi.get(p, 0.0)
                soucet_delka += delka_nad.get(p, 0.0)
            elif povodi.get(p):
                # p je uzaverovy usek sve rozvodnice - vezmeme jeji ASUM
                if povodi[p] not in zapocteno:
                    zapocteno.add(povodi[p])
                    soucet_vnejsi += kumulovana.get(povodi[p], 0.0)
        vnejsi[u] = soucet_vnejsi
        delka_nad[u] = soucet_delka

    # Vysledna plocha + monotonni oprava.
    #
    # Prirazeni useku k rozvodnici se dela podle stredu useku, takze u toku,
    # ktery vede tesne podel hranice, obcas padne usek do sousedniho polygonu.
    # Pri kotveni na ASUM je to fatalni - jeden spatne prirazeny usek prepise
    # celou naakumulovanou plochu plochou sousedniho (casto pramenneho)
    # povodi. Ostruzna tak na 37. km vychazela 12,6 misto 165,5 km2.
    #
    # Fyzika ale dava dve tvrde meze: koncem useku musi protect aspon soucet
    # toho, co do nej vteka, a nejvyse ASUM jeho rozvodnice.
    plochy = {}
    for u in poradi_akumulace:
        chp = povodi.get(u)
        if not chp:
            plochy[u] = None
            continue
        celkem = delka_site.get(chp, 0.0)
        podil = (delka_nad.get(u, 0.0) / celkem) if celkem else 1.0
        hodnota = vnejsi.get(u, 0.0) + vlastni_plocha.get(chp, 0.0) * min(podil, 1.0)
        # Spodni mez: NEJVETSI z pritoku, ne jejich soucet. Soucet by v siti
        # s bocnimi rameny a kanaly tutez plochu zapocital vickrat (Vltava
        # vychazela 1910 misto 479 km2), kdezto maximum je vzdy platny
        # odhad zdola - plocha povodi po proudu nikdy neklesa.
        zdola = max((plochy[x] or 0.0 for x in predchudci.get(u, [])
                     if x in plochy), default=0.0)
        # Poradi je podstatne: strop nejdriv, spodni mez az potom. Kdyz je
        # usek prirazen do spatneho polygonu, je jeho ASUM nesmyslne nizky
        # a stropem by prebil realne pritekajici plochu (Ostruzna 12,3 misto
        # 165,0 km2). Pritekajici plocha je naopak neporusitelna.
        strop = kumulovana.get(chp)
        if strop:
            hodnota = min(hodnota, strop)
        plochy[u] = max(hodnota, zdola)
    for uid in useky:
        plochy.setdefault(uid, None)
    return plochy


def sestav(vystup, tolerance):
    print("1/6  načítám úseky a Strahlerův řád…")
    t = time.perf_counter()
    useky, poradi = nacti_useky()
    print(f"     {len(useky)} úseků za {time.perf_counter() - t:.1f} s")

    print("2/6  počítám vzdálenost od pramene…")
    t = time.perf_counter()
    km, predchudci = km_od_pramene(useky)
    print(f"     hotovo za {time.perf_counter() - t:.1f} s, "
          f"nejdelší tok {max(km.values()) / 1000:.1f} km")

    print("3/6  načítám geometrii…")
    t = time.perf_counter()
    geometrie = {}
    stredy = {}
    for i, bbox, casti in cti_shp(A02 + ".shp", 3):
        if i >= len(poradi) or poradi[i] is None or not casti:
            continue
        body = [b for c in casti for b in c]
        geometrie[poradi[i]] = (bbox, zjednodus(body, tolerance))
        stredy[poradi[i]] = body[len(body) // 2]
    print(f"     {len(geometrie)} geometrií za {time.perf_counter() - t:.1f} s")

    print("4/6  přiřazuji rozvodnice…")
    t = time.perf_counter()
    prirazeni = priraz_rozvodnice(useky, poradi, stredy)
    print(f"     přiřazeno {len(prirazeni)} z {len(stredy)} "
          f"({100 * len(prirazeni) / len(stredy):.1f} %) za "
          f"{time.perf_counter() - t:.1f} s")

    print("5/6  počítám plochu povodí…")
    t = time.perf_counter()
    plochy = plocha_povodi(useky, predchudci, prirazeni)
    print(f"     spočítáno pro {len(plochy)} úseků za {time.perf_counter() - t:.1f} s")

    print("6/6  zapisuji databázi…")
    t = time.perf_counter()
    if os.path.exists(vystup):
        os.remove(vystup)
    conn = sqlite3.connect(vystup)
    conn.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE useky (
            id          INTEGER PRIMARY KEY,   -- UTOKJ_ID
            nasl        INTEGER,               -- navazujici usek po proudu
            tok_id      TEXT,
            idvt        TEXT,
            nazev       TEXT,
            strahler    INTEGER,
            delka       REAL,                  -- [m]
            km_konec    REAL,                  -- vzdalenost od pramene ke konci [km]
            plocha_konec REAL,                 -- plocha povodi nad koncem [km2]
            umori       INTEGER,               -- 1 Labe, 2 Odra, 3 Dunaj
            chp         TEXT,                  -- cislo hydrologickeho poradi
            geom        BLOB                   -- float32 dvojice X,Y v S-JTSK
        );
        CREATE VIRTUAL TABLE useky_idx USING rtree(id, xmin, xmax, ymin, ymax);
    """)
    radky = []
    idx = []
    for uid, u in useky.items():
        if uid not in geometrie:
            continue
        bbox, body = geometrie[uid]
        a = prirazeni.get(uid)
        radky.append((
            uid, u["nasl"] or None, u["tok_id"], u["idvt"], u["nazev"],
            u["strahler"], u["delka"], km[uid] / 1000.0, plochy.get(uid),
            UMORI_Z_CHP.get((a or {}).get("CHP_1", "")),
            (a or {}).get("CHP_14_S"), zabal(body),
        ))
        idx.append((uid, bbox[0], bbox[2], bbox[1], bbox[3]))
    conn.executemany("INSERT INTO useky VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", radky)
    conn.executemany("INSERT INTO useky_idx VALUES (?,?,?,?,?)", idx)
    conn.execute("CREATE INDEX ix_useky_tok ON useky(tok_id)")
    conn.execute("CREATE INDEX ix_useky_nazev ON useky(nazev)")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    print(f"     {len(radky)} řádků za {time.perf_counter() - t:.1f} s")
    print(f"\nhotovo: {vystup}  ({os.path.getsize(vystup) / 1e6:.1f} MB)")


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vystup", default=VYCHOZI_VYSTUP)
    p.add_argument("--tolerance", type=float, default=TOLERANCE,
                   help="zjednodušení geometrie v metrech")
    args = p.parse_args()
    sys.setrecursionlimit(10000)
    sestav(args.vystup, args.tolerance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
