"""
Srovnani sirek sloupcu tak, aby se tabulka vesla do sve plochy.

Vychozi sirky sloupcu jsou zapsane v kodu a odpovidaji sirokemu oknu.
Na mensim monitoru se do nej tabulka nevejde a dole se objevi vodorovny
posuvnik - prehled se pak musi prohlizet po castech, prestoze by vetsina
sloupcu klidne snesla, aby byla o neco uzsi.

Tenhle modul sirky pri startu prepocita:

* Kdyz se sloupce nevejdou, umerne se zmensi. Uzke sloupce s kody by se
  ale pri umernem zmenseni staly necitelnymi driv nez siroke sloupce
  s nazvy, proto maji spodni mez - pod ni uz se nezmensuji a chybejici
  misto se vezme sirsim sloupcum.
* Kdyz naopak misto zbyva, dostane ho nejsirsi sloupec. To je zpravidla
  nazev, tedy ten, ktery se nejcasteji nevejde.

Kdyz se sloupce nevejdou ani pri spodni mezi, posuvnik zustane - to uz
je poctivejsi nez sloupce, ve kterych neni nic videt.

Sirky se srovnavaji jen pri sestaveni zalozky. Pozdejsi zmena velikosti
okna uz do nich nesaha, aby aplikace nepreprala sirku, kterou si uzivatel
sam pretahl mysi.
"""

from __future__ import annotations

#: Nejmensi sirka sloupce po zmenseni [px]. Zhruba na "ANO" nebo peticiferny
#: kod plus okraje; pod tim uz se z hodnoty nic nevycte.
MIN_SIRKA = 55

#: Kdyz je viditelna plocha uzsi nez tohle, srovnavani se preskoci -
#: tabulka jeste nema skutecnou velikost.
MIN_PLOCHA = 100


def _nejsirsi(sirky, z_indexu=None):
    """Index nejširšího sloupce; při shodě ten vpravo."""
    indexy = list(z_indexu) if z_indexu else list(range(len(sirky)))
    if not indexy:
        indexy = list(range(len(sirky)))
    return max(indexy, key=lambda i: (sirky[i], i))


def _viditelne_sloupce(pohled):
    model = pohled.model()
    if model is None:
        return []
    return [s for s in range(model.columnCount())
            if not pohled.isColumnHidden(s)]


def rozpocitej(sirky, k_dispozici, min_sirka=MIN_SIRKA):
    """Spočítá nové šířky sloupců pro danou plochu.

    Args:
        sirky: současné šířky viditelných sloupců
        k_dispozici: šířka viditelné plochy tabulky
        min_sirka: pod tuhle mez se sloupec nezmenšuje

    Returns:
        seznam nových šířek, nebo None, když se nemá měnit nic
    """
    if not sirky or k_dispozici < MIN_PLOCHA:
        return None

    celkem = sum(sirky)
    if celkem == k_dispozici:
        return None

    if celkem < k_dispozici:
        # Zbylé místo dostane nejširší sloupec - obvykle název. Při shodě
        # vyhrává ten vpravo: v detailech dvojice popisek/hodnota je to
        # hodnota, která si o místo říká.
        nove = list(sirky)
        nove[_nejsirsi(nove)] += k_dispozici - celkem
        return nove

    if len(sirky) * min_sirka > k_dispozici:
        # Ani na spodní mezi by se sloupce nevešly. Zmenšovat je nemá
        # smysl - posuvník by zůstal a nadto by v nich nebylo nic vidět.
        return None

    # Zmenšování. Sloupce, které by spadly pod mez, se na ní zafixují
    # a zbytek se rozpočítá znovu mezi ty ostatní. Opakuje se, dokud
    # nějaký další nespadne - proto smyčka, ne jediný výpočet.
    pevne = set()
    pomer = 1.0
    while True:
        pruzne = [i for i in range(len(sirky)) if i not in pevne]
        soucet = sum(sirky[i] for i in pruzne)
        rozpocet = k_dispozici - min_sirka * len(pevne)
        if not pruzne or soucet <= 0 or rozpocet <= 0:
            break
        pomer = rozpocet / soucet
        spadle = [i for i in pruzne if sirky[i] * pomer < min_sirka]
        if not spadle:
            break
        pevne.update(spadle)

    nove = [min_sirka if i in pevne else max(int(sirky[i] * pomer), min_sirka)
            for i in range(len(sirky))]

    # Zaokrouhlovalo se dolů, takže pár pixelů zbývá; ať je dostane
    # nejširší sloupec, jinak by vpravo zůstala nevyužitá mezera.
    zbytek = k_dispozici - sum(nove)
    if zbytek > 0:
        volne = [i for i in range(len(nove)) if i not in pevne]
        nove[_nejsirsi(nove, volne)] += zbytek
    return nove


def srovnej(pohled, min_sirka=MIN_SIRKA):
    """Upraví šířky sloupců tabulky podle její viditelné plochy.

    Returns:
        True, když se šířky změnily.
    """
    sloupce = _viditelne_sloupce(pohled)
    if not sloupce:
        return False

    hlavicka = pohled.horizontalHeader()
    sirky = [hlavicka.sectionSize(s) for s in sloupce]
    nove = rozpocitej(sirky, pohled.viewport().width(), min_sirka)
    if nove is None:
        return False

    for sloupec, sirka in zip(sloupce, nove):
        hlavicka.resizeSection(sloupec, sirka)
    return True


def srovnej_vse(korenovy_widget, min_sirka=MIN_SIRKA):
    """Srovná šířky ve všech tabulkách pod daným widgetem."""
    from PyQt6.QtWidgets import QTableView

    for pohled in korenovy_widget.findChildren(QTableView):
        try:
            srovnej(pohled, min_sirka)
        except Exception as chyba:  # noqa: BLE001
            # Kosmetika nesmí shodit sestavení okna.
            print(f"[sirky_sloupcu] {pohled.objectName() or pohled}: {chyba}")
