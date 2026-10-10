# Odvození abiotických parametrů z GIS

Datum: 24. 8. 2026

Ověřeno na **86 lokalitách** z databáze, kde jsou hodnoty z ARROW k dispozici
(plocha povodí 1,2–28 061 km², vzdálenost od pramene 1,1–408 km).

---

## 1. Které vrstvě věřit u které veličiny

| veličina | zdroj | jak |
|---|---|---|
| Strahlerův řád | `U_TOKJ_STRAHLER` (DIBAVOD) | **číst z atributu**, nepočítat |
| vzdálenost od pramene | `A02_Vodni_tok_JU` (DIBAVOD) | graf přes `UTOKJN_ID` |
| plocha povodí | `CHMU_rozvodnice5G_4_plus` | `ASUM_KM2` + korekce uvnitř polygonu |
| úmoří | `CHP_1` z rozvodnic | přímo |
| nádrže, jezy | `HY-P.gpkg` | až pro jezerní metodiky |

### Znaková sada — liší se vrstva od vrstvy

| vrstva | kódování |
|---|---|
| `U_TOKJ_STRAHLER.dbf` | **UTF-8** (má i `.cpg`) |
| `A02_Vodni_tok_JU.dbf` | **cp1250** |
| `CHMU_rozvodnice5G_4_plus.dbf` | **cp1250** |

Detekce v `kodovani_dbf()`: nejdřív `.cpg`, pak zkusit UTF-8 (nad cp1250 daty
spolehlivě spadne na `UnicodeDecodeError`), pak cp1250.

---

## 2. Strahlerův řád — číst, nepočítat

Přepočet z hydrografické sítě ZABAGED dává úplně jiné hodnoty, protože
Strahlerův řád závisí na hustotě sítě:

| lokalita | DIBAVOD | přepočet z HY-NET | ARROW |
|---|---|---|---|
| Velička | 3 | 3 | **3** |
| Sudoměřický p. | 3 | 8 | **3** |
| Vlára | 6 | 7 | **6** |
| Kyjovka | 5 | 15 | **5** |

Čtení z `U_TOKJ_STRAHLER` sedí **4 ze 4** s odsazením bodu 0–1 m od osy.
Metodika ostatně předepisuje konkrétní vrstvu („řád toku Strahler 1:10 000").

Vedlejší přínos: odpadá problém s příhraničními toky, kde je síť přerušená
na hranici a přepočtený řád by vyšel nesmyslně nízký.

---

## 3. Plocha povodí — bez výškopisu

Vrstva `CHMU_rozvodnice5G_4_plus` (10 229 polygonů) nese v atributech
`A_KM2` (vlastní plocha) a `ASUM_KM2` (kumulovaná plocha nad uzávěrovým
profilem). Je vnitřně bezchybná — platí `ASUM = Σ ASUM přítoků + vlastní A`
s mediánem relativní odchylky **0,000 %** (10 206 z 10 229 do 1 %).

Původně navrhované řešení přes flow accumulation z DEM (WhiteboxTools) je
tímto zbytečné. Cesta k použitelnému vzorci ale vedla přes tři iterace.

### 3.1 Co nefungovalo

**Varianta A — odečet podílu polygonu**

```
plocha(bod) = ASUM(polygon) − A(polygon) × (1 − podíl sítě nad bodem)
```

Na hlavním toku sedí výborně (medián 0,7 %), ale platí **jen tam**. Malý
přítok uvnitř téhož polygonu zdědí skoro celou plochu hlavního toku:
bezejmenný pravobřežní přítok Jizery vyšel **830 km² místo 3,80** (+21 711 %).

**Varianta B — rozdělení vlastních ploch a akumulace odspodu**

Vlastní plocha každého polygonu se rozdělí mezi jeho úseky podle délek
a příspěvky se sčítají po proudu. Bezpečné všude, katastrofy zmizely, ale
drobné chyby se sčítají po celé délce toku a medián se **zhoršil na 2,34 %**.

### 3.2 Co funguje — kotvení na ASUM

```
plocha(úsek) = Σ ASUM(rozvodnic vtékajících do této nad úsekem)
             + A(rozvodnice) × délka sítě v rozvodnici nad úsekem / délka sítě
```

V uzávěru rozvodnice vyjde přesně `ASUM`, uvnitř se dopočítává jen z její
**vlastní** plochy — chyba se nikde nekumuluje. Podíl se odhaduje délkou
říční sítě, která s plochou koreluje mnohem líp než vzdušná vzdálenost.

### 3.3 Dvě pojistky, bez nichž to nefunguje

Přiřazení úseku k rozvodnici se dělá podle **středu úseku**. U toku, který
vede těsně podél rozvodnice, občas padne úsek do sousedního polygonu — a při
kotvení na ASUM je to fatální, protože jeden špatně přiřazený úsek přepíše
celou naakumulovanou plochu plochou sousedního (často pramenného) povodí.
Ostružná tak na 37. km vycházela **12,6 místo 165,5 km²**.

Fyzika ale dává dvě tvrdé meze — a **záleží na pořadí**, ve kterém se uplatní:

1. **strop:** plocha nesmí přesáhnout `ASUM` své rozvodnice;
2. **spodní mez:** plocha musí být aspoň taková, jaká do úseku přitéká.

Nejdřív strop, pak spodní mez. Obráceně by nesmyslně nízký strop u špatně
přiřazeného úseku přebil reálnou přitékající plochu.

Spodní mez je **maximum z přítoků, ne jejich součet.** Součet by v síti
s bočními rameny a kanály tutéž plochu započítal vícekrát — Vltava vycházela
1 910 místo 479 km². Maximum je vždy platný odhad zdola, protože plocha
povodí po proudu nikdy neklesá.

### 3.4 Výsledek (n = 86)

| varianta | medián | do 1 % | do 5 % | do 20 % | max |
|---|---|---|---|---|---|
| A — odečet podílu polygonu | 0,70 % | – | – | – | 21 711 % |
| B — akumulace odspodu | 2,34 % | – | 53 | 76 | 56 % |
| C — kotvení na ASUM, bez pojistek | 1,45 % | 40 | 58 | 77 | 92 % |
| **C + obě pojistky** | **0,88 %** | **45** | **65** | **80** | **38 %** |

Zbylých šest lokalit nad 20 % jsou drobné toky (1,5–12 km²), kde jde
o rozdíl řádu 1 km² — chyba vzniká rozdělením plochy uvnitř jedné
rozvodnice a jinak než výškopisem ji zpřesnit nelze.

Kontrolní body: Ohře–Karlovy Vary **1 484,10** vs. ARROW 1 484,66 (0,04 %),
největší povodí v síti 51 261 km² = Labe na státní hranici.

Testována byla ještě korekce na nezaříznutou pramennou oblast (virtuální
délka nad hlavou koryta, 250 a 500 m). Medián sice klesl na 0,80 %, ale ocas
rozdělení se zhoršil a malé toky začaly přestřelovat místo podstřelovat —
do produkce nešla.

---

## 4. Vzdálenost od pramene

Načtení 249 903 úseků 1,3 s, výpočet 1,1 s, přichycení 86 bodů 4,3 s.
Medián odsazení lokality od osy toku **0,1 m**.

Kontrola smysluplnosti: nejdelší cesta v síti vychází **541,5 km**, což
odpovídá Labi na státní hranici přes Vltavu (430 + 110 km).

### Porovnání variant (n = 86)

| varianta | medián \|Δ\| | do 0,1 km | do 0,5 km | do 2 km | max |
|---|---|---|---|---|---|
| nejdelší cesta sítí | 0,894 km | 30 | 43 | 54 | 65,5 |
| po pojmenovaném toku | 0,037 km | 45 | 52 | 62 | 68,9 |
| **hybrid** | 0,028 km | 46 | 53 | 63 | 68,9 |
| **hybrid + kalibrace zahraničí** | **0,010 km** | **49** | **58** | **68** | **20,4** |

**Hybrid** = jít proti proudu po `TOK_ID`; když pojmenovaný tok skončí,
pokračovat do nejdelší zdrojnice. Řeší toky, kde se mění jméno (Vltava
začíná soutokem Teplé a Studené Vltavy, Otava soutokem Vydry a Křemelné,
Ostravice soutokem Bílé a Černé Ostravice).

ARROW **neměří nejdelší linii**, ale délku po hlavním toku — nejdelší cesta
přestřeluje, protože DIBAVOD má v pramenných oblastech hustší síť drobných
přítoků, než jaké ARROW považuje za pramen.

### Kalibrace toků pramenících v zahraničí

Data končí na státní hranici. Pramenný úsek cesty se testuje na vzdálenost
od hranice ČR; leží-li do ~250 m a odchylka je konzistentně záporná, přičte
se offset:

| tok | offset | podklad |
|---|---|---|
| Ohře | +68,89 km | 1 lokalita, pramen 84 m od hranice |
| Studená Vltava | +8,01 km | 1 lokalita, 112 m |
| Divoká Orlice | +2,71 km | 1 lokalita, 108 m |
| Malše | +2,50 km | 2 lokality (−2,39 a −2,60), 160 m |

Malše je dobrý test konzistence — dvě nezávislé lokality dávají offset lišící
se o 0,2 km.

**Pozor:** blízkost hranice sama o sobě nestačí. Morava pramení na Králickém
Sněžníku 156 m od polské hranice, ale celý tok je v ČR. Tabulka proto musí
být ruční, ne odvozená jen z geometrie.

---

## 5. Co zůstává nedořešené

Po kalibraci zbývá 18 lokalit s odchylkou nad 2 km, ve dvou skupinách:

**Dračice −20,4 km** — pramení v Rakousku, ale pramenný úsek je 10 km od
hranice (tok se k ní vrací). Detekce podle vzdálenosti ho nechytí, patří do
ruční tabulky.

**Vltava +15,3 / Otava +11,5 / Morava +7,0 / Úhlava +7,3** — hybrid jde do
*nejdelší* zdrojnice, zatímco ARROW používá *uznávanou* pramennou větev, což
nemusí být totéž. U Moravy je to nekonzistentní (tři lokality: +0,17, +6,95,
+6,95), takže tam bude jiná příčina — pravděpodobně se cesta rozchází na
konkrétním soutoku.

Doporučuji doplnit ruční tabulku pramenných větví pro velké řeky (Vltava,
Otava, Ostravice, Morava, Úhlava, Odra) — je jich řádově deset a jde
o jednorázový zápis, který zároveň slouží jako dokumentace rozhodnutí.

---

## 6. Výsledná vrstva

Ze tří zdrojových vrstev se jednorázově sestaví **`dtb/ricni_sit.db`**
(66,6 MB, 249 903 úseků, R\*Tree index). Aplikace pak nepotřebuje ani
geopandas, ani samotné shapefily — jen tenhle jeden soubor.

```
python _tools/gen_ricni_sit.py          # sestavení, ~60 s
```

| krok | čas |
|---|---|
| načtení 249 903 úseků z DBF | 1,7 s |
| vzdálenost od pramene pro celou ČR | 1,4 s |
| načtení geometrie | 11,0 s |
| přiřazení rozvodnic (100 % úseků) | 36,8 s |
| plocha povodí | 2,2 s |
| zápis databáze | 5,6 s |

### Dotaz za běhu

```python
from ricni_sit import RicniSit
with RicniSit() as sit:
    sit.popis_bodu(49.5804, 18.0831)
```

vrátí `tok, idvt, strahler, km_od_pramene, plocha_povodi, umori, chp,
odsazeni, poznamka` za **18 ms**. Medián odsazení lokality od osy toku je
0,4 m, maximum 5 m; nad `MEZ_ODSAZENI` (150 m) se do výsledku přidá
upozornění, nad `MAX_VZDALENOST_OD_TOKU` (500 m) se hodnota nedoplní vůbec.

### Souhrn přesnosti na 86 lokalitách

| veličina | shoda s ARROW |
|---|---|
| úmoří | **86/86** přesně |
| Strahlerův řád | **85/86** přesně |
| vzdálenost od pramene | medián \|Δ\| **6 m**, 50 lokalit do 100 m |
| plocha povodí | medián **0,88 %**, 65 lokalit do 5 % |

---

## 7. Napojení do aplikace

`abiotic_params.py` už shapefily nečte. Parametry `UMORI`, `STRAHLER`,
`KM_OD_PRAM` a `PLOCHA_POV` se berou z říční sítě, `MNM` a `SLOPE` z DMR:

```
python abiotic_params.py --db dtb/LULAN_dtb_001.db --vse
```

### Nadmořská výška

Dotaz na `identify` službu ČÚZK, primárně **DMR 5G** (úplná střední chyba
výšky 0,18 m v terénu), s automatickým přepadnutím na DMR 4G tam, kde 5G
není k dispozici.

### Podélný sklon

`RicniSit.osa_okolo()` složí osu toku z navazujících úseků — proti proudu se
drží hlavního toku (vybírá předchůdce s největší plochou povodí, takže
neuhne do bočního přítoku) — a vrátí 9 stejně vzdálených bodů na 400 m
kolem lokality. Pro každý se odečte výška a sklon se určí jako směrnice
**Theil–Senovy přímky** (medián směrnic všech dvojic).

Regrese, ne prostý rozdíl krajních bodů: jednotlivý odečet z DMR může
padnout na břehovou hranu nebo most a dvoubodový výpočet by tím byl
znehodnocen. Theil–Sen snese až 29 % vadných hodnot.

Osa se podařilo sestavit pro **86 z 86** lokalit.
