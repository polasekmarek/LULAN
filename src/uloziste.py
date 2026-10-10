"""
Detekce typu uloziste, na kterem lezi databaze.

SQLite si neporadi se zamykanim souboru na sitovych discich a na slozkach
synchronizovanych cloudovymi klienty. Projevuje se to chybami

    disk I/O error
    database is locked
    database disk image is malformed

a v adresari zustava rozpracovany soubor `-journal`. Riziko je o to vetsi,
ze synchronizacni klient muze soubor prepsat uprostred transakce, nebo
vytvorit konfliktni kopii.

Modul detekuje tri urovne rizika:

    'sitove'  - sitovy disk (SMB, NFS, mapovana jednotka, cesta UNC)
    'cloud'   - slozka synchronizovana cloudovym klientem
    'lokalni' - bezne lokalni uloziste

Detekce je zamerne konzervativni: pri pochybnostech oznaci uloziste jako
rizikove. Nepouziva zadne knihovny mimo standardni instalaci Pythonu.
"""

from __future__ import annotations

import os
import platform
import sys

#: Nazvy adresaru, ktere typicky patri synchronizacnim klientum.
#: Porovnava se bez ohledu na velikost pismen proti jednotlivym castem cesty.
CLOUDOVE_ADRESARE = {
    "owncloud": "ownCloud",
    "nextcloud": "Nextcloud",
    "onedrive": "OneDrive",
    "dropbox": "Dropbox",
    "google drive": "Google Drive",
    "googledrive": "Google Drive",
    "my drive": "Google Drive",
    "icloud drive": "iCloud Drive",
    "com~apple~clouddocs": "iCloud Drive",
    "mobile documents": "iCloud Drive",
    "pcloud": "pCloud",
    "seafile": "Seafile",
    "megasync": "MEGA",
    "yandex.disk": "Yandex.Disk",
    "box sync": "Box",
    "cloudstorage": "cloudový klient",
}

#: Predpony nazvu adresaru, ktere klienti pouzivaji s doplnkem
#: (napr. "OneDrive - Nazev firmy", "OneDrive-Personal").
CLOUDOVE_PREDPONY = ("onedrive", "owncloud", "nextcloud", "dropbox", "pcloud")

#: Nazvy, ktere jsou samy o sobe prilis obecne na to, aby rozhodly -
#: pouziji se jen tehdy, kdyz se v ceste nenajde nic konkretnejsiho.
OBECNE_NAZVY = {"cloudový klient"}

#: Souborove systemy povazovane za sitove.
SITOVE_FS = {
    "nfs", "nfs4", "cifs", "smbfs", "smb", "afpfs", "webdav", "ftp",
    "fuse.sshfs", "fuse.davfs", "fuse.rclone", "fuse.gvfsd-fuse",
    "9p", "ncpfs", "afs", "coda",
}

#: Souborove systemy typu FUSE, u kterych nelze zarucit zamykani.
FUSE_FS_PREFIX = "fuse"

#: Kody z GetDriveTypeW ve Windows.
_DRIVE_REMOTE = 4
_DRIVE_CDROM = 5


class Uloziste:
    """Vysledek detekce."""

    def __init__(self, cesta, druh, popis, detail=""):
        self.cesta = cesta
        self.druh = druh          # 'lokalni' | 'sitove' | 'cloud'
        self.popis = popis        # kratky nazev pro uzivatele
        self.detail = detail      # doplnujici informace (fs, pismeno disku)

    @property
    def rizikove(self):
        """True, pokud na tomto ulozisti hrozi chyby SQLite."""
        return self.druh in ("sitove", "cloud")

    def __repr__(self):
        return f"Uloziste({self.druh!r}, {self.popis!r}, {self.detail!r})"


# ---------------------------------------------------------------------------
# Detekce podle nazvu cesty (spolecne pro vsechny platformy)
# ---------------------------------------------------------------------------

def _rozdel_cestu(cesta):
    """Rozdeli cestu na casti bez ohledu na to, jaky oddelovac pouziva.

    Diky tomu se detekce chova stejne i nad cestami z jineho systemu
    (napr. pri kontrole ulozene konfigurace).
    """
    return [c for c in cesta.replace("\\", "/").split("/") if c]


def _cloudovy_klient(cesta):
    """Vrati nazev cloudoveho klienta, pokud cesta vede do jeho slozky.

    Casti cesty prochazi od nejhlubsi, aby konkretnejsi nazev prebil
    obecnejsi - napr. u cesty
    ~/Library/CloudStorage/OneDrive-Personal/... ma prednost OneDrive.
    """
    obecny = None

    for cast in reversed(_rozdel_cestu(cesta)):
        klic = cast.lower()
        nalez = CLOUDOVE_ADRESARE.get(klic)
        if nalez is None:
            for predpona in CLOUDOVE_PREDPONY:
                if klic.startswith(predpona):
                    nalez = CLOUDOVE_ADRESARE[predpona]
                    break
        if nalez is None:
            continue
        if nalez in OBECNE_NAZVY:
            obecny = obecny or nalez
            continue
        return nalez

    return obecny


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _detekce_windows(cesta):
    plna = os.path.abspath(cesta)

    # cesta UNC: \\server\share\...
    if plna.startswith("\\\\"):
        server = plna.lstrip("\\").split("\\")[0]
        return Uloziste(cesta, "sitove", "síťová cesta UNC", f"\\\\{server}")

    try:
        import ctypes

        koren = os.path.splitdrive(plna)[0] + os.sep
        typ = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(koren))
        if typ == _DRIVE_REMOTE:
            return Uloziste(
                cesta, "sitove", "mapovaná síťová jednotka", koren.rstrip(os.sep)
            )
        if typ == _DRIVE_CDROM:
            return Uloziste(cesta, "sitove", "jednotka jen pro čtení", koren)
    except Exception:  # noqa: BLE001 - detekce nesmi shodit aplikaci
        pass

    return None


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _detekce_macos(cesta):
    plna = os.path.abspath(cesta)

    try:
        import subprocess

        vysledek = subprocess.run(
            ["/sbin/mount"], capture_output=True, text=True, timeout=5
        )
        # radky maji tvar: //user@server/share on /Volumes/share (smbfs, ...)
        nejdelsi = None
        for radek in vysledek.stdout.splitlines():
            if " on " not in radek or "(" not in radek:
                continue
            zdroj, zbytek = radek.split(" on ", 1)
            pripojeno = zbytek.rsplit(" (", 1)[0]
            typ = zbytek.rsplit("(", 1)[1].rstrip(")").split(",")[0].strip()
            if plna == pripojeno or plna.startswith(pripojeno.rstrip("/") + "/"):
                if nejdelsi is None or len(pripojeno) > len(nejdelsi[0]):
                    nejdelsi = (pripojeno, typ, zdroj)

        if nejdelsi:
            _, typ, zdroj = nejdelsi
            if typ.lower() in SITOVE_FS:
                return Uloziste(cesta, "sitove", f"síťový disk ({typ})", zdroj)
    except Exception:  # noqa: BLE001
        pass

    return None


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def _detekce_linux(cesta):
    plna = os.path.abspath(cesta)

    try:
        with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
            radky = f.read().splitlines()
    except OSError:
        return None

    nejdelsi = None
    for radek in radky:
        casti = radek.split()
        if len(casti) < 3:
            continue
        zdroj, bod, typ = casti[0], casti[1].replace("\\040", " "), casti[2]
        if plna == bod or plna.startswith(bod.rstrip("/") + "/"):
            if nejdelsi is None or len(bod) > len(nejdelsi[0]):
                nejdelsi = (bod, typ, zdroj)

    if nejdelsi is None:
        return None

    _, typ, zdroj = nejdelsi
    if typ.lower() in SITOVE_FS:
        return Uloziste(cesta, "sitove", f"síťový disk ({typ})", zdroj)
    if typ.lower().startswith(FUSE_FS_PREFIX):
        return Uloziste(
            cesta, "sitove", f"připojený svazek typu FUSE ({typ})", zdroj
        )
    return None


# ---------------------------------------------------------------------------
# Verejne rozhrani
# ---------------------------------------------------------------------------

def zjisti(cesta):
    """Zjisti, na jakem ulozisti lezi zadana cesta.

    Args:
        cesta: cesta k souboru nebo adresari (nemusi existovat)

    Returns:
        Uloziste
    """
    if not cesta:
        return Uloziste(cesta, "lokalni", "neurčeno")

    # adresar souboru staci - soubor jeste nemusi existovat
    sledovana = cesta if os.path.isdir(cesta) else os.path.dirname(
        os.path.abspath(cesta)
    ) or os.path.abspath(cesta)

    system = platform.system()
    detektor = {
        "Windows": _detekce_windows,
        "Darwin": _detekce_macos,
        "Linux": _detekce_linux,
    }.get(system)

    if detektor is not None:
        try:
            vysledek = detektor(sledovana)
        except Exception:  # noqa: BLE001
            vysledek = None
        if vysledek is not None:
            return vysledek

    klient = _cloudovy_klient(sledovana)
    if klient:
        return Uloziste(cesta, "cloud", f"složka synchronizovaná do {klient}", klient)

    return Uloziste(cesta, "lokalni", "lokální disk")


def doporucene_umisteni(nazev_souboru="LULAN_dtb_001.db"):
    """Vrati doporucenou lokalni cestu pro pracovni kopii databaze.

    Pouziva standardni adresar pro data aplikaci dane platformy.
    """
    system = platform.system()
    if system == "Windows":
        zaklad = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        adresar = os.path.join(zaklad, "LULAN")
    elif system == "Darwin":
        adresar = os.path.expanduser("~/Library/Application Support/LULAN")
    else:
        zaklad = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
            "~/.local/share"
        )
        adresar = os.path.join(zaklad, "LULAN")
    return os.path.join(adresar, nazev_souboru)


def text_varovani(uloziste):
    """Sestavi text varovani pro uzivatele."""
    kde = {
        "sitove": "na síťovém disku",
        "cloud": "ve složce synchronizované do cloudu",
    }.get(uloziste.druh, "")

    detail = f" ({uloziste.detail})" if uloziste.detail else ""

    return (
        f"Databáze je uložená {kde} — {uloziste.popis}{detail}.\n\n"
        "SQLite si na takovém úložišti neporadí se zamykáním souborů. "
        "Může to vést k chybám „disk I/O error“ nebo „database is locked“, "
        "v horším případě k poškození databáze — zvlášť když synchronizační "
        "klient přepíše soubor uprostřed zápisu, nebo když se stejný soubor "
        "otevře na dvou počítačích.\n\n"
        "Doporučení: mít databázi na místním disku a na síťové úložiště "
        "ukládat jen zálohy."
    )


# ---------------------------------------------------------------------------
# Prace z lokalni pracovni kopie
# ---------------------------------------------------------------------------

class PracovniKopie:
    """Drzi databazi na lokalnim disku a na konci ji vrati na puvodni misto.

    Pouziva se, kdyz databaze lezi na sitovem nebo synchronizovanem ulozisti.
    Aplikace pak cely beh pracuje s lokalnim souborem, kde SQLite funguje
    spolehlive, a pri ukonceni se soubor zkopiruje zpatky.

    Pouziti:
        kopie = PracovniKopie(cesta_k_db)
        kopie.priprav()
        ...                       # aplikace pracuje s kopie.pracovni_cesta
        kopie.uloz_zpet()
    """

    def __init__(self, puvodni_cesta, cilova_cesta=None):
        self.puvodni_cesta = os.path.abspath(puvodni_cesta)
        self.pracovni_cesta = cilova_cesta or doporucene_umisteni(
            os.path.basename(self.puvodni_cesta)
        )
        self.pripravena = False

    def priprav(self):
        """Zkopiruje databazi na lokalni disk. Vraci cestu k pracovni kopii."""
        import shutil

        os.makedirs(os.path.dirname(self.pracovni_cesta), exist_ok=True)
        if os.path.exists(self.puvodni_cesta):
            shutil.copy2(self.puvodni_cesta, self.pracovni_cesta)
        self.pripravena = True
        return self.pracovni_cesta

    def uloz_zpet(self, zalohovat=True):
        """Zkopiruje pracovni kopii zpet na puvodni misto.

        Args:
            zalohovat: pred prepsanim vytvorit zalohu puvodniho souboru

        Returns:
            (uspech, zprava)
        """
        import shutil
        from datetime import datetime

        if not self.pripravena or not os.path.exists(self.pracovni_cesta):
            return False, "Pracovní kopie databáze neexistuje."

        try:
            if zalohovat and os.path.exists(self.puvodni_cesta):
                zaloha = (
                    f"{self.puvodni_cesta}.zaloha_{datetime.now():%Y%m%d_%H%M%S}"
                )
                shutil.copy2(self.puvodni_cesta, zaloha)

            shutil.copy2(self.pracovni_cesta, self.puvodni_cesta)
            return True, f"Databáze uložena zpět do {self.puvodni_cesta}"
        except Exception as e:  # noqa: BLE001
            return False, (
                f"Nepodařilo se uložit databázi zpět do {self.puvodni_cesta}:\n{e}\n\n"
                f"Data zůstávají v pracovní kopii:\n{self.pracovni_cesta}"
            )

    def je_novejsi_original(self):
        """True, pokud byl puvodni soubor mezitim zmenen (napr. synchronizaci)."""
        try:
            return (
                os.path.exists(self.puvodni_cesta)
                and os.path.exists(self.pracovni_cesta)
                and os.path.getmtime(self.puvodni_cesta)
                > os.path.getmtime(self.pracovni_cesta) + 1
            )
        except OSError:
            return False


if __name__ == "__main__":  # rychla kontrola z prikazove radky
    cesty = sys.argv[1:] or [os.getcwd()]
    for c in cesty:
        u = zjisti(c)
        znak = "!" if u.rizikove else "+"
        print(f"{znak} {c}")
        print(f"    druh={u.druh}  {u.popis}  {u.detail}")
    print(f"\nDoporučené umístění databáze: {doporucene_umisteni()}")
