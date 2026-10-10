# Úklid a refaktoring — přehled změn

Datum: 29. 7. 2026

---

## 0. HMWB — hodnocení ekologického potenciálu

### 0.1 Sloupec HMCH přejmenován na HMWB

Sloupec `utvary.HMCH` nesl hodnoty **P / S / U** (942 / 167 / 9 útvarů), tedy
přirozený / silně ovlivněný / umělý útvar. To je přesně vymezení HMWB a AWB
podle Rámcové směrnice, jen pod matoucím názvem. Sloupec je přejmenovaný
na `HMWB` v databázi, v GUI i v registru.

```bash
python _tools/migrace_hmwb.py dtb/LULAN_dtb_001.db      # migrace (dělá zálohu)
python _tools/migrace_hmwb.py dtb/LULAN_dtb_001.db --zpet
```

Import útvarů z CSV přijímá obě hlavičky — starší exporty s `HMCH` se
automaticky přemapují.

### 0.2 HMWB je nyní dimenzí rozřazovacího klíče

Klíč `registry.REGISTR` se rozšířil na

```
(složka, kategorie, HMWB, vysychavost, broditelnost) → hodnoticí funkce
```

takže pro potenciál lze zaregistrovat samostatný modul, aniž by se sahalo
do výpočtu stavu.

### 0.3 Nový modul pro potenciál makrozoobentosu

`calc_index/mzb_potencial_broditelne.py` + tabulka
`mzb_potencial_broditelne_table.py`, obojí podle metodiky

> Opatřilová L. a kol. (2013): *Metoda pro hodnocení ekologického potenciálu
> silně ovlivněných a umělých vodních útvarů — kategorie řeka.* VÚV TGM.
> (`metodiky/OOV-Metoda_hodnoceni_ekologickeho_potencialu-20140821.pdf`)

Přepsaných je všech 28 kombinací z tabulek 3 (jaro) a 4 (podzim), váhy
z tabulek 6 a 7, hranice tříd z tabulky 8. Rozdíly proti hodnocení stavu:

* horní meze metrik citlivých na hydromorfologii jsou snížené na úroveň
  maximálního ekologického potenciálu (např. Litál v typu 2-1 jaro: 58 → 46)
* u B-indexu je horní mez snížená z 1,0 na 0,8, tedy o jednu třídu
* saprobní index a Margalefův index zůstávají beze změny — na
  hydromorfologii nereagují
* váhy metrik jsou shodné s hodnocením stavu

Kontrola na 120 reálných vzorcích: potenciál nevyšel nižší než stav ani
jednou, průměrné zvýšení **+0,102** (min +0,043, max +0,200).

### 0.4 Umělé útvary — biologické složky se nehodnotí

Metodika (kap. 6): *„Hodnocení ekologického potenciálu umělých vodních útvarů
tekoucích vod bude prováděno pouze na základě hodnocení fyzikálně-chemických
parametrů a specifických znečišťujících látek, biologické složky nebudou
v těchto útvarech hodnoceny."*

Původní kód počítal biologii i pro `HMCH = 'U'`. Nově se pro umělé útvary
vrací `None` s vysvětlující poznámkou a případné starší výsledky se z tabulky
`results` smažou.

### 0.5 Fytobentos a makrofyta se u HMWB hodnotí jako přirozené útvary

Metodika (kap. 6): *„Hodnocení biologických složek fytobentos a makrofyta
zůstává shodné s hodnocením pro přirozené vodní útvary."* Aktualizace
metodik FB a MF z roku 2019 vlastní hranice pro potenciál nedefinují
(ověřeno prohledáním obou PDF).

Původní kód přitom pro FB a MF používal vlastní, mírnější hranice tříd
pro potenciál (FB: 0,75 / 0,55 / 0,35 / 0,15; MF: jiné meze pro každý typ).
**Nepodařilo se mi dohledat, odkud pocházejí** — nově se u HMWB použijí
hranice pro stav. Prosím ověřit; pokud ty hranice mají oporu v novější
metodice, stačí do `registry.HMWB_HODNOTI_JAKO_STAV` složku nezařadit.

### 0.6 Hranice tříd potenciálu — potvrzeno

Tabulka 8 metodiky: dobrý a lepší `MMI > 0,6`, střední `0,4 < MMI ≤ 0,6`,
poškozený `0,2 < MMI ≤ 0,4`, zničený `MMI ≤ 0,2`. Čtyři třídy, ostrá
nerovnost.

Tím se **potvrzuje oprava 1.8** níže — původní nedosažitelná větev
`elif eqr > 4` skutečně měla být 0,4.

### 0.7 Metodika potvrdila i opravu vah

Váhy metrik v tabulkách 6 a 7 jsem porovnal s tabulkou vytaženou z původního
kódu: **shoda ve všech 12 kombinacích typ × sezóna**, včetně sporné skupiny
3-1 jaro, kde metodika uvádí váhu Jep Abu (MB08) = 1,0 — přesně jak
předpokládala oprava 1.4. Původní dvojí započtení MB08 (1,0 + 0,8) tedy bylo
chybou.

### 0.8 Velké nebroditelné řeky mají vlastní metodiku

Toky typu 12-3 se **nedají hodnotit jednou metodikou**. Pro 24 vyjmenovaných
vodních útvarů platí

> Němejcová D. a kol. (2019): *Metodika hodnocení biologické složky bentičtí
> bezobratlí pro velké nebroditelné řeky.* VÚV TGM.
> (`metodiky/OOV-metodika_MZB_VR_aktualizace-20191014.pdf`)

Ta používá **úplně jinou sadu metrik a B-index nepoužívá vůbec** — jeho roli
přebírá index REKOnstruovaných taxocenóz MEPT. Nový modul
`calc_index/mzb_velke_reky.py`:

| metrika | popis | zdroj dat |
|---|---|---|
| VR01 | REKO MEPT | `TAXONY_MEPT_VLT` / `TAXONY_MEPT_MO` |
| VR02 | Margalefův index diverzity | abundance |
| VR03 | říční zonace epipotamál [%] | `ZEP` |
| VR04 | EPT Abu [%] | taxonomie |
| VR05 | saprobní index | `SZS`, `SZG` |
| VR06 | SPEAR organic | `SPEAR_ORG` |

Meze jsou z Tab. 4, třídy z Tab. 5, všechny váhy = 1. Hodnotí se **pouze
letní vzorky**. Příslušnost k úmoří rozhoduje o tom, proti kterému seznamu
očekávaných taxonů se REKO počítá.

**O použití této metodiky rozhoduje vyjmenovaný seznam útvarů**
(`calc_index/velke_reky_utvary.py`), nikoli Strahlerův řád ani sloupec
`BROD`. Seznam z metodiky se shoduje s `BROD='NEBROD'` v databázi ve všech
24 případech; kdyby se rozešly, aplikace to před výpočtem ohlásí a rozhodne
seznam z metodiky.

Původní kód měl u typu 12-3 Strahler 8/9 váhu B-indexu 0 — což v praxi
odpovídalo realitě, protože všechny toky 8. a 9. řádu v ČR jsou nebroditelné
a spadají pod metodiku velkých řek. Formálně ale Tab. 3, 4, 6 a 7 metodiky
potenciálu uvádějí řádky „8 (broditelné)" i s vahou B-indexu, takže pro
(hypotetický) broditelný tok 8. řádu se B-index použije. V současných datech
takový tok není.

### 0.9 Prázdná ID a přetržené taxonomické rodokmeny

Při implementaci REKO se ukázalo, že **334 taxonů v `taxalist_mzb` nemá
vyplněné `ID`**. V cache indexované podle ID se všechny slévaly do jediného
záznamu a přebíraly vlastnosti toho, který se načetl jako poslední. Projevilo
se to i na REKO — místo 119 očekávaných taxonů jich vycházelo 109.

Závažnější je druhá věc: **550 taxonů má prázdné `PARENT_ID`, ale vyplněné
jméno rodiče** ve sloupci `PARENT`. Taxonomický rodokmen se u nich trhal, takže
metriky založené na příslušnosti ke skupině (EPT Abu, EPT Tax, počet čeledí,
počet taxonů pakomárů) tyto taxony neviděly. Ve vzorcích se vyskytuje 78 z nich.

```
Melanoides sp. → (konec)
Melanoides sp. → Thiaridae Gen. sp. → Prosobranchia → Gastropoda → Mollusca  ← po opravě
```

`nacti_taxalist()` přiděluje taxonům bez ID náhradní klíč odvozený od jména
a dohledává rodiče podle jména, když chybí `PARENT_ID`. Obojí ohlásí do
konzole. To je ale jen záplata nad vadnými daty — proto je i oprava dat.

#### Oprava dat v databázi

```bash
python _tools/oprava_taxalist.py dtb/LULAN_dtb_001.db                  # náhled
python _tools/oprava_taxalist.py dtb/LULAN_dtb_001.db --zapsat \
       --report dtb/oprava_taxalistu_report.csv
```

Obojí spolu souvisí: **všech 550 chybějících `PARENT_ID` ukazovalo na
rodiče, který sám neměl `ID`.** Bez přidělení ID nešlo doplnit ani jedno.
Skript proto postupuje ve dvou krocích a druhý opakuje, protože rodiče
tvoří řetěz (taxon bez ID je potomkem jiného taxonu bez ID).

Výsledek na ostré databázi:

| krok | počet |
|---|---|
| přiděleno nových ID | 334 (183 DRUH, 81 ROD, 27 CEL, 26 PODROD, 12 PCEL, 4 RAD, 1 KMEN) |
| doplněno `PARENT_ID` | 550 |
| **zůstalo nedoplněno** | **0** |

Nová ID jsou z vyhrazeného rozsahu **od 9 000 000 000** (nejvyšší dosud
používané je 2 002 437 489), aby bylo na první pohled poznat, že jde
o lokálně přidělené kódy, a aby nekolidovaly s kódy z IS ARROW.

Bezpečnostní kontroly před zápisem: žádný z taxonů bez ID se nevyskytuje
v tabulce `data` ani není cílem adjustací; po zápisu žádná duplicitní ID,
žádné `PARENT_ID` mířící na neexistující taxon, nejhlubší rodokmen 12 úrovní,
`integrity_check` v pořádku. Kontrolní výpočet na 80 vzorcích dal shodné
výsledky jako na neopravené databázi — což potvrzuje, že záplata v kódu
i oprava dat dávají totéž.

> **Pozor na zápis do databáze na ownCloudu.** SQLite si na FUSE a síťových
> discích neporadí se zámky a journalem — přímý zápis skončí chybou
> `disk I/O error` a v adresáři zůstane rozpracovaný soubor `-journal`.
> Skript proto pracuje na dočasné kopii v lokálním adresáři a hotový soubor
> zkopíruje zpět jedním tahem. Totéž platí i pro běžný provoz aplikace.

### 0.10 Fytoplankton (FP)

Implementováno v `calc_index/fp_reka.py` podle

> Desortová B. a kol. (2019): *Metodika hodnocení ekologického stavu útvarů
> povrchových vod tekoucích pomocí biologické složky fytoplankton.* VÚV TGM.
> (`metodiky/OOV-metodika-FP_aktualizace-20191014.pdf`)

Čtyři metriky, všechny s vahou 1, multimetrika je jejich prostý průměr:

| metrika | popis | reaguje |
|---|---|---|
| FP01 | % Bacillariophyceae (rozsivky) | klesá se zatížením |
| FP02 | % Cyanophyceae (sinice) | stoupá se zatížením |
| FP03 | % Chlorophyceae (zelené řasy) | stoupá se zatížením |
| FP04 | chlorofyl-a [µg/l] | stoupá se zatížením |

Meze jsou z Tab. 2 podle Strahlerova řádu (7, 8, 9), třídy z Tab. 3.
Pro silně ovlivněné útvary se použije mírnější mez chlorofylu z Tab. 9
metodiky potenciálu (2013) a čtyřstupňová klasifikace; podíly taxonomických
skupin zůstávají stejné.

Omezení podle metodiky: hodnotí se **jen toky 7.–9. řádu** a **jen vegetační
sezóna březen–říjen**. Mimo tento rozsah se vrátí `None` s vysvětlením.

Podíly se vyjadřují jako **zlomek 0–1** (0,85 = 85 %), stejně jako meze
v tabulkách metodiky.

#### Pořadí výpočtu

Metodika (kap. 3): *„Pro hodnocení fytoplanktonu jsou použity průměry
jednotlivých hodnot metrik naměřených za vegetační sezónu od března do října."*

Nejdřív se tedy zprůměrují **hodnoty metrik** přes vegetační sezónu — včetně
chlorofylu-a — a teprve z průměrů se počítají EQR. Pořadí není lhostejné:
EQR se ořezává do ⟨0; 1⟩, takže průměr EQR z jednotlivých vzorků dá jiné
číslo. Na testovací sezóně je rozdíl **0,491 vs 0,509**.

Hodnoticí jednotkou proto není vzorek, ale dvojice **lokalita + rok**.
Všechny vzorky téže lokality a roku dostanou shodný výsledek; sezónní
průměry se počítají jen jednou a drží se v cache.

Chlorofyl-a se bere jako průměr kódu `IC0000` **za vegetační sezónu** daného
roku na dané lokalitě. Kód v číselníku `chem_params` chyběl — doplní ho

```bash
python _tools/migrace_chlorofyl.py dtb/LULAN_dtb_001.db --zapsat
```

(v `taxalist_chem`, odkud se plní detail vzorku, už kód byl).

#### Jmenovatel podílů

Podíly se počítají z **celkového počtu jedinců ve vzorku, včetně taxonů,
které nejsou v `taxalist_fb`**. Kdyby se počítalo jen z dohledaných taxonů,
každá mezera v seznamu by všechny tři podíly nafoukla — u rozsivek by stav
vycházel lepší, u sinic a zelených řas horší. Pokud se nějaký taxon
nedohledá, uvede se to v poznámce k výsledku i do konzole.

#### Chemické parametry se nesmí počítat mezi taxony

Tabulka `data` míchá dohromady taxony a chemická měření — obojí je uložené
jako dvojice (název, hodnota). U ostatních složek to nevadilo, protože
neznámé názvy stejně vypadávaly při řešení synonym. U fytoplanktonu ale
jmenovatel schválně bere všechny řádky, takže by se koncentrace chlorofylu
započítala mezi jedince ve vzorku — a to tím spíš, že metodika předepisuje
odebrat vzorek pro chlorofyl souběžně se vzorkem fytoplanktonu.

`nacti_data_vzorku()` proto nově vyřazuje názvy, které jsou kódem
z číselníku `chem_params` nebo `taxalist_chem`. V současných datech není
žádný vzorek, který by míchal obojí, takže na stávající výsledky to nemá
vliv — ale jakmile se začnou importovat data s chlorofylem, mělo by.

#### Ověření

V databázi zatím nejsou žádné FP vzorky, takže výpočet ověřuje
`_tools/test_fp.py` na uměle sestavené sezóně: tři vzorky ve vegetační
sezóně s výrazně odlišným složením, jeden prosincový (nesmí se počítat),
taxon mimo seznam a chlorofyl-a uložený u vzorků. Kontroluje se, že

* průměry metrik i EQR sedí na ruční výpočet podle Tab. 2,
* mezní hodnoty dávají EQR přesně 0 a 1 a ořezání do ⟨0; 1⟩ funguje,
* všechny vzorky sezóny dostanou shodný výsledek,
* prosincový vzorek se nevyhodnotí.

### 0.11 Co je připraveno, ale zatím nepočítá

V `neimplementovane.py` jsou přepsané meze pro ryby CZI-HMWB
(hranice 0,65 / 0,43 / 0,22). Chybí k nim výpočet samotných metrik, který je
společný s hodnocením stavu — a to zatím implementované není.

Modul `mzb_perennial_nebroditelne.py` už se v praxi nepoužívá — nebroditelné
toky obslouží `mzb_velke_reky.py`. Zůstává jako záchytný bod pro případ,
že by se objevil nebroditelný útvar mimo vyjmenovaný seznam.

Silně ovlivněné **vysychavé** toky metodika neřeší; použije se výpočet jako
pro přirozené vysychavé toky, jen s hranicemi tříd pro potenciál.

Původní `src/calc_indexes.py` (3 757 řádků) je beze změny uložený
v `_archiv/src/calc_indexes_puvodni.py`. Nic nebylo smazáno — všechno
nepotřebné je jen přesunuté do `_archiv/`.

---

## 1. Nalezené chyby ve výpočtu

Během strojového rozboru původního kódu se našlo osm chyb (další vyplynuly
z porovnání s metodikou, viz 0.8). Všechny jsou opravené a níže doložené. **Doporučuji je projít a potvrdit proti metodice** —
u některých jde o interpretaci.

### 1.1 Prázdné souřadnice S-42 → B-index nešel spočítat pro žádný vzorek

**Nejzávažnější nález.** Sloupce `loc.S42_X` a `loc.S42_Y` jsou v databázi
prázdné pro všech 86 lokalit. Predikční model B-index (`B_index2.py`) je
používá jako vstup, takže pro každý vzorek spadl na
`TypeError: unsupported operand type(s) for -: 'NoneType' and 'int'`
a metrika **MB07 nebyla nikdy spočítaná**.

V původním kódu se ale MB07 přesto započítala do multimetriky —
s hodnotou EQR 0 a plnou vahou (1,0–1,3 podle typu). Každý vzorek byl tedy
systematicky penalizovaný, u typu 3-1 jaro například o 20 % výsledné hodnoty.

Nový modul `abiotic_params.py` souřadnice dopočítá z WGS84. Po jejich
doplnění se B-index spočítá pro **25 z 25** testovaných vzorků.

> Ověřeno: model očekává Gauss-Krügerovo zobrazení pásmo 3 (EPSG:28403).
> Odpovídají tomu posuny v `B_index2.transform_vector` (−3 290 000 pro X,
> −5 380 000 pro Y) i řády koeficientů diskriminační matice (~1e−5).

### 1.2 Metrika MB14 vždy vycházela 0

Výpočet abundance pošvatek používal proměnné z metriky MB08:

```python
# původní kód
if is_in_taxonomic_group(taxon_id, e_order, ...):   # e_order = Ephemeroptera!
    e_log_abundance += log(abundance)               # plní se e_, ne p_
...
metrics['MB14'] = round((p_log_abundance / total_log_abundance) * 100, 2)
                         # ^ p_log_abundance zůstalo 0.0
```

Opraveno na `Plecoptera`. Ověřeno na 18 vzorcích, kde se hodnota změnila
z 0,0 na reálnou (např. LOMR_1_J_MZB: 0,0 → 25,13).

### 1.3 Podmínka, která byla vždy pravdivá

Ochranná podmínka opakovaná u každé metriky:

```python
if metrics['MB01'] is not None and not isinstance(metrics['MB01'], float) \
   or not float('nan') == metrics['MB01']:
```

Pravá strana `not (nan == x)` je pravdivá vždy (NaN se nerovná ničemu,
ani sobě), a `or` má nižší prioritu než `and`. Podmínka tedy propouštěla
i `None`, což vedlo k pádům typu
`TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'`
(prokázáno na vzorku SUDP_1_L_MZB a pěti FB vzorcích).

Nahrazeno funkcí `common.je_platna()`.

### 1.4 Skupina 3-1 jaro: metrika MB08 započítaná dvakrát

```python
final_eqr = (... + 0.7*MB06_EQR + 1*MB08_EQR + 0.8*MB08_EQR + 0.6*MB09_EQR)
            / (1 + 1 + 0.7 + 1 + 1.3 + 1 + 0.6)
```

V čitateli je MB08 dvakrát (váhy 1,0 a 0,8) a navíc MB06, které se pro tuto
skupinu vůbec nepočítá (je nastavené na NaN, takže přispívalo nulou).
Jmenovatel 6,6 přitom přesně odpovídá sedmi vahám
1 + 1 + 0,7 + 1 + 1,3 + **1** + 0,6.

Opraveno na váhu MB08 = 1,0, MB06 vyřazeno. Součet vah nyní odpovídá
jmenovateli u všech 28 kombinací.

### 1.5 Skupina 12-3, Strahler 8 a 9: multimetrika vždy NaN

```python
eqr_values['MB10_EQR'] = float('nan')
...
final_eqr = (... + 0 * eqr_values.get('MB10_EQR', 0) + ...) / (...)
```

V Pythonu je `0 * nan == nan`, takže celý čitatel — a tím i výsledek —
vycházel NaN. Týkalo se to čtyř kombinací (12-3 J/P × Strahler 8/9).

Metriky s nulovou vahou se nyní do tabulky vůbec nedostanou.

### 1.6 Metrika MB03 ve skupině 12-3 jaro: chybějící posun v čitateli

```python
eqr_values['MB03_EQR'] = metrics['MB03'] / (0.69 - 0.03)   # 12-3, Strahler 7
```

Ve všech ostatních 25 kombinacích má MB03 tvar
`(MB03 - 0.03) / (horní_mez - 0.03)`. Posun 0,03 ve jmenovateli napovídá,
že v čitateli vypadl. Opraveno pro Strahler 7, 8 i 9.

### 1.7 Fytobentos: synonyma se slučovala do rodu

Taxonomické seznamy kódují synonyma **různě**:

| seznam | sloupec `SYN` | platné jméno je v |
|---|---|---|
| `taxalist_mzb` | příznak `'SYNONYM'` (577×) | `PARENT` |
| `taxalist_fb` | přímo platné jméno (2 081×) | `SYN` |
| `taxalist_mf` | přímo platné jméno (64×) | `SYN` |
| `taxalist_ryby` | přímo platné jméno (13×) | `SYN` |

Sdílená funkce `resolve_synonyms()` používala vždy `PARENT`. U fytobentosu
tedy synonyma padala na rod (`Attheya zachariasii` → `Acanthoceras sp.`
místo `Acanthoceras zachariasii`), čímž se ztrácely druhové trait hodnoty.

Funkce `common.vyres_synonyma()` nyní zkusí nejprve `SYN` a jen když takové
jméno v seznamu neexistuje, sáhne po `PARENT`. Tím je správně obsloužený
MZB i ostatní seznamy. Po opravě zmizely rozdíly v metrice FB_01.

> Pozn.: funkce `hodnoceni_ES_FB_perennial` tuto věc dělala správně
> (používala `SYN`), zatímco `hodnoceni_ES_FB_intermittent` sdílenou
> funkci — tedy chybně. Nekonzistence uvnitř jednoho souboru.

### 1.8 Klasifikace potenciálu: nedosažitelná mez

```python
if final_eqr > 0.6:    eqr_class = "D/L"
elif final_eqr > 4:    eqr_class = "S"     # EQR nikdy nepřekročí 1
```

Druhá větev byla nedosažitelná. Hranice v `common.HRANICE_POTENCIAL` jsou
nyní 0,6 / 0,4 / 0,2. **Prosím ověřit proti metodice** — je možné, že
zamýšlená hodnota byla 0,4 a řádky se jen prohodily.

---

### 1.9 Stav `D` v adjustačním předpisu znamená VYŘADIT, ne „ponechat“

Nejzávažnější nalezená chyba. Původní kód:

```python
if pravidlo['STATE'] == 'D':
    vysledek[taxon_id] = abundance     # ponechat beze změny
```

Že jde o opak, plyne přímo z dat:

* žádné pravidlo `D` nemá vyplněný cíl (`TAXON_SEQ_TO` je prázdné)
* v jarní sadě `METR_J` je pravidel `D` jen 92 a jsou to **výhradně vysoké
  taxony** — `Arthropoda`, `Crustacea`, `Annelida`, `Diptera`, `Insecta`,
  `Hexapoda`, `Gastropoda`, `Araneida`, `Bryozoa`, `Cnidaria`,
  `Coleoptera Ad./Lv.` Záznam určený jen do kmene nelze „ponechat“ — nemá
  traity, ze kterých by se počítalo.
* v podzimní sadě `METR_P` je pravidel `D` 627, protože k nim přibývají
  **všichni pakomáři**. Podzimní hodnocení tedy pakomáry z výpočtu vyřazuje —
  proto má oficiální MB11 u 91 % podzimních vzorků hodnotu 0.

Ověřeno na `KAZI_1_P_MZB`: po vyřazení pakomárů vychází MB04 = 44,84750
a MB05 = 1,82167, tedy přesně oficiální hodnoty.

### 1.10 Adjustační předpis odkazuje na stará jména taxonů

Pořadí kroků bylo `vyřeš synonyma → adjustuj`. Jenže adjustační předpis
vznikl nad starší verzí taxonomického seznamu a odkazuje na ID, která jsou
dnes vedená jako **synonyma**:

| ve vzorku / v předpisu | v dnešním seznamu | pravidlo `PRED_*` |
|---|---|---|
| `Pisidium personatum` | `Euglesa personata` | → `Pisidium sp.` |
| `Serratella ignita` | `Ephemerella ignita` | → `Ephemerella ignita` |
| `Oreodytes sanmarkii Ad.` | `Nectoporus sanmarkii Ad.` | → `Oreodytes sanmarkii Ad.` |

Po vyřešení synonyma se taxon jmenuje `Euglesa personata` a **pod tímto ID
už žádné pravidlo neexistuje** — zůstal tedy na druhové úrovni místo aby se
sloučil na rod. U indexu B se navíc rodové jméno `Pisidium sp.` shoduje
s tím, co očekává predikční model, takže se predikovaný taxon nikdy
nespároval a index vycházel systematicky nižší.

`vyres_synonyma()` nyní volitelně vrací mapování `{platné_id: původní_id}`
a `aplikuj_adjustace()` sáhne po pravidle původního ID, pokud pro platné
jméno žádné není.

Dopad na MB07: shodných hodnot **318 → 384 z 408 (94 %)**, jarní vzorky
sedí prakticky beze zbytku (202 z 203).

### 1.11 Index B: predikční model drží stará jména taxonů

Predikční model si nese jména taxonů ve stavu, v jakém byla podkladová
databáze pořízena. Část z nich je dnes v taxonomickém seznamu vedená jako
**synonymum** novějšího jména:

| predikční model | dnešní platné jméno |
|---|---|
| `Lasiocephala basalis` | `Lepidostoma basale` |
| `Serratella ignita` | `Ephemerella ignita` |
| `Oreodytes sanmarkii Ad.` | `Nectoporus sanmarkii Ad.` |

Data vzorku přes `vyres_synonyma()` projdou, a jsou tedy už pod platnými
jmény. Predikce ne — takový taxon se proto nikdy nespároval a index B
vycházel systematicky nižší.

`mapa_synonym()` v `common.py` teď sestaví převod
`{normalizované jméno: normalizované platné jméno}` (586 synonym z 5947
záznamů seznamu) a `_b_index()` ho použije na obě strany porovnání.

Samotná `Lasiocephala basalis` stála za odchylkou u **12 z 15** postižených
kombinací lokalita + sezóna.

**Shoda MB07 s ARROW: 374/396 (94 %) → 395/396 (99,7 %)**, korelace
0,99881 → 0,99996. Poslední vzorek dořešila oprava 1.12.

### 1.12 Podrod: záznam „Rod (Podrod) sp." patří k podrodu, ne k rodu

`_bez_podrodu()` odstraňovala závorku ze všech jmen, takže

    Cricotopus (Paratrichocladius) sp.  ->  Cricotopus sp.

Jenže záznam na úrovni PODRODU neznamená „nějaký zástupce rodu", ale
konkrétní podrod, který byl dříve samostatným rodem — a právě pod tím
starým rodovým jménem ho zná predikční model. Vzorek `SAZA_3_J_MZB` má
`Paratrichocladius rufiventris`, adjustace ho sloučí na
`Cricotopus (Paratrichocladius) sp.`, a ten po odstranění závorky chybně
sedl na predikovaný `Cricotopus sp.` (77,8 %). Model přitom oba taxony
rozlišuje — `Paratrichocladius sp.` predikuje s pravděpodobností 0,7 %,
tedy hluboko pod limitem.

Nově se u záznamů končících na `sp.` bere jméno podrodu, u druhů se
závorka odstraňuje dál (`Simulium (Simulium) noelleri` →
`Simulium noelleri`). Zároveň odpadla ruční položka
`"paratrichocladius sp.": "cricotopus sp."` v `NAZVOVE_OPRAVY`, kterou
pravidlo nahradilo.

**Index B tím sedí na 406 ze 406 vzorků, korelace 1,00000.**

### 1.13 Zaokrouhlení jmenovatele indexu B — v referenčních datech není

Kód z ARROW zaokrouhluje očekávaný počet taxonů na desetiny:

```pascal
Bind := poc_ocek_tax_vzk / (floor((sum_pravd * 10) + 0.5) / 10);
```

Referenční hodnoty tímhle ale spočítané nejsou. Ověřeno na 252 vzorcích
s indexem menším než 1, které sedí na pět desetinných míst
s **nezaokrouhleným** součtem — a jen u 15 z nich je součet náhodou
násobkem 0,1. Například `MOLO_2_P_MZB`: 14 / 24,3866 = 0,57409 přesně sedí
na ARROW, zatímco 14 / 24,4 = 0,57377 nikoli.

Zavedení zaokrouhlení shodu zhorší z **94 % na 69 %**, proto se
neimplementuje. Zřejmě jde o jinou verzi výpočtu, než ze které pochází
referenční tabulka.

### 1.14 Typ 2-1 jaro: ARROW počítá se špatnými horními mezemi

U **všech 30** jarních vzorků typu 2-1 se EQR metrik RETI a Margalef liší,
přestože hodnota metriky sedí přesně. Zpětná regrese EQR na hodnotu metriky
dává meze, které ARROW použil, s **R² = 1,000000**:

| metrika | dolní mez | horní mez podle ARROW | horní mez podle metodiky (Tab. 3) |
|---|---|---|---|
| MB03 RETI | 0,03 | **0,86** | 0,81 |
| MB05 Margalef | 0,40 | **8,4** | 7,7 |

Hodnoty 0,86 a 8,4 jsou přesně ty, které Tab. 3 uvádí pro typ **3-1**
(tedy o řádek níž). ARROW přitom vybírá sadu metrik správně podle 2-1
(má vyplněné EPT Abu i Metaritrál, které 3-1 nepoužívá) — liší se jen
ty dvě horní meze.

**Pravdu má metodika, ne ARROW.** Dokazují to hraniční hodnoty tříd, které
Tab. 3 uvádí ve stejném řádku — musí ležet na EQR 0,8 / 0,6 / 0,4 / 0,2:

| | horní mez | hranice v Tab. 3 | dopočteno z mezí |
|---|---|---|---|
| Margalef 2-1 | 7,7 | 6,24 / 4,78 / 3,32 / 1,86 | **6,24 / 4,78 / 3,32 / 1,86** ✓ |
| Margalef 2-1 | *8,4* | 6,24 / 4,78 / 3,32 / 1,86 | 6,80 / 5,20 / 3,60 / 2,00 ✗ |
| RETI 2-1 | 0,81 | 0,65 / 0,50 / 0,34 / 0,19 | **0,654 / 0,498 / 0,342 / 0,186** ✓ |
| RETI 2-1 | *0,86* | 0,65 / 0,50 / 0,34 / 0,19 | 0,694 / 0,528 / 0,362 / 0,196 ✗ |

U Margalefa sedí dopočet na setiny přesně. Řádek pro typ 2-1 je tedy
vnitřně konzistentní s mezemi 0,81 a 7,7; hodnoty 0,86 a 8,4 patří typu
3-1, který je v tabulce hned pod ním.

Přepínač `mzb_perennial_broditelne.MEZE_DLE_ARROW` (výchozí `False`) umožní
přepnout na chování ARROW při porovnávání výsledků:

| | metodika | dle ARROW |
|---|---|---|
| MB03 RETI, EQR | 64 % (r 0,98865) | **76 %** (r 0,99906) |
| MB05 Margalef, EQR | 84 % (r 0,99265) | **96 %** (r 0,99986) |
| MB_CELKEM, shodná třída | 98,0 % | 98,5 % |

Zpětná regrese EQR na hodnotu metriky (R² = 1,000000) potvrdila, že
**u všech ostatních skupin toků jsou meze shodné** — 2-1 jaro je jediná
odchylka. Seznam dotčených vzorků a lokalit je v
`EQR_odskocene_vzorky.csv`.

---

## 2. Změny, které nejsou opravou chyby, ale mění chování

Obojí je řízené konstantou v `src/calc_index/common.py`, takže se dá vrátit
jednou změnou.

### 2.1 `CHYBEJICI_METRIKA` (výchozí `"vynechat"`)

Když metriku nelze spočítat:

* `"vynechat"` — do multimetriky nevstoupí vůbec (ani do jmenovatele).
  Výsledek se počítá z metrik, které k dispozici jsou.
* `"nula"` — vstoupí s hodnotou EQR 0, ale plnou vahou (chování původního
  kódu). Každá nespočítaná metrika výsledek výrazně strhne dolů.

### 2.0 `TAXON_BEZ_PRAVIDLA` (výchozí `"ponechat"`)

Otestováno i chování „taxon, který v předpisu není, vyřaď (jako `D`)“.
Na 539 vzorcích s oficiálními hodnotami je **výrazně horší**:

| | ponechat | vyřadit |
|---|---|---|
| MB_CELKEM, shodná třída | 98 % | 91 % |
| MB13 EPT Tax, shodných | 92 % | 7 % (medián −2 taxony) |
| MB04 EPT Abu | 87 % | 3 % (medián −1,94) |
| MB08 Jep Abu | 87 % | 4 % (medián −1,98) |
| MB12 počet čeledí | 34 % | 36 % (medián −1) |

Vyřadily by se totiž i početné druhové agregáty
(`Baetis fuscatus/scambus`, `Rhithrogena carpatoalpina/iridina/picteti`,
`Sericostoma personatum/schneiderii`), které do hodnocení jednoznačně patří
— v předpisu chybí jen proto, že u nich není co adjustovat.

**Adjustační předpis tedy není uzavřený seznam hodnocených taxonů, ale
seznam potřebných úprav.** Přepínač zůstává v kódu pro případ, že by se
ukázalo něco jiného.

Seznam všech 36 taxonů bez pravidla je v `taxony_bez_adjustace.csv`.

### 2.2 `OREZAVAT_EQR` (výchozí `True`)

Původní kód nechával EQR vyjít i záporné nebo nad 1 (např. MI02_EQR
= −0,0281, MI04_EQR = 2,069 u vzorku SUDP_1_L_MZB). Nově se ořezává do
⟨0; 1⟩. Nastavte `False` pro původní chování.

> Pozor: `OREZAVAT_EQR` se uplatní jen u metodik, které jdou přes
> `common.preved_na_eqr()` (MZB, fytobentos vysychavý). Fytobentos
> stáletekoucí a makrofyta počítají EQR přímo vlastním vzorcem, takže
> u nich hodnoty nad 1 zůstávají (FB_CELKEM max 1,072; MF_CELKEM max 1,2).
> Na zařazení do třídy to nemá vliv. Ponecháno shodně s původním kódem —
> **prosím posoudit, zda je to podle metodiky v pořádku.**

### 2.3 Logaritmus abundance ≤ 1

Původní kód volal `log(abundance)` bez ochrany — pro abundanci 0 spadl,
pro abundanci mezi 0 a 1 (vzniká po redistribuci adjustací typu `R`)
použil **záporný** logaritmus jako váhu, což může jmenovatel vážného
průměru přiblížit nule.

Nově se taxony s `log(abundance) ≤ 0` z vážených průměrů vynechávají
(`common.safe_log`). Dopad je malý — dotčeno 3–5 vzorků, změny řádu
0,1 % (např. MB02 u DORL_2_J_MZB: 35,028 → 34,982).

---

## 3. Ověření

Skripty v `_tools/`:

| skript | co dělá |
|---|---|
| `extract_eqr.py` | vytáhne EQR tabulky z původního if/elif stromu přes AST |
| `normalize_eqr.py` | převede výrazy na `(dolní_mez, horní_mez, invert)` a **numericky ověří** ekvivalenci proti původním výrazům (50 náhodných hodnot na metriku) |
| `gen_table.py` | vygeneruje `mzb_perennial_broditelne_table.py` a vypíše provedené opravy |
| `regrese.py` | spustí starý i nový výpočet nad reálnými daty a porovná |
| `vykon.py` | měření rychlosti |
| `qtstub/` | náhrada PyQt6 nad `sqlite3`, aby šel výpočet testovat bez GUI |

Výsledky:

* všech **28 kombinací** (typ lokality × sezóna × Strahler) vytaženo
  a numericky ověřeno proti původnímu kódu
* rozřazovací tabulka `registry.REGISTR` dává pro všech 20 kombinací
  složka × kategorie × vysychavost × broditelnost **shodný výsledek**
  s původním `select_hodnoceni_function`
* metrika STRAHLER dopočítaná z shapefilu reprodukuje **10 z 10** hodnot
  už uložených v databázi
* regresní běh na 157 reálných vzorcích: rozdíly odpovídají výhradně
  opravám 1.2, 1.4–1.7 a změnám v části 2

### Rychlost

30 vzorků MZB: **4,12 s → 0,87 s (4,5×)**.

Hlavní úspora nepochází z odstranění if/elif, ale ze dvou míst:

1. **Lineární hledání v cache** — původní kód měl 15× vzor
   ```python
   for name, info in taxon_cache.items():
       if info['ID'] == taxon_id: ...
   ```
   tedy průchod desítkami tisíc taxonů pro *každý* taxon ve vzorku.
   Nahrazeno indexem `by_id`.
2. **Opakované načítání taxalistu** — `taxalist_mzb` se načítal znovu pro
   každý vzorek. Nyní se cachuje (`common._CACHE`, vyprázdní se na začátku
   každé dávky).

---

## 4. Co zůstává nedořešené

* `MNM` a `SLOPE` — spoléhají na online službu ČÚZK (DMR 5G s přepadem
  na 4G). Doporučuji výsledky namátkově ověřit.
* MZB nebroditelné toky (ekologický stav) — metodika není k dispozici,
  zůstává jako zástupná funkce v `calc_index/neimplementovane.py`
* Hranice klasifikace potenciálu (viz 1.8)

---

## 5. Stojaté vody (kategorie jezero)

Zdroj: Borovec J. a kol. (2014), *Metodika pro hodnocení ekologického
potenciálu silně ovlivněných a umělých vodních útvarů — kategorie jezero*.

### 5.1 Typologie sedí na 72 ze 77 útvarů

Kód `A-B-C-D-E-F-G-H` odvozený podle Tabulky 1 se u pěti útvarů rozchází
s kódem vytištěným v Příloze 1. Ve všech případech jsem se držel **pravidel
z Tabulky 1**, protože ta jsou normativní; rozpory jsou vypsané
v `calc_index/jezera_utvary.ROZPORY`.

| útvar | Příloha 1 | podle Tab. 1 | v čem |
|---|---|---|---|
| Orlík I, II, III | D=1, G=1 | D=2, G=2 | zmax 45–68 m a zprum 13–27 m nemohou být „mělké" |
| Lučina | H=3 | H=2 | TRT 0,13 spadá do pásma 0,1–0,5 |
| Slapy | H=2 | H=1 | TRT vytištěno 0,10, což je podle tabulky ještě H=1 |

Tři z pěti jsou zjevné překlepy (celý Orlík), Lučina je rozpor tabulky se
sebou samou. U Slap jde nejspíš o zaokrouhlení skutečné hodnoty nad 0,1 —
všechny ostatní útvary s TRT ≤ 0,09 mají H=1 a od 0,10 výš H=2.

### 5.2 Pozice B, C a F na nic nemají vliv

Metodika (str. 7) říká, že hraniční hodnoty metrik určuje **jen** nadmořská
výška (A), průměrná hloubka (G) a doba zdržení (H). Zbytek kódu je popisný.
Moduly proto vyhledávají meze podle zkráceného klíče:

| složka | klíč |
|---|---|
| fyzikálně-chemické složky, fytoplankton | (A, H) |
| ryby | (A, G) |
| makrofyta | žádný — meze jsou pro všechny typy stejné |

### 5.3 Podíl sinic se počítá i bez taxalistu

Metrika FPJ03 potřebuje vědět, které taxony jsou sinice. Kdyby se spoléhala
jen na taxalist, u databáze bez taxalistu fytoplanktonu stojatých vod by
tiše vycházela nulová — a nula je zároveň **nejlepší možná** hodnota, takže
by chybějící data vypadala jako čistá voda.

Příloha 2 vede u každého rodu i třídu, takže se zařazení dohledá z ní
(`jezera_fp_optima.zarazeni`). Biomasa, u které se třídu určit nepodaří, se
sečte a ohlásí v poznámce.

### 5.4 EQR se nepočítá z hrstky metrik

Chybějící metrika se neboduje vůbec, takže vzorek s jedinou spočítanou
metrikou by dostal plnohodnotně vypadající EQR. Nejhorší kombinace je
„chybí skoro všechno" + „to zbylé vyšlo špatně": výsledkem je EQR 0,00
a třída *zničený potenciál*, což je tvrzení o stavu útvaru, pro které
data nejsou.

Proto se EQR sestaví jen tehdy, když jde spočítat aspoň polovina metrik
(`jezera_common.MIN_PODIL_METRIK`), jinak se vrátí `None` s vysvětlením.

### 5.5 Import ryb musí rozlišovat sítě

Import vzorků slučoval řádky podle (SAMPLE, NAME, TYP, LOC_ID, DATE). U ryb
ve stojatých vodách to nestačí — tentýž druh uloví bentická i pelagická
tenatní síť a metriky CZ-FBI je rozlišují. Plotice z BT a PT se slila do
jednoho řádku a většina metrik se pak nedala spočítat. Do klíče přibyly
`SIT` a `ZONA`.

Zároveň přestal být povinný sloupec `VAL` — u fytoplanktonu ho nahrazuje
`BIOMASA`, u makrofyt `POKRYVNOST`. Nová kontrola vyžaduje, aby byla
vyplněná aspoň jedna z těch tří.

---

## 6. Makrofyta v tocích — porovnání s ARROW

Podklad: `export_MF_brod_vzorky.csv`, 33 vzorků z broditelných toků.
Report: `porovnani_metrik_MF.html`, generuje `_tools/porovnani_mf.py`.

### 6.1 Výsledek

| veličina | korelace | shodných |
|---|---|---|
| index MTV | 0,99810 | 20/32 |
| EQR | 0,99807 | 20/32 |
| počet indikátorových taxonů | 0,98080 | 24/33 |
| typ toku | — | **33/33** |
| třída ekologického stavu | — | **32/33** |

Rozpad podle typu je jednoznačný:

| typ | n | shodných MTV | medián \|Δ\| |
|---|---|---|---|
| 1 — horské toky nad 500 m | 14 | **2/14** | 0,097 |
| 2A, 2B, 3, 4A, 4B | 18 | **18/18** | 0,000 |

**Mimo typ 1 sedí index MTV na pět desetinných míst u všech 18 vzorků.**
Vážený vzorec `MTV = Σ(E·mtv) / ΣE`, transformace pokryvnosti do stupňů
1–5 i zařazení do typů toku jsou tedy správně.

### 6.2 Opraveno: kategorie OTHER v taxalistu

Metodika (kap. 5) zná jen **dvě** skupiny druhů:

* **stenovalentní** — pět vyjmenovaných druhů ze skupiny A+D, tj. vázaných
  na nadmořské výšky nad 500 m a vody s nízkou konduktivitou (*Fontinalis
  squamosa*, *Myriophyllum alterniflorum*, *Potamogeton alpinus*,
  *P. polygonifolius*, *Scapania undulata*);
* **širokovalentní** — všechny ostatní.

`taxalist_mf` má u čtyř druhů (*Lemanea*, *Nuphar pumila*, *Ranunculus
aquatilis*, *Zannichellia palustris*) třetí hodnotu `OTHER`, kterou
metodika nezná. Všechny čtyři jsou v Tab. 6 ve skupinách B nebo C, tedy
širokovalentní.

Původní SQL je do pravidla alternujícího druhu nezahrnovalo — zůstávaly
stranou jako samostatné záznamy. Opraveno: cokoli jiného než `STEN` se
bere jako širokovalentní. Medián odchylky v typu 1 tím klesl
z **0,314 na 0,100** bodu MTV a korelace z 0,99548 na 0,99756; mimo typ 1
se nezměnilo nic.

### 6.3 Opraveno: alternující druh se v typu 1 uplatní vždy

Metodika pravidlo alternujícího druhu podmiňuje: *„V případě společného
výskytu druhů **obou** skupin…"* Stenovalentní druhy jsou ale všechny
vázané na výšky nad 500 m, takže doslova vzato připadá pravidlo v úvahu
jen v typu 1 — a v tomtéž typu se hodnoty rozcházely.

ARROW ho v typu 1 uplatňuje **i tam, kde žádný stenovalentní druh není**:
sloučí všechny širokovalentní do jednoho a index pak vyjde jako prostý
průměr jejich MTV. Odpovídá to větě, kterou metodika pravidlu předesílá:
*„u typu vod 1 dochází … ke zkreslení výsledků … V tomto typu vod je proto
vhodnější provést výpočet jiným způsobem."*

Ověřeno na všech třech vzorcích typu 1 bez stenovalentních druhů:

| vzorek | ARROW | vážený průměr | alternující druh |
|---|---|---|---|
| REF_081_III | 5,600 | 6,154 | **5,600** |
| REF_027_III | 6,000 | 6,278 | **6,000** bez *Lemanea* |
| REF_081_II | 7,500 | 7,813 | **7,500** bez *Lemanea* |

`MTV_SQL` proto bere navíc příznak „agregovat i bez stenovalentních
druhů", který `hodnoceni()` nastaví podle typu toku
(`_agregovat_vzdy()`). Korelace stoupla z 0,99756 na 0,99810, největší
rozdíl klesl z 0,554 na 0,500. Mimo typ 1 se nezměnilo nic — pořád 18/18.

### 6.3.1 Modelový příklad: REF_081_III

Vzorek obsahuje osm taxonů, z toho pět skórujících. Snadno se přehlédne,
že **`Batrachium aquatile` je synonymum pro `Ranunculus aquatilis`**,
který Tab. 6 vede jako skórující druh skupiny C s MTV 8:

| výpočet | hodnota |
|---|---|
| 4 taxony bez *Ranunculus aquatilis*, vážený | 48/9 = 5,333 |
| 5 taxonů, vážený průměr | 80/13 = 6,154 |
| 5 taxonů jako alternující druh (prostý průměr MTV) | 28/5 = **5,600** |

### 6.4 Zbytek rozdílu v typu 1 se reprodukovat nedaří

Zbývá 11 vzorků typu 1, které stenovalentní druhy **mají** — tam LULAN
agreguje stejně jako ARROW a přesto zůstává rozdíl 0,04 až 0,22 bodu MTV.

Otestované varianty (žádná nepomohla):

* alternující druh s pokryvností jako součet / maximum / medián místo průměru
* MTV alternujícího druhu vážená pokryvností
* agregace stenovalentních druhů do jednoho záznamu
* váha alternujícího druhu jako volný parametr — vychází pro každý vzorek
  jiná (1,17 / 1,28 / 1,58), takže o konstantu nejde
* vypuštění jednoho či dvou taxonů (hrubá síla přes všechny kombinace)
* hrubá síla přes všechna přiřazení stupňů pokryvnosti 1–5

U `REF_030_II` je průkazné, že ARROW nepočítá vážený průměr s celočíselnými
váhami: hodnota 9,47945 nad taxony s MTV 10, 10, 9 a 8 na žádnou takovou
kombinaci nepadne. Váha alternujícího druhu tedy celé číslo není, ale ani
průměr pokryvností ji nereprodukuje.

**Závěr: buď ARROW počítá s jinými hodnotami pokryvnosti, než jsou
v databázi, nebo u vzorků se stenovalentními druhy používá ještě další
nezdokumentovanou úpravu.** Rozdíl je věcně malý — třída ekologického
stavu sedí u 32 z 33 vzorků.

### 6.4 Taxalist proti Tab. 6 metodiky sedí

Kontrola všech 42 skórujících druhů: stejný počet, stejná MTV skóre,
stejné zařazení stenovalentních. Dva druhy má taxalist pod platným
současným jménem:

| metodika (2019) | taxalist |
|---|---|
| *Lemanea fluitans* | *Lemanea fluviatilis* |
| *Potamogeton pectinatus* | *Stuckenia pectinata* |

Obojí je správně — jde o platná jména; LULAN se drží metodiky a *Lemanea*
skóruje. **ARROW ji ale nezapočítává:**
počet indikátorových taxonů sedí u **32 z 33** vzorků, když se z výpočtu
vypustí. Metodika ji přitom výslovně mezi skórující druhy řadí (kap. 2:
*„považujeme za vhodné ke skórujícím druhům makrofyt zařadit také …
zejména druh Lemanea fluitans"*, a Tab. 6 jí dává MTV 9).

Vypadá to, že ARROW má v taxalistu staré jméno *L. fluitans*, kdežto data
z monitoringu chodí pod jménem *L. fluviatilis*, takže se taxon nespáruje
a do výpočtu nevstoupí. To je nedopatření na straně ARROW, ne LULANu —
ale vysvětluje rozdíl v počtu taxonů a část rozdílu v MTV.

Jediná další nesrovnalost je `REF_196_III`: v databázi má vzorek jediný
taxon (*Agrostis stolonifera*, bez MTV), ARROW počítal se dvěma. Tam chybí
data, ne výpočet.

---

## 7. Ryby — taxony bez příznaku tiše nadhodnocovaly ND1 a ND2

Vzorky `RV_082`, `RV_220` a `RV_086` vycházely na CZI 0,25 (resp. 0,30),
přestože je celé tvoří jediný nepůvodní druh.

### 7.1 Jak to vzniklo

Aritmetika seděla: (0×1,8 + 0×1,2 + **1**×0,4 + **1**×0,6) / 4 = 0,25.
Celá hodnota pocházela z metrik ND1 a ND2, které dostaly plný počet bodů,
protože ve vzorku „nebyl žádný nežádoucí taxon".

Příčina **není** v chybějícím ořezání hodnoty — `ryby_metriky.eqr()` mez
uplatňuje hned na začátku (`hodnota = min(hodnota, mez)`).

Příčina je v tom, že **taxon bez příznaku R / EL / I nevstoupí do žádné
metriky, ale do celkové abundance ano.** U ND1 a ND2 to skóre tiše zvyšuje:
vzorek složený výhradně z neskórovaného druhu vypadá jako „žádné nežádoucí
taxony". Konkrétně `Carassius auratus` (karas zlatý) v `taxalist_ryby`
žádný příznak nemá.

### 7.2 Rozpouštění synonym funguje, taxalist odpovídá Tab. 4

Kontrola proti Tabulce 4 metodiky (Janáč a kol. 2019): všech **61
skórujících taxonů** je v taxalistu se správnými příznaky, žádný nechybí
a žádnému příznak nechybí. Dalších 26 záznamů s příznakem jsou rozpisy
souhrnných taxonů (*Lampetra* sp. → *L. fluviatilis*/*planeri*, *Gobio*
sp., *Cottus* sp., *Coregonus* sp., formy *Salmo trutta*) — v pořádku.

Synonyma se rozpouštějí správně: *Aspius aspius* → *Leuciscus aspius*,
*Abramis bjoerkna* → *Blicca bjoerkna*, *Proterorhinus marmoratus* →
*P. semilunaris*.

### 7.3 Doplněno: karas zlatý jako nepůvodní

Karas zlatý (*Carassius auratus*) **není synonymum** karase stříbřitého
(*Carassius gibelio*) — jde o samostatný platný druh. Tabulka 4 ho nevede,
ale ekologicky patří mezi nepůvodní invazní druhy stejně jako karas
stříbřitý. Po odsouhlasení zadavatelem mu byly doplněny příznaky
**EL = 1 a I = 1**.

Zapisuje je `_tools/oprava_taxalist_ryby.py --doplnit` (tabulka `DOPLNIT`
v hlavičce skriptu). Bez přepínače skript nic nemění, jen zkontroluje.
Sloupec `SYN` zůstává prázdný — o synonymii nejde.

Dopad na 640 vzorků ryb: změnilo se CZI u **35** vzorků, třída u **17**.

| vzorek | před | po |
|---|---|---|
| RV_082 | 0,250 (P) | **0,000 (Z)** |
| RV_220 | 0,250 (P) | **0,000 (Z)** |
| RV_086 | 0,300 (P) | **0,071 (Z)** |
| RV_211 | 0,340 (P) | 0,105 (Z) |
| RV_216 | 0,562 (S) | 0,335 (P) |

### 7.4 Tři druhy Tabulka 4 neskóruje

| druh | český název | výskyt |
|---|---|---|
| *Ameiurus nebulosus* | sumeček americký | 3 vzorky, 113 jedinců |
| *Salmo salar* | losos obecný | 2 vzorky, 6 jedinců |
| *Sabanejewia aurata* | sekavčík (starší jméno) | 1 vzorek, 5 jedinců |

Zůstávají bez příznaku — jejich zařazení je odborné rozhodnutí a taxalist
se aktualizuje samostatně. U *S. aurata* jde nejspíš o starší souhrnné
jméno pro *S. balcanica*, ale ztotožnit je bez potvrzení nechci.

### 7.5 Co s tím dělá LULAN

Zařazení taxonů LULAN sám nemění. Nově ale takový případ **neschová**:
`ryby_metriky.bez_priznaku()` vypíše každý taxon vzorku bez příznaku
R / EL / I do poznámky výsledku:

```
… nezadouci taxony: invazni; POZOR: metodika neskoruje
Ameiurus nebulosus - do metrik nevstupuje
```

Pracovní seznam pro aktualizaci taxalistu vypíše
`_tools/oprava_taxalist_ryby.py` — porovná taxalist s Tab. 4 metodiky
a vypíše taxony vzorků, které po rozpuštění synonym zůstanou bez příznaku.
Skript nic nemění.

---

## 8. Nehodnocené vzorky se zapisují jako NA s důvodem

Po přepočtu hlásila aplikace „úspěšně vyhodnoceno 1601 z 1639". Zbylých
38 vzorků metodika nehodnotí — ale v tabulce `results` po nich nezůstala
žádná stopa, takže to v aplikaci vypadalo jako selhání výpočtu.

### 8.1 Co se změnilo

Vzorek, který nelze vyhodnotit, dostane nově řádek v `results`:

| sloupec | hodnota |
|---|---|
| `METRIC` | `<složka>_CELKEM` |
| `VAL`, `VAL_EQR` | prázdné |
| `CLASS` | `NA` |
| `POZN` | důvod |

Roční agregace takový řádek přeskočí — vybírá jen `VAL_EQR IS NOT NULL`
a třídu doplňuje jen tam, kde EQR vyšlo. Ověřeno: 116 agregovaných
záznamů před i po, žádná třída `NA` v `results_year`.

Dialog po výpočtu nově rozlišuje tři čísla:

```
Zpracováno vzorků: 1639
Úspěšně vyhodnoceno: 1601
Nehodnoceno podle metodiky: 38
```

### 8.2 Důvody jsou formulované tak, aby šlo rozlišit příčinu

Ne každé „nehodnoceno" znamená totéž. Rozlišují se dvě situace:

**Metodika vzorek nehodnotí** — nic se s tím dělat nedá:

| složka | podmínka |
|---|---|
| ryby | tok 1.–3. Strahlerova řádu |
| makrofyta | tok 1.–3. Strahlerova řádu |
| fytoplankton | mimo 7.–9. Strahlerův řád |
| MZB velké řeky | vzorek mimo letní kampaň |
| MZB | kombinace nadm. výšky a řádu mimo typologii |

**Chybí data** — spravitelné:

* `Nehodnoceno: chybí abiotické parametry lokality (nadmořská výška,
  Strahlerův řád)` — dřív to hlásilo `Nelze urcit typ lokality pro
  MNM=None, STRAHLER=None`, což vypadalo jako chyba výpočtu;
* `Nehodnoceno: vzorek neobsahuje žádný skórující taxon makrofyt`.

### 8.3 Rozpad 38 nehodnocených vzorků

| n | složka | důvod |
|---|---|---|
| 13 | MZB | kombinace výšky a řádu mimo typologii (800,5 m + 3. řád; 894,7 m + 5. řád) |
| 12 | RYBY | tok 2. a 3. Strahlerova řádu |
| 6 | MZB | chybí abiotické parametry lokality |
| 6 | MZB | velké řeky mimo letní kampaň |
| 1 | MF | vzorek bez skórujícího taxonu |

Šest vzorků MZB bez abiotických parametrů je jediná položka, kterou lze
spravit doplněním dat — buď ručně, nebo tlačítkem „Doplnit abiotické
parametry".


## 9. Fytobentos — porovnání s ARROW

Kontrola proti exportu z IS ARROW (`kontrola_vysledku/LULAN_vzorky_kontrola_FB.csv`,
409 vzorků). Sestavu vyrábí `_tools/porovnani_fb.py`, výstup
`porovnani_metrik_FB.html` má stejné rozvržení jako u MZB a makrofyt.

### 9.1 Výchozí stav

| veličina | shoda |
|---|---|
| FB01 — saprobní index | 343/409 |
| SOUCET_VAH — součet indikačních vah | 340/409 |
| FB03, FB04 | nepočítaly se |

### 9.2 Co je `SOUCET_VAH`

První stopa vedla vedle. Sloupec `SOUCET_VAH` neseděl ani jednou, protože
se porovnával se jmenovatelem indexu. To jsou ale dvě různé veličiny:

```
jmenovatel indexu   = sum(h * w)     vážený abundancí
součet vah Sw       = sum(w)         nevážený
```

Metodika (odst. 6.6) definuje `Sw` jako „součet indikačních vah taxonů —
indikátorů ve vyhodnocovaném vzorku". Slouží jako míra důvěryhodnosti
stanovení, ne jako dělitel. Po opravě porovnání seděl `Sw` u 340 vzorků,
tedy přesně u těch, kde seděl i index — což ukázalo, že rozdíl není ve
vzorci, ale v tom, **které taxony do výpočtu vstupují**.

### 9.3 Příčina: osm taxonů v `taxalist_FB`

Živá tabulka `taxalist_FB` se rozešla se zálohou `taxalist_fb_zaloha`,
která odpovídá taxalistu použitému v ARROW. Rozdíl u taxonů vyskytujících
se ve vzorcích je přesně osm položek:

| taxon | taxalist | záloha (= ARROW) | vzorků |
|---|---|---|---|
| *Surirella lacrimula* | MSZS 1,9 / MSZG 1 | — | 37 |
| *Fragilaria recapitellata* | MSZS 1,6 / MSZG 1 | — | 24 |
| *Nitzschia kuetzingii* | MSZS 2,7 / MSZG 4 | — | 7 |
| *Stauridium tetras* | MSZS 2,1 / MSZG 3 | — | 3 |
| *Lepocinclis acus* | MSZS 2,4 / MSZG 3 | — | 1 |
| *Gyrosigma scalproides* | MSZS 2,2 / MSZG 3 | řádek chybí | 1 |
| *Eunotia arcus* | MSZS 0,4 / MSZG 4 | řádek chybí | 1 |
| *Pinnularia neomaior* | **řádek chybí** | MSZS 0,6 / MSZG 4 | 3 |

Prvních sedm LULAN skóroval navíc, poslední naopak vůbec nezapočítal.
Hodnota u *Pinnularia neomaior* se přitom dala odvodit i nezávisle: ze
tří vzorků, kde se vyskytuje, vychází při MSZG 4 shodně MSZS 0,600 —
tedy přesně to, co má záloha. To je nezávislé potvrzení, že rozdíl
nespočívá ve vzorci.

Nástroj `_tools/kontrola_taxalist_fb.py` rozdíly vypíše a přepínačem
`--srovnat` je srovná se zálohou. Ve výchozím stavu nic nemění —
autekologické hodnoty jsou odborný údaj, ne technikálie.

### 9.4 Zaokrouhlený index vstupoval do EQR

Druhá, drobnější chyba: `fb_perennial.py` dosazoval do vzorce pro EQR už
zaokrouhlený saprobní index. U 52 z 409 vzorků to posunulo EQR o 0,001.
Třídu ekologického stavu to na tomto souboru nepřehodilo u žádného
vzorku, ale u hodnoty těsně na hranici (0,5995 vs. 0,600) by ji přehodit
mohlo. Nyní se zaokrouhluje až výsledek.

### 9.5 Doplněné metriky FB03 a FB04

ARROW exportuje dvě veličiny, které LULAN nepočítal. Metodika je zavádí
v odst. 6.5 a 6.6 jako míru důvěryhodnosti stanovení:

```
FB03  střední chyba indexu
      s = sqrt( sum((S - I)^2 * h * w) / ((n - 1) * sum(h * w)) )     [8]

FB04  spolehlivost stanovení
      R = Sw / 50 + 0,20 / s
      R < 1  nespolehlivé,  1 ≤ R < 2  málo spolehlivé,  R ≥ 2  spolehlivé
```

Obě se nově ukládají do `results`, spolu se součtem vah (`FB_SW`).
Slovní hodnocení spolehlivosti je součástí poznámky u výsledku. Klesne-li
součet vah pod 30, poznámka navíc upozorní na odst. 6.8.1 metodiky —
v takovém vzorku už může převažovat heterotrofní složka a hodnocení podle
fytobentosu ztrácí oporu.

### 9.6 Stav po opravě

| veličina | shoda |
|---|---|
| FB01 — saprobní index | **409/409** |
| FB01EQR — EQR | **409/409** |
| SOUCET_VAH — součet vah | **409/409** |
| FB03 — střední chyba | **409/409** |
| FB04 — spolehlivost | **409/409** |
| FB_CELKEM | **409/409** |

Fytobentos je tak po makrozoobentosu druhá složka, kde se hodnocení
LULANu shoduje s ARROW beze zbytku.

### 9.7 Kontrola proti záloze nyní hlídá i chybějící řádky

`common.zkontroluj_traity()` porovnávala taxalist se zálohou přes `JOIN`,
takže si všimla jen změněných hodnot u taxonů přítomných v obou
tabulkách. *Pinnularia neomaior*, která v živém taxalistu vůbec nebyla,
jí proto unikla. Kontrola nyní prochází i taxony přítomné jen v jedné
z tabulek.

## 10. Vysychavé toky (MZB) — porovnání s kalibračními daty metodiky

Kontrola proti sešitu `kontrola_vysledku/LULAN_kontrola_MZB_vysychave.xlsx`,
což jsou podklady, na kterých se metodika hodnocení vysychavých toků
kalibrovala — 101 lokalit, 458 vzorků, matice 1049 taxonů. Hodnotí se
222 jarních vzorků, u kterých je vyplněné referenční EQR; podzimní sběr
metodika nepoužívá.

Sestavu vyrábí `_tools/porovnani_vysychave.py`, výstup
`porovnani_metrik_vysychave.html`.

### 10.1 Příznak vysychavosti se nečetl

Sloupec `samples.INTERMITTENT` GUI zobrazuje a import ho plní, ale
výpočet ho vůbec nečetl — vysychavost se brala výhradně z
`utvary.VYSYCHAVY`. V databázi bylo 15 vzorků označených jako vysychavé,
ale jen 5 z nich leželo v útvaru vedeném jako vysychavý; zbylých 10 se
počítalo podle metodiky stálých toků.

`registry.vlastnosti_utvaru()` teď dává přednost příznaku u vzorku, a to
jen jedním směrem: `TRUE` povýší na vysychavý, prázdná hodnota ani
`FALSE` zařazení útvaru nepřepíší. Vysychání je vlastnost úseku toku, ne
celého útvaru, takže záznam odběratele je konkrétnější údaj než hrubé
zařazení útvaru; `FALSE` je naopak ve většině záznamů jen nevyplněná
výchozí hodnota, ne uvážené popření.

### 10.2 Tři chyby ve výpočtu metrik

**MI01 a MI02 se počítaly jen z taxonů, které zná taxalist.** Diverzita
i celková abundance jsou přitom vlastnosti vzorku. Každá mezera
v taxalistu tak Margalefův index snižovala a podíl pošvatek naopak
zvyšovala. Po opravě se obojí počítá z celého vzorku:

| | jen známé taxony | celý vzorek |
|---|---|---|
| Margalef | 24/222 přesně | **222/222 přesně** |
| podíl pošvatek | r 0,9959 | **r 1,000000** |

**Trait metriky MI03–MI05 vážily surovou abundanci** místo
logaritmované. Metriky stálých toků přitom používají ln(x+1) už dávno
(`mzb_metrics._vazeny_trait`). Ověřeno proti kalibračním datům: ze šesti
testovaných variant vážení (surová abundance, relativní abundance,
odmocnina, prezence/absence, ln(x), ln(x+1)) vychází ln(x+1) nejlépe
u všech tří metrik současně.

**Trait metriky nevracely procenta.** Valence jsou v taxalistu
rozdělené po deseti bodech mezi jednotlivé kategorie vlastnosti,
výsledek se tedy musí dělit deseti a násobit stem. Bez toho byly
hodnoty zhruba desetinové proti referenci.

K tomu jedna podstatná drobnost ve jmenovateli: do něj patří všechny
taxony, které mají danou **vlastnost** popsanou, ne jen ty, které mají
nenulovou zrovna sledovanou dvojici valencí. Taxon se saprobitou
popsanou, ale s nulou u SZA i SZP, je taxon bez sledované vlastnosti —
do jmenovatele patří a přispívá nulou. Kvůli tomu se načítají celé
skupiny valencí (`VALENCE` v `mzb_intermittent.py`), ne jen šest
sledovaných sloupců; s useknutým jmenovatelem vyskočila MI05 až na
sedminásobek.

### 10.3 Stav po opravě

| metrika | korelace | shodných |
|---|---|---|
| MI01 podíl pošvatek | **1,000000** | 201/222 |
| MI02 Margalefův index | **1,000000** | **222/222** |
| MI03 saprobita SZA+SZP | 0,9867 | 0/222 |
| MI04 teplomilnost WAR+EUT | 0,9475 | 1/222 |
| MI05 reprodukce frc+tec | 0,8542 | 15/222 |
| MZB_CELKEM multimetrika | 0,9754 | — |

Zbylých 21 vzorků u MI01 se liší o setiny procentního bodu (typicky
0,005–0,013), což je pod jakoukoli praktickou mezí.

U MI03–MI05 zůstává rozdíl v řádu jednotek procentních bodů (medián
|Δ| 1,2 / 2,4 / 1,9). Vzorec je ověřený — žádná jiná varianta vážení ani
jmenovatele nedává lepší shodu. Rozdíl tedy nejspíš leží v *hodnotách*
trait tabulky: taxalist LULANu je nemá totožné s tabulkou, se kterou se
metodika kalibrovala. Doložit to bez původní trait tabulky nelze;
`taxalist_mzb_zaloha` tyto sloupce nevede.

### 10.4 Názvy taxonů

63 taxonů z matice (4,53 % abundance) taxalist neznal — nejde
o odlišné taxony, jen o odlišnou konvenci zápisu: vložený podrod
(`Simulium ornatum` → `Simulium (Simulium) ornatum`), jiná úroveň
zařazení (`Tubificidae Gen. sp.` → `Tubificinae Gen. sp.`), přípony
skupin a stadií, pravopisné varianty.

Převod je zapsaný jako výčet v `_tools/nazvy_vysychave.py`, ne jako
automatické párování podle podobnosti — u každé položky je vidět, co se
s čím spojilo. Pokrývá 51 taxonů, tedy 4,45 % abundance; zbylých 12
(0,07 %) v taxalistu není vůbec. Import přepínačem `--nazvy` převod
použije, report ukazuje obě varianty vedle sebe.

Na metriky má převod menší vliv, než by se čekalo: Margalef sedí
222/222 tak i tak, protože se počítá z celého vzorku. Znát nebo neznat
taxon rozhoduje jen u metrik, které potřebují jeho vlastnosti.

### 10.5 Abiotické parametry

Import lokalit záměrně neukládá abiotické parametry ze sešitu, aby šly
nezávisle dopočítat a porovnat:

| parametr | n | korelace | medián \|Δ\| | shodných |
|---|---|---|---|---|
| Strahlerův řád | 98 | **1,000000** | 0,000 | **98/98** |
| vzdálenost od pramene | 98 | 0,9914 | 0,034 km | 42/98 (±10 m) |
| plocha povodí | 98 | 0,9686 | 0,497 km² | 3/98 (±10 m²) |

Strahlerův řád sedí u všech lokalit přesně. Vzdálenost od pramene
a plocha povodí korelují velmi dobře; rozdíly jdou na vrub odlišné
říční sítě (LULAN používá vlastní vrstvu odvozenou ze ZABAGED
a DIBAVOD).

Nadmořskou výšku a podélný sklon nešlo ověřit — vyžadují dotaz na
výškopis ČÚZK. Doplní se spuštěním
`python _tools/porovnani_vysychave.py --online`.

Dvě lokality (`MVN_N_NAD_1`, `MVN_N_POD_1`) se nepodařilo přichytit
k říční síti — v okolí bodu není žádný vodní tok. Podle názvu jde
nejspíš o malé vodní nádrže.

## 11. Fytobentos vysychavých toků — porovnání s kontrolními daty

Kontrola proti `kontrola_vysledku/LULAN_kontrola_FB_vysychave.xlsx`
(85 lokalit, 228 vzorků, matice 681 taxonů). Hodnotí se 120 jarních
vzorků — referenční EQR je vyplněné právě u nich. Sestavu vyrábí
`_tools/porovnani_fb_vysychave.py`, výstup
`porovnani_metrik_FB_vysychave.html`.

### 11.1 Sešit je posunutý, použitelný je jen list `orig`

Listy `data` a `vysledky` nejdou brát tak, jak vypadají. List `vysledky`
jsou dokonce dva bloky slepené vedle sebe:

| sloupce | co to je |
|---|---|
| vzorek, SAL_EQR, O2_EQR, SI_sla_EQR, EQR | 120 řádků = jarní vzorky v pořadí listu `orig` |
| SAL, O2, sap | 228 řádků zarovnaných s řádky listu `orig` |

Řádek listu `vysledky` tedy nedává dohromady jeden vzorek. Kdo by ho tak
četl, dostane nesmysly: korelace mezi metrikou a jejím vlastním EQR
vycházela −0,08 až +0,12. Po správném spárování je to −0,85 (SAL),
−0,94 (O2) a −0,72 (sap).

Skript proto bere hodnoty metrik z `orig` a EQR z levého bloku,
spárované podle pořadí jarních vzorků, a při načtení ověří, že názvy
sedí.

### 11.2 Co je sloupec `sap`

**Není to Sládečkové saprobní index.** Hodnoty v sešitu jsou zlomky se
společným jmenovatelem a celočíselnými čitateli (2,06060… = 68/33),
takže za nimi stojí celočíselná trait hodnota — zatímco MSZS je
desetinné. `sap` má navíc na každém řádku **týž jmenovatel jako SAL
a O2**, takže se počítá přes tutéž množinu taxonů; jde o třetí trait
z téže zdrojové tabulky.

Taxonomický seznam LULANu tento sloupec nemá. FI01 proto počítá
skutečný saprobní index z MSZS a s `sap` se shodovat nemůže — korelace
0,71 je tím, co dvě různé míry saprobity spojuje věcně, ne výpočtem.
Doplnit ho lze jedině přidáním sloupce do `taxalist_FB`.

### 11.3 Dvě chyby ve výpočtu

**Dělilo se celkovou abundancí.** FI02 a FI03 dělily součtem abundancí
všech taxonů vzorku, ne jen těch, které danou trait hodnotu mají. Každý
taxon bez vyplněné hodnoty tak výsledek stahoval k nule a metrika měřila
hlavně úplnost taxalistu. Že je správně druhá varianta, plyne přímo
z kontrolních dat: jmenovatel zlomků odpovídá součtu abundancí taxonů
s vyplněnou hodnotou (33 z 50 u prvního vzorku).

| | před | po |
|---|---|---|
| FI02 ↔ SAL | r 0,489 | **r 0,877** |
| FI03 ↔ O2 | r 0,544 | **r 0,911** |

**Chyběla inverze.** `EQR_TABLE` invertovala jen FI01. U salinity
i nároků na kyslík přitom vyšší hodnota znamená horší stav — plyne to
z povahy věci a kontrolní data to potvrzují jednoznačně (korelace
hodnoty s jejím EQR −0,85 a −0,94). Multimetrika kvůli tomu šla proti
smyslu: proti referenčním EQR vycházela korelace **−0,53**.

### 11.4 Stav po opravě

| metrika | korelace | medián \|Δ\| |
|---|---|---|
| FI01 saprobní index ↔ `sap` | 0,709 | 0,467 |
| FI02 salinita ↔ SAL | 0,877 | 0,089 |
| FI03 kyslík ↔ O2 | 0,911 | 0,128 |
| **FB_CELKEM ↔ EQR** | **0,970** | **0,028** |

Multimetrika se z −0,53 dostala na 0,970. Zbytkový rozdíl u FI02 a FI03
jde na vrub trait hodnot: taxalist LULANu má SAL a O2 vyplněné u jiné
množiny taxonů než zdrojová tabulka (jmenovatele se liší typicky
o 3–5 jedinců), a 24 taxonů z matice (1,84 % abundance) v taxalistu
není vůbec.

Vzorec multimetriky je naproti tomu potvrzený beze zbytku: odmocnina
z prostého průměru dílčích EQR reprodukuje referenční EQR
u **120 ze 120** vzorků přesně.
