# Co je pro běh potřeba a co ne

Přehled vznikl při přípravě instalátoru pro Windows. Dělí soubory na
tři skupiny: co aplikace potřebuje za běhu, co je vývojová obsluha
(patří do repozitáře, ne do instalace) a co jde smazat.

## 1. Chybí — bez toho aplikace nefunguje naplno

Při úklidu zmizely soubory, na které se kód odkazuje. Aplikace kvůli
nim nespadne (mapa se ošetřuje tiše), ale funkce vypadnou.

| soubor | co se stane bez něj | odkud vzít |
|---|---|---|
| `src/GIS/hrcr_S42.{shp,shx,dbf,prj}` | mapka na Lokalitách zůstane prázdná s hláškou | **jen ze zálohy** |
| `src/GIS/hlavni_toky_S42.*` | mapka bez řek | obnoveno |
| `img/filtr_ikona.png`, `@2x` | filtr bez trychtýře | obnoveno |

Vrstvu hlavních toků i ikony filtru jsem vyrobil znovu (`filter_icon.svg`
a `_tools/vyber_hlavni_toky.py` zůstaly). **Hranice ČR ale obnovit
neumím** — původní `hrcr_S42.shp` v repozitáři nikdy nebyl, jen na
disku. Zkopírujte ho prosím ze zálohy zpátky do `src/GIS/`.

## 2. Potřeba za běhu — musí do instalace

```
src/*.py                     kód aplikace
src/calc_index/*.py          výpočetní moduly
src/GIS/hrcr_S42.*           hranice ČR pro mapku
src/GIS/hlavni_toky_S42.*    řeky pro mapku
dtb/LULAN_dtb_001.db   24 MB hlavní databáze
dtb/ricni_sit.db       64 MB odvozená říční síť (abiotické parametry)
dtb/ciselnik_traits.csv      překlad zkratek vlastností
dtb/hodnoceni_zkratky.csv    překlad zkratek metrik
img/LULAN_icon.ico           ikona aplikace (Windows)
img/LULAN_icon.icns          ikona aplikace (macOS)
img/LULAN_icon.png           ikona aplikace (Linux) a záloha jinde
img/filtr_ikona.png, @2x     ikona v polích filtru
LICENSE                      text licence
```

`img/LULAN_logo.jpg` je jen zdroj ikony, do instalace ho netřeba —
`ikona_aplikace()` ho zkouší až jako třetí možnost.

Ikonu pro macOS vyrábí `_tools/vyrob_icns.py` z `LULAN_icon.png`;
`build/sestavit_mac.sh` ji obnoví sám, kdykoli je zdrojový obrázek
novější. Do repozitáře patří, aby sestavení nevyžadovalo Pillow.

## 3. Vývojová obsluha — do repozitáře ano, do instalace ne

```
_tools/                      generátory, kontroly, srovnávací skripty
build/                       předpisy pro sestavení instalátorů
*.md                         dokumentace
img/LULAN_logo.jpg           zdroj ikony
img/filter_icon.svg          zdroj ikony filtru
requirements.txt
VERZE
```

Tyhle složky se do repozitáře **nedávají** a jsou v `.gitignore`, i když
pro vývoj jsou potřeba:

```
metodiky/                    PDF metodik — autorská díla třetích stran
kontrola_vysledku/           kontrolní sešity s provozními daty
```

Bez nich nejdou spustit srovnávací skripty v `_tools/`. Držte je mimo
repozitář a při práci je nakopírujte zpět.

## 4. Co se nepřidává do gitu

Všechno, co vzniká při běhu, je v `.gitignore`:

| vzor | odkud se bere |
|---|---|
| `__pycache__/`, `*.pyc` | překlad Pythonu |
| `.venv/` | virtuální prostředí, staví se z `requirements.txt` |
| `dist/`, `build/prace/`, `build/vystup/` | sestavení instalátorů |
| `build/verze_generovano.txt` | popis verze, skládá se ze souboru `VERZE` |
| `porovnani_metrik_*.html`, `*.csv` | výstupy srovnávacích skriptů |
| `_tools/eqr_*.json`, `regrese.json` | mezivýsledky převodu EQR tabulek |
| `*.db-journal`, `*.db-wal`, `*.db.zaloha_*` | pracovní soubory SQLite a zálohy |
| `.DS_Store` | soubory Finderu |

Zálohu databáze držte **mimo pracovní adresář**. Soubory
`LULAN_dtb_001.db.zaloha_*` sice `.gitignore` zachytí, ale v pracovní
složce stejně nemají co dělat — při jedné z nich se omylem přepsal
zdrojový soubor.

## 5. Velikost repozitáře

`dtb/ricni_sit.db` má **64 MB**. GitHub od 50 MB varuje a nad 100 MB
soubor odmítne — projde tedy, ale repozitář tím znatelně nabobtná
a každé klonování ho stáhne znovu.

Stojí za zvážení přesunout ho do Git LFS, nebo ho k vydáním přikládat
jako samostatný soubor a nechat `_tools/gen_ricni_sit.py`, ať si ho
každý vyrobí sám z GIS podkladů.

Pozor na `dtb/ciselnik_traits.csv` a `dtb/hodnoceni_zkratky.csv` —
vypadají jako pomocné soubory, ale aplikace je čte za běhu (kapitola 2).
