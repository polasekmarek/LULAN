# Podpis programu a varování systému

Dokument má dvě části: [Windows](#windows) a [macOS](#macos). Linuxový
balíček `.deb` se nepodepisuje — Debian ani Ubuntu na tom netrvají
a žádné varování uživateli neukážou.

---

# Windows

## Nejdřív to podstatné

**Podepsat program za vás nemůžu.** Podpis vyžaduje soukromý klíč
uložený na hardwarovém tokenu a certifikát vydaný na konkrétní
právnickou nebo fyzickou osobu po ověření totožnosti. Ani jedno nejde
udělat kódem — je to smluvní a identifikační věc, ne technická.
Připravit jde všechno ostatní, což je hotové: sestavení, instalátor,
vyplněná identifikace v souboru.

## Proč Windows varuje

Nepodepsaný program stažený z internetu dostane od Windows značku
„z nedůvěryhodného zdroje" a při spuštění se objeví modré okno
**SmartScreen**: *„Systém Windows ochránil váš počítač"*. Spustit to
jde — přes odkaz **Další informace → Přesto spustit** — ale vypadá to
poplašně a část uživatelů to odradí.

Varování se řídí dvěma věcmi: jestli je soubor podepsaný a jakou má
pověst. Pověst se buduje počtem stažení a spuštění bez incidentu.
Nepodepsaný program si ji buduje sám za sebe, podepsaný ji sdílí
s ostatními programy podepsanými týmž certifikátem.

## Možnost 1: nechat to být

Pro nástroj, který si stáhne pár desítek lidí z instituce, je to
obhajitelné. Uživatelům stačí říct, co je čeká, a přidat kontrolní
součet, aby si mohli ověřit, že stáhli právě váš soubor:

```powershell
Get-FileHash LULAN-setup-1.0.1.exe -Algorithm SHA256
```

Součet vypište vedle odkazu ke stažení. Je to slabší ochrana než
podpis, ale lepší než nic a zdarma.

## Možnost 2: koupit certifikát

Certifikát vydá certifikační autorita (DigiCert, Sectigo, SSL.com,
GlobalSign a další) po ověření totožnosti. Pro univerzitu to znamená
doložit existenci organizace — obvykle výpisem z registru a ověřovacím
telefonátem.

**Dva druhy, a rozdíl mezi nimi se v roce 2024 setřel.** Do března 2024
platilo, že EV certifikát ruší varování SmartScreen okamžitě, zatímco
OV si musí pověst teprve vybudovat. Microsoft to změnil: dnes obojí
buduje pověst stejně. Připlácet za EV jen kvůli SmartScreenu tedy nemá
smysl.

| | OV | EV |
|---|---|---|
| cena za rok | zhruba 200–300 USD | zhruba 250–580 USD |
| ověření | organizace | organizace, přísnější |
| SmartScreen | buduje pověst | **stejně, od března 2024** |

Dvě věci, které je potřeba vědět předem:

**Klíč musí být na hardwaru.** Od června 2023 vyžaduje CA/Browser Forum,
aby soukromý klíč ležel na USB tokenu nebo v cloudovém HSM. Nedostanete
tedy soubor s klíčem — dostanete token poštou, nebo přístup ke cloudové
službě. Podepisovat pak jde jen ze stroje, kde je token zapojený.

**Platnost je nově nejvýš rok.** Od února 2026 se certifikáty vydávají
maximálně na dvanáct měsíců, takže je to opakovaný náklad, ne jednorázový.

Vzhledem k tomu, že jde o výstup projektu TAČR, stojí za dotaz, jestli
certifikát nemá univerzita už pořízený centrálně — na ÚVT nebo v týmu,
který spravuje podepisování dokumentů. Bývá to levnější cesta než
kupovat vlastní.

## Jak podepsat, až certifikát budete mít

Potřebujete **Windows SDK** kvůli nástroji `signtool.exe`. Podepisuje se
jak samotný program, tak instalátor — v tomto pořadí, jinak by podpis
instalátoru nepokryl změněný obsah:

```bat
rem 1. program
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
    /a "dist\LULAN\LULAN.exe"

rem 2. sestavit instalátor (build\sestavit.bat, krok 4)

rem 3. instalátor
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
    /a "build\vystup\LULAN-setup-1.0.1.exe"
```

`/tr` přidává **časové razítko** a vynechat se nesmí. Bez něj přestanou
být podpisy platné ve chvíli, kdy certifikátu vyprší platnost — tedy do
roka. S razítkem zůstávají platné i potom, protože je doložené, že
podpis vznikl v době, kdy certifikát platil.

Ověření, že se podpis povedl:

```bat
signtool verify /pa /v "build\vystup\LULAN-setup-1.0.1.exe"
```

## Co pověsti pomůže i bez certifikátu

Něco z toho je už hotové, zbytek je na vás.

**Vyplněná identifikace v souboru.** `build/verze.txt` doplňuje do
`LULAN.exe` název, verzi, autora a copyright. Soubor bez těchto údajů
vypadá podezřeleji než ten s nimi. *(hotovo)*

**Bez komprese UPX.** Balení spustitelných souborů UPX je oblíbené
u malwaru, takže na něj antiviry reagují. Spec ji vypíná. *(hotovo)*

**Adresářová podoba místo jednoho souboru.** Volba `--onefile` se při
každém spuštění rozbaluje do dočasného adresáře, což je chování, které
antiviry hlásí. *(hotovo)*

**Stabilní místo ke stažení.** Stejná adresa a doména dlouhodobě pomáhá
pověsti víc než přesouvání souboru sem a tam.

**Hlášení planého poplachu.** Když nějaký antivirus program označí
neprávem, dá se to nahlásit — Microsoft na
<https://www.microsoft.com/wdsi/filesubmission>, ostatní výrobci mají
obdobné formuláře. Bývá to vyřízené během několika dnů.

---

# macOS

## Nejdřív to podstatné

Na macOS hlídá spouštění **Gatekeeper**. Rozlišuje tři stupně, a je
důležité je nesplést dohromady:

| stupeň | co to znamená | co udělá macOS |
|---|---|---|
| **notarizovaná** | podepsaná certifikátem *Developer ID* a ověřená u Applu | spustí bez ptaní |
| **podepsaná, nenotarizovaná** | má podpis, ale Apple ji neviděl | zablokuje, jde povolit v Nastavení |
| **nepodepsaná** | žádný podpis | zablokuje a **v Nastavení se ani nenabídne** |

Ten třetí řádek je důvod, proč `build/sestavit_mac.sh` aplikaci
podepisuje takzvaně **ad-hoc** (`codesign --sign -`). Ad-hoc podpis
nevyžaduje žádný certifikát ani účet, nikomu nic nedokazuje — ale
posune aplikaci ze třetího řádku do druhého. Uživatel tak dostane
tlačítko *Přesto otevřít* místo hluché zdi.

Na Apple Silicon je to navíc nutnost: tamní systém odmítne spustit
binární soubor bez jakéhokoli podpisu úplně.

## Co uvidí uživatel a co má udělat

Při prvním spuštění se objeví okno, že aplikace *„nemůže být otevřena,
protože nelze ověřit vývojáře"*. Postup:

1. V dialogu kliknout na **Hotovo**.
2. Otevřít **Nastavení systému → Soukromí a zabezpečení**.
3. Sjet dolů k části **Zabezpečení**, kde bude řádek o zablokovaném
   LULANu, a kliknout na **Přesto otevřít**.
4. Potvrdit heslem nebo Touch ID.

Stačí jednou; podruhé se aplikace spustí rovnou.

### Když se v Nastavení nic neobjeví

Nejdřív zjistěte, jestli je aplikace vůbec v karanténě:

```bash
xattr -l /Applications/LULAN.app
```

**Značku `com.apple.quarantine` dostávají jen soubory stažené
z internetu** — z prohlížeče, z pošty, ze zprávy. Aplikace, kterou jste
sestavil sám na svém Macu, ji nikdy neměla. Pak ve výpisu nebude a není
co řešit; blokuje ji něco jiného (viz níž).

Je-li značka přítomná, sejměte ji:

```bash
xattr -dr com.apple.quarantine /Applications/LULAN.app
```

Přepínač `-r` je podstatný: aplikace je ve skutečnosti adresář se
stovkami souborů a značku může nést kterýkoli z nich, ne jen obal.
Bez něj se sejme jen z obalu a systém aplikaci blokuje dál.

Odpoví-li příkaz **`No such xattr: com.apple.quarantine`**, znamená to
prostě, že tam značka není — není to chyba a nic se nepokazilo.

### Když karanténa není, a přesto to nejde spustit

Pak je problém v podpisu. Ověřte ho:

```bash
codesign --verify --deep --strict --verbose=2 /Applications/LULAN.app
```

Když se ohlásí `code object is not signed at all` nebo `invalid
signature`, podepište aplikaci znovu ad-hoc:

```bash
codesign --force --deep --sign - /Applications/LULAN.app
```

Tohle je přesně ten případ, kvůli kterému `build/sestavit_mac.sh`
podepisuje už při sestavení — úplně nepodepsaná aplikace se
v Nastavení v části Zabezpečení vůbec nenabídne a tlačítko *Přesto
otevřít* neexistuje.

## Možnost 1: nechat to být

Pro nástroj, který si nainstaluje pár desítek lidí z instituce, je to
obhajitelné — stejně jako u Windows. Uživatelům stačí předem říct, co je
čeká, a přiložit kontrolní součet:

```bash
shasum -a 256 LULAN-1.0.1.dmg
```

## Možnost 2: Developer ID a notarizace

Apple Developer Program stojí **99 USD ročně** (organizace i jednotlivci;
Enterprise varianta za 299 USD je pro interní firemní aplikace a na
veřejnou distribuci se nevztahuje). Členství není jednorázové — když
vyprší, dříve notarizované aplikace sice běží dál, ale nové už
notarizovat nelze.

Členství zahrnuje certifikát **Developer ID Application**, kterým se
podepisují aplikace šířené mimo App Store. Notarizace samotná se
neplatí zvlášť.

Až certifikát budete mít, sestavení se přepne proměnnou:

```bash
export LULAN_PODPIS="Developer ID Application: Masarykova univerzita (TEAMID)"
build/sestavit_mac.sh
```

Notarizace je pak ještě jeden krok — DMG se pošle Applu ke kontrole
a výsledek se k němu „přišije":

```bash
# jednorázově: uložit přihlašovací údaje do klíčenky
xcrun notarytool store-credentials "LULAN" \
    --apple-id "vas@email.cz" --team-id "TEAMID" \
    --password "heslo-pro-aplikaci"

# při každém vydání
xcrun notarytool submit build/vystup/LULAN-1.0.1.dmg \
    --keychain-profile "LULAN" --wait
xcrun stapler staple build/vystup/LULAN-1.0.1.dmg
```

Heslo pro aplikaci (app-specific password) se vytváří na
<https://appleid.apple.com>, ne to běžné k Apple ID. Kontrola obvykle
trvá jednotky minut.

Notarizace vyžaduje podpis s `--options runtime` (hardened runtime),
což skript už nastavuje. U aplikací zabalených PyInstallerem může Apple
odmítnout některé knihovny; hlášení z `notarytool log` pak řekne
kterou.

---

# Linux

Balíček `.deb` se nepodepisuje. Debian i Ubuntu podpisy u jednotlivých
balíčků neřeší — ověřují se celé repozitáře, a LULAN se žádným nešíří.
Uživatel balíček nainstaluje bez jediného varování:

```bash
sudo apt install ./lulan_1.0.1_amd64.deb
```

Kontrolní součet se hodí i tady:

```bash
sha256sum lulan_1.0.1_amd64.deb
```

---

Údaje o cenách a pravidlech platí k září 2026. Podmínky certifikačních
autorit i Applu se mění, před nákupem si je ověřte.

Zdroje: [Microsoft Learn – Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options),
[Microsoft Learn – SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation),
[SSL.com – EV vs OV](https://www.ssl.com/faqs/which-code-signing-certificate-do-i-need-ev-ov/),
[Apple Developer Program – Membership details](https://developer.apple.com/programs/whats-included/),
[Apple Support – Safely open apps on your Mac](https://support.apple.com/en-us/102445)
