# Revize kódu — nálezy a doporučení

Datum: 23. 8. 2026

Stav výpočetní části je hotový a ověřený (viz `OPRAVY.md`). Tento dokument
shrnuje, co jsem našel při průchodu celým zdrojovým kódem — co už je
opravené a co doporučuji řešit dál.

---

## 1. Opraveno v rámci revize

### 1.1 `save_samples_changes()` mohla poškodit data — ZÁVAŽNÉ

Metoda v `main_app_deploy.py` byla nefunkční hned v pěti ohledech:

| problém | důsledek |
|---|---|
| otevírala si vlastní spojení na natvrdo zapsanou cestu `"dtb/LULAN_dtb_001.db"` | obcházela pracovní kopii databáze i volbu jiného souboru; při jiném pracovním adresáři si vyrobila prázdnou databázi |
| všechny hodnoty převáděla na `float()` | `SAMPLE_ID`, `LOC_ID`, `TYP` i `DATE` by se zapsaly jako `NULL` |
| `WHERE KOD = ?` | tabulka `samples` sloupec `KOD` nemá (má `ID`, `SAMPLE_ID`, `TYP`, `INTERMITTENT`, `DATE`, `LOC_ID`, `DTCH`) |
| volala `self.save_samples_changes_button` | widget se nikde nevytváří → `AttributeError` |
| četla `self.samples_detail_model` | ten je od `load_sample_details()` nahrazený jiným modelem (`QSqlQueryModel` se seznamem taxonů) |

Metoda se volá při přepnutí vzorku, pokud uživatel odpoví „Ano" na dotaz
o neuložených změnách. Prakticky vždy spadla na `AttributeError` dřív, než
došlo k zápisu — což data paradoxně zachránilo.

Nahrazeno bezpečnou verzí, která uživateli řekne, že editace záznamů vzorku
zatím není hotová. **Tohle je přesně ta funkcionalita, kterou chceš doplnit
(editace po jednotlivých záznamech)** — až se k ní dostaneme, nahradí se
tenhle zástupný kód pořádnou implementací.

### 1.2 `src/adjustace.py` — mrtvý kód s obrácenou logikou

382 řádků, které nikdo neimportoval. Duplikovaly funkcionalitu dnes
v `common.aplikuj_adjustace()`, ale se starým (chybným) výkladem stavu `D`
jako „ponechat". Kdyby se do nich někdo napojil, vrátil by tím zpět největší
opravenou chybu. Přesunuto do `_archiv/src/`.

### 1.3 `_tools/vykon.py` spoléhal na neexistující dočasný soubor

Skript četl `/tmp/abio.db`, který zbyl po dávno skončeném běhu — po restartu
padal na `no such table: samples`. Přepsán tak, aby si pracovní kopii
databáze připravil sám, a aby srovnání s původní verzí přeskočil, když
`_archiv/src_orig` není k dispozici.

### 1.4 Křehký klíč cache u `mapa_synonym()`

Cache se klíčovala přes `id(taxalist)`. Adresa objektu se po uvolnění paměti
může znovu použít pro jiný seznam, což by vrátilo cizí mapování. Mapa se teď
drží přímo v načteném seznamu, takže zaniká spolu s ním.

### 1.5 Holé `except:`

Sedm výskytů (`B_index2.py`, `main_app_deploy.py`) zachytávalo i
`KeyboardInterrupt` a `SystemExit` a zakrývalo překlepy v kódu. Zúženy na
konkrétní výjimky.

### 1.6 Nepoužité importy a proměnné

Vyčištěno v `main_app_deploy.py` (`sqlite3`, `QThread`, `pyqtSignal`,
`QSizePolicy`, `QSpacerItem`, `QTableWidgetItem`, dvojitý `QHBoxLayout`,
lokální reimport `QColor`), `fb_perennial.py`, `mzb_metrics.py`
a v nástrojích.

---

## 2. Doporučuji řešit dál (neopraveno)

### 2.1 `main_app_deploy.py` má 2 878 řádků v jediné třídě

Osm metod přesahuje 100 řádků (`import_samples_from_csv` 227,
`initTab4` 190, `initTab1` 166, `initTab0` 160). Tři metody pro import CSV
(`import_locations_from_csv`, `import_samples_from_csv`,
`import_utvary_from_csv`) dělají v podstatě totéž — načíst CSV, ověřit
hlavičku, namapovat sloupce, vložit řádky.

**Návrh:** vytáhnout GUI do balíčku `src/gui/` (záložka = modul) a import
CSV sjednotit do jednoho parametrizovaného modulu `src/import_csv.py`
s popisem tabulek (povinné sloupce, převody, validace). Tím se zároveň
připraví půda pro to, co chceš doplnit.

### 2.2 Poziční vazba detailu lokality na sloupce databáze

`save_location_changes()` bere hodnoty z modelu podle pořadí řádků
a napevno je váže na `WGS84_LAT, WGS84_LON, STRAHLER, MNM, PLOCHA_POV,
KM_OD_PRAM, SLOPE, UMORI`. Pořadí musí přesně odpovídat seznamu `labels`
v `load_location_details()`, který je definovaný o 70 řádků výš. Přidání
jednoho pole na špatné místo tiše přepíše jiný sloupec.

**Návrh:** jeden společný seznam dvojic `(sloupec, popisek)` a vázat podle
názvu sloupce, ne podle pořadí.

### 2.3 Editace detailu převádí vše na `float`

`save_location_changes()` převádí každou hodnotu na `float` a při neúspěchu
zapíše `NULL`. U lokality jsou všechny editované sloupce číselné, takže to
zatím projde, ale je to past pro každý budoucí textový sloupec.

### 2.4 Skládání SQL z proměnných

`f"SELECT * FROM {current_table}"`, `f"PRAGMA table_info({current_table})"`,
`f"INSERT INTO utvary ({columns_str})"`. Názvy tabulek a sloupců pocházejí
z vlastního kódu, ne od uživatele, takže o injekci nejde — ale u importu
útvarů se `columns_str` skládá z hlavičky CSV. Doporučuji hlavičku
proti seznamu povolených sloupců ověřovat, ne jen předpokládat.

### 2.5 `load_sample_details()` vkládá `sample_id` přímo do SQL

`WHERE data.sample = '{sample_id}'`. Hodnota jde z databáze, takže reálné
riziko je malé, ale správně tam patří vázaný parametr. Navíc jsou v metodě
čtyři větve (`MZB`, `FB`, `RYBY`, `MF`) s naprosto stejným dotazem —
zůstaly po odstranění `INNER JOIN` na taxalisty.

### 2.6 Nedokončené funkce

* `export_samples_placeholder()` a `export_results_placeholder()` —
  jen zástupné metody
* `mzb_perennial_nebroditelne.py` — záchytný bod pro nebroditelné toky
  mimo seznam velkých řek
* `neimplementovane.py` — jezerní metodiky (FP, MF, ryby)
* `optional_fields` v importu vzorků se naplní, ale nikde nepoužije

### 2.7 GIS vrstvy jsou v repozitáři

`src/GIS/U_TOKJ$STRAHLER.dbf` má 81 MB, celá složka přes 180 MB. Do
distribuce aplikace to nepatří — vrstvy by měly být volitelná externí data
se stahováním nebo konfigurovatelnou cestou. Dolar v názvu souboru navíc
dělá potíže v shellu a v některých instalátorech.

### 2.8 Kódování v archivované původní verzi

Výstupy z `_archiv/src_orig` jsou rozsypané mojibake (několikanásobné
překódování cp1252). Nové moduly tím netrpí, ale při případném srovnávání
s archivem to bude vadit.

---

## 3. Stav ověření

| kontrola | výsledek |
|---|---|
| dávkový výpočet 1 046 vzorků | 20 s, **žádná výjimka**, 10 626 záznamů výsledků |
| testy ryb (`_tools/test_ryby.py`) | **63/63** |
| testy fytoplanktonu (`_tools/test_fp.py`) | **0 chyb** |
| porovnání s ARROW, MB07 index B | **406/406**, r = 1,00000 |
| porovnání s ARROW, MB11 a MB13 | **406/406**, r = 1,00000 |
| MB_CELKEM, shodná třída | **388/396 = 98,0 %** |
| `pyflakes` na `src/` | 3 zbytkové kosmetické nálezy |
| překlad všech modulů | OK |

Výchozí nastavení počítá **výhradně s mezemi z metodiky**
(`MEZE_DLE_ARROW = False`). Přepínač `--meze-arrow` je ponechaný jako důkaz
správnosti implementace — po jeho zapnutí sedne i RETI (76 %) a Margalef
(96 %), viz `OPRAVY.md`, kap. 1.14.
