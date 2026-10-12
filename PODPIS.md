# Podpis programu a varování systému

Dokument má dvě části: [Windows](#windows) a [macOS](#macos). Linuxový
balíček `.deb` se nepodepisuje.

---

# Windows


## Proč Windows varuje

Nepodepsaný program stažený z internetu dostane od Windows značku
„z nedůvěryhodného zdroje" a při spuštění se objeví modré okno
**SmartScreen**: *„Systém Windows ochránil váš počítač"*. Spustit to
jde — přes odkaz **Další informace → Přesto spustit**.


---

# macOS

## Postup pro spuštění

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
z internetu** — z prohlížeče, z pošty, ze zprávy. 

Je-li značka přítomná, sejměte ji:

```bash
xattr -dr com.apple.quarantine /Applications/LULAN.app
```

Odpoví-li příkaz **`No such xattr: com.apple.quarantine`**, znamená to
prostě, že tam značka není — není to chyba a nic se nepokazilo.

### Když karanténa není, a přesto to nejde spustit

Pak je problém v podpisu. Ověřte ho:

```bash
codesign --verify --deep --strict --verbose=2 /Applications/LULAN.app
```

Když se ohlásí `code object is not signed at all` nebo `invalid
signature`, napište prosím mail vývojáři (marek_polasek@centrum.cz).


---

# Linux

Balíček `.deb` se nepodepisuje. Instalace balíku:

```bash
sudo apt install ./lulan_1.0.1_amd64.deb
```

---

