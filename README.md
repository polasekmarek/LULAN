# LULAN

**Limnologický Univerzální Laboratorně Analytický Nástroj**

Desktopová aplikace pro hodnocení ekologického stavu a potenciálu útvarů
povrchových vod ČR podle Rámcové směrnice o vodách (2000/60/ES).
Python 3 + PyQt6 + SQLite.

Hodnotí všechny biologické složky — makrozoobentos, fytobentos,
fytoplankton, makrofyta a ryby — pro tekoucí i stojaté vody, včetně
vysychavých toků, velkých nebroditelných řek a silně ovlivněných útvarů.

*Vzniklo za finanční podpory Technologické agentury ČR v rámci programu
Prostředí pro život, projekt SS06010258.*

---

## Dokumentace

| Soubor | Obsah |
|---|---|
| [DOKUMENTACE.md](DOKUMENTACE.md) | **uživatelská příručka a technická dokumentace** — začněte tady |
| [PODPIS.md](PODPIS.md) | podpis programu a varování systémů při instalaci |


## Spuštění ze zdrojových kódů

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/main_app_deploy.py
```

Databáze se při prvním spuštění použije z `dtb/LULAN_dtb_001.db`.
U nainstalované verze si ji program zkopíruje do uživatelských dat —
podrobnosti v [DOKUMENTACE.md](DOKUMENTACE.md), kapitola 2.2.4.

## Sestavení instalačních balíčků

PyInstaller neumí sestavit pro jinou platformu, než na které běží —
každý balíček proto vzniká na svém systému. Předpis `build/lulan.spec`
je společný.

```
Windows   build\sestavit.bat        → instalátor .exe (Inno Setup)
macOS     build/sestavit_mac.sh     → LULAN.app + obraz .dmg
Linux     build/sestavit_linux.sh   → balíček .deb (Debian, Ubuntu)
```

Číslo verze má jediné místo — soubor [`VERZE`](VERZE). Čte ho aplikace,
předpis PyInstalleru, instalátor i oba skripty pro macOS a Linux.

## Struktura

```
src/
  main_app_deploy.py        hlavní okno, pět záložek, menu
  calc_indexes.py           veřejné rozhraní výpočtu (tenká fasáda)
  calc_index/               výpočetní jádro — modul na kombinaci
  abiotic_params.py         dopočet abiotických parametrů lokalit
  ricni_sit.py              práce s odvozenou říční sítí
  B_index2.py               predikční model B-indexu
  import_csv.py             import dat včetně popisu tabulek
  export_csv.py             export dat a výsledků
  uloziste.py               detekce síťového / synchronizovaného úložiště
  cesty.py                  umístění dat (zdrojáky vs. zabalená aplikace)
  GIS/                      shapefily pro mapový náhled

dtb/                        databáze a číselníky
img/                        ikony aplikace
build/                      předpisy pro sestavení instalátorů
_tools/                     vývojové nástroje, generátory, kontroly
```

### Výpočetní jádro

Výběr metodiky je vedený jako tabulka v `calc_index/registry.py` —
klíčem je pětice (složka, kategorie útvaru, HMWB, vysychavost,
broditelnost), hodnotou hodnoticí funkce. Kombinací je přes dvacet,
takže vnořené podmínky by se staly nepřehlednými.

Balík nezná grafické prvky a dostává jen spojení do databáze a kód
vzorku, takže jde spustit i z příkazové řádky. Toho využívají srovnávací
nástroje v `_tools/`.

Přehled „složka × typ útvaru → modul × metodika" je
v [DOKUMENTACE.md](DOKUMENTACE.md), kapitola 3.2.2.

## Licence

Zdrojový kód je pod licencí [MIT](LICENSE).

**Data, se kterými aplikace pracuje, pod MIT nejsou.** Odvozená říční síť
(`dtb/ricni_sit.db`) a GIS vrstvy v `src/GIS/` jsou odvozená díla
z DIBAVOD, ZABAGED a rozvodnic ČHMÚ a řídí se licencemi svých správců.
Metodiky hodnocení, taxonomické seznamy a autekologické charakteristiky
jsou autorskými díly třetích stran. Přehled je
v [DOKUMENTACE.md](DOKUMENTACE.md), kapitola 4.2.
