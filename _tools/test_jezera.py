"""
Kontrola vypoctu hodnoceni stojatych vod (kategorie jezero).

Overuje ctyri veci:

  1. typologii proti Priloze 1 metodiky (77 vymezenych vodnich utvaru)
  2. prevod bodu na EQR proti vzorci z kap. 6.3
  3. hranicni pripady bodovani metrik proti Tabulkam 4, 6 a 8
  4. zvlastni pravidla (okounovita obsadka, rybniky, pruhlednost na dno)

Pouziti:
    python _tools/test_jezera.py
"""

import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOREN, "_tools", "qtstub"))
sys.path.insert(0, os.path.join(KOREN, "src"))

_stav = {"ok": 0, "chyba": 0}


def zkontroluj(popis, spocteno, ocekavano, tolerance=0.001):
    if isinstance(ocekavano, (str, type(None))) or isinstance(spocteno, str):
        shoda = spocteno == ocekavano
    else:
        shoda = spocteno is not None and abs(spocteno - ocekavano) <= tolerance
    _stav["ok" if shoda else "chyba"] += 1
    znacka = "ok  " if shoda else "CHYBA"
    print(f"  {znacka} {popis:58s} {str(spocteno):>16s}  čekáno {ocekavano}")


# ---------------------------------------------------------------------------

def test_typologie():
    """Typologie proti Priloze 1 metodiky."""
    from calc_index.jezera_typologie import typ_z_kodu, urci_typ

    print("\n1. Typologie proti Příloze 1 metodiky (Tabulka 1)")
    # (mnm, zmax, zprum, trt, geologie, ocekavany kod)
    pripady = [
        (354.1, 28.5, 9.3, 0.14, 1, "2BC21F22"),   # Hracholusky
        (313.6, 7.0, 2.7, 0.02, 1, "2BC11F11"),    # České údolí
        (171.4, 3.9, 2.2, 0.03, 1, "1BC11F11"),    # Nové Mlýny I
        (724.9, 19.3, 6.0, 0.67, 1, "3BC21F23"),   # Lipno I
        (615.3, 9.0, 4.3, 0.97, 1, "2BC11F13"),    # Velké Dářko
        (496.0, 60.5, 26.6, 1.10, 1, "2BC21F23"),  # Slezská Harta
        (195.0, 75.0, 22.0, 1.00, 2, "1BC22F23"),  # Most
    ]
    for mnm, zmax, zprum, trt, geo, ocekavano in pripady:
        typ, _ = urci_typ(mnm=mnm, zmax=zmax, zprum=zprum, trt=trt,
                          geologie=geo)
        zkontroluj(f"{mnm} m, zmax {zmax}, zprum {zprum}, TRT {trt}",
                   typ.kod, ocekavano)

    zkontroluj("rozklad kódu zpět na typ", typ_z_kodu("2BC21F22").kod,
               "2BC21F22")
    typ, duvod = urci_typ(mnm=400, zmax=20, zprum=None, trt=0.5)
    zkontroluj("chybějící průměrná hloubka", str(typ), "None")


def test_hranice_typologie():
    """Mezni hodnoty podle Tabulky 1."""
    from calc_index.jezera_typologie import urci_typ

    print("\n2. Mezní hodnoty typologie")

    def kod(mnm=400, zmax=20, zprum=10, trt=0.3):
        return urci_typ(mnm=mnm, zmax=zmax, zprum=zprum, trt=trt)[0].kod

    zkontroluj("199,9 m n. m. → A=1", kod(mnm=199.9)[0], "1")
    zkontroluj("200,0 m n. m. → A=2", kod(mnm=200.0)[0], "2")
    zkontroluj("699,9 m n. m. → A=2", kod(mnm=699.9)[0], "2")
    zkontroluj("700,0 m n. m. → A=3", kod(mnm=700.0)[0], "3")
    zkontroluj("zmax 12,9 → D=1", kod(zmax=12.9)[3], "1")
    zkontroluj("zmax 13,1 → D=2", kod(zmax=13.1)[3], "2")
    zkontroluj("zprum 4,9 → G=1", kod(zprum=4.9)[6], "1")
    zkontroluj("zprum 5,1 → G=2", kod(zprum=5.1)[6], "2")
    zkontroluj("TRT 0,05 → H=1", kod(trt=0.05)[7], "1")
    zkontroluj("TRT 0,30 → H=2", kod(trt=0.30)[7], "2")
    zkontroluj("TRT 0,50 → H=3", kod(trt=0.50)[7], "3")


def test_eqr():
    """Prevod bodu na EQR podle vzorce z kap. 6.3."""
    from calc_index.jezera_common import (
        KLESA, ROSTE, TRIDY_JEZERA, TRIDY_RYBY, eqr_z_bodu,
        klasifikuj_jezero, oboduj,
    )

    print("\n3. Převod bodů na EQR (kap. 6.3)")
    zkontroluj("všechny metriky 5 bodů → EQR 1", eqr_z_bodu([5, 5, 5, 5]), 1.0)
    zkontroluj("všechny metriky 1 bod → EQR 0", eqr_z_bodu([1, 1, 1, 1]), 0.0)
    zkontroluj("všechny metriky 3 body → EQR 0,5", eqr_z_bodu([3, 3, 3, 3]), 0.5)
    zkontroluj("5,5,3,1 → (14-4)/(20-4)", eqr_z_bodu([5, 5, 3, 1]), 0.625)
    zkontroluj("None se do počtu metrik nezapočítá",
               eqr_z_bodu([5, 5, None]), 1.0)
    zkontroluj("žádná platná metrika", eqr_z_bodu([None, None]), None)

    print("\n4. Bodování metrik (uzavřené střední pásmo)")
    zkontroluj("rostoucí, pod dolní mezí", oboduj(29, 30, 40, ROSTE), 5)
    zkontroluj("rostoucí, přesně na dolní mezi", oboduj(30, 30, 40, ROSTE), 3)
    zkontroluj("rostoucí, přesně na horní mezi", oboduj(40, 30, 40, ROSTE), 3)
    zkontroluj("rostoucí, nad horní mezí", oboduj(41, 30, 40, ROSTE), 1)
    zkontroluj("klesající, nad horní mezí", oboduj(21, 10, 20, KLESA), 5)
    zkontroluj("klesající, na horní mezi", oboduj(20, 10, 20, KLESA), 3)
    zkontroluj("klesající, pod dolní mezí", oboduj(9, 10, 20, KLESA), 1)

    print("\n5. Třídy ekologického potenciálu")
    zkontroluj("EQR 1,00 (Tab. 5)", klasifikuj_jezero(1.0, TRIDY_JEZERA),
               "dobrý a lepší potenciál")
    zkontroluj("EQR 0,75 (Tab. 5)", klasifikuj_jezero(0.75, TRIDY_JEZERA),
               "dobrý a lepší potenciál")
    zkontroluj("EQR 0,74 (Tab. 5)", klasifikuj_jezero(0.74, TRIDY_JEZERA),
               "střední potenciál")
    zkontroluj("EQR 0,00 (Tab. 5)", klasifikuj_jezero(0.0, TRIDY_JEZERA),
               "zničený potenciál")
    zkontroluj("ryby EQR 0,88 (Příloha 3)",
               klasifikuj_jezero(0.88, TRIDY_RYBY), "lepší potenciál")
    zkontroluj("ryby EQR 0,63 (Příloha 3)",
               klasifikuj_jezero(0.63, TRIDY_RYBY), "dobrý potenciál")
    zkontroluj("ryby EQR 0,62 (Příloha 3)",
               klasifikuj_jezero(0.62, TRIDY_RYBY), "střední potenciál")


def test_fytoplankton():
    """CZ-PHYPI - trificky index, podil sinic, hranice Tabulky 4."""
    from calc_index.jezera_fp import podil_sinic, troficky_index, vyhodnot
    from calc_index.jezera_typologie import urci_typ

    print("\n6. Fytoplankton (CZ-PHYPI, Tabulka 4)")

    # Trificky index: jeden taxon se 100 % biomasy dá přímo své optimum.
    idx, znamo = troficky_index([
        {"nazev": "Microcystis aeruginosa", "biomasa": 10.0}])
    zkontroluj("index jednoho taxonu = jeho optimum", idx, 1.788)
    zkontroluj("podíl známé biomasy", znamo, 1.0)

    # Dva taxony půl na půl -> průměr optim.
    idx, _ = troficky_index([
        {"nazev": "Microcystis aeruginosa", "biomasa": 5.0},   # 1,788
        {"nazev": "Dinobryon sp.", "biomasa": 5.0},            # -0,73
    ])
    zkontroluj("dva taxony půl na půl", idx, (1.788 - 0.73) / 2)

    # Neznámý rod má s = 0 a ředí index k nule.
    idx, znamo = troficky_index([
        {"nazev": "Microcystis aeruginosa", "biomasa": 5.0},
        {"nazev": "Nesmyslnyrod sp.", "biomasa": 5.0},
    ])
    zkontroluj("neznámý rod ředí index k nule", idx, 0.894)
    zkontroluj("podíl známé biomasy je poloviční", znamo, 0.5)

    # Podíl sinic: pikoplankton se nezapočítá.
    taxony = [
        {"nazev": "Microcystis aeruginosa", "biomasa": 20.0,
         "trida": "Cyanobacteria"},
        {"nazev": "Aphanocapsa sp.", "biomasa": 20.0,
         "trida": "Cyanobacteria"},          # pikoplankton
        {"nazev": "Asterionella formosa", "biomasa": 60.0,
         "trida": "Bacillariophyceae"},
    ]
    zkontroluj("podíl sinic bez pikoplanktonu [%]", podil_sinic(taxony)[0], 20.0)

    # Třída se dohledá podle rodu i bez taxalistu (Příloha 2 ji obsahuje).
    bez_tridy = [{"nazev": n, "biomasa": b} for n, b in
                 [("Microcystis aeruginosa", 20.0), ("Aphanocapsa sp.", 20.0),
                  ("Asterionella formosa", 60.0)]]
    zkontroluj("podíl sinic i bez uvedené třídy [%]",
               podil_sinic(bez_tridy)[0], 20.0)
    zkontroluj("neznámý rod se ohlásí jako nezařazený",
               podil_sinic([{"nazev": "Nesmyslnyrod sp.", "biomasa": 5.0}])[1],
               1.0)

    # Celý výpočet pro typ 2-*-2 (Tab. 4: chl-a < 10 | 10-20 | > 20).
    typ, _ = urci_typ(mnm=400, zmax=20, zprum=10, trt=0.3)
    zkontroluj("typ pro test", typ.kod, "2BC21F22")
    v = vyhodnot(typ, taxony, chlorofyl=5.0)
    zkontroluj("chlorofyl 5 µg/l → 5 bodů", v["body"]["FPJ01"], 5)
    v = vyhodnot(typ, taxony, chlorofyl=15.0)
    zkontroluj("chlorofyl 15 µg/l → 3 body", v["body"]["FPJ01"], 3)
    v = vyhodnot(typ, taxony, chlorofyl=25.0)
    zkontroluj("chlorofyl 25 µg/l → 1 bod", v["body"]["FPJ01"], 1)
    zkontroluj("biomasa 100 mm³/l → 1 bod", v["body"]["FPJ02"], 1)
    zkontroluj("podíl sinic 20 % → 1 bod", v["body"]["FPJ03"], 1)


def test_makrofyta():
    """CZ-MPHYI - Tabulka 6."""
    from calc_index.jezera_mf import vyhodnot

    print("\n7. Makrofyta (CZ-MPHYI, Tabulka 6)")
    hodne = [{"nazev": f"Druh {i}", "pokryvnost": 3.0} for i in range(12)]
    v = vyhodnot(hodne)
    zkontroluj("12 druhů → početnost 5 bodů", v["body"]["MFJ01"], 5)
    zkontroluj("pokryvnost 36 % → 5 bodů", v["body"]["MFJ02"], 5)
    zkontroluj("obě metriky nejlepší → EQR 1", v["eqr"], 1.0)
    zkontroluj("třída", v["trida"], "dobrý a lepší potenciál")

    malo = [{"nazev": "Druh A", "pokryvnost": 2.0},
            {"nazev": "Druh B", "pokryvnost": 3.0}]
    v = vyhodnot(malo)
    zkontroluj("2 druhy → početnost 1 bod", v["body"]["MFJ01"], 1)
    zkontroluj("pokryvnost 5 % → 1 bod", v["body"]["MFJ02"], 1)
    zkontroluj("obě metriky nejhorší → EQR 0", v["eqr"], 0.0)
    zkontroluj("upozornění na málo druhů",
               "omezenou vypovídací hodnotu" in (v["poznamka"] or ""), True)

    stred = [{"nazev": f"Druh {i}", "pokryvnost": 2.0} for i in range(7)]
    v = vyhodnot(stred)
    zkontroluj("7 druhů → početnost 3 body", v["body"]["MFJ01"], 3)
    zkontroluj("pokryvnost 14 % → 3 body", v["body"]["MFJ02"], 3)
    zkontroluj("duplicitní názvy se počítají jednou",
               float(vyhodnot([{"nazev": "Týž druh", "pokryvnost": 1.0}] * 5
                              )["metriky"]["MFJ01"]), 1.0)


def test_ryby():
    """CZ-FBI - Tabulka 8 a zvlastni pravidla."""
    from calc_index.jezera_ryby import (
        pocet_druhu_0plus, podil_okouna_vsechny_site, vyhodnot,
    )
    from calc_index.jezera_typologie import urci_typ

    print("\n8. Ryby (CZ-FBI, Tabulka 8)")
    hluboky, _ = urci_typ(mnm=400, zmax=20, zprum=10, trt=0.3)
    melky, _ = urci_typ(mnm=400, zmax=10, zprum=3, trt=0.3)
    zkontroluj("hluboký typ", hluboky.kod, "2BC21F22")
    zkontroluj("mělký typ", melky.kod, "2BC11F12")

    ulovky = [
        {"nazev": "Abramis brama", "sit": "BT", "zona": "H",
         "val": 100, "biomasa": 10},
        {"nazev": "Perca fluviatilis", "sit": "BT", "zona": "H",
         "val": 100, "biomasa": 10},
        {"nazev": "Rutilus rutilus", "sit": "BT", "zona": "H",
         "val": 100, "biomasa": 80},
    ]
    v = vyhodnot(melky, ulovky)
    zkontroluj("mělký typ používá 5 metrik", len(v["body"]), 5)
    zkontroluj("biomasa v BT 100 kg → 1 bod", v["body"]["RYJ01"], 1)
    zkontroluj("cejn 10 % biomasy BT → 5 bodů", v["body"]["RYJ02"], 5)
    zkontroluj("okoun 10 % biomasy BT → 3 body", v["body"]["RYJ03"], 3)
    zkontroluj("ježdík 0 % početnosti BT → 5 bodů", v["body"]["RYJ04"], 5)

    v = vyhodnot(hluboky, ulovky)
    zkontroluj("hluboký typ používá 9 metrik", len(v["body"]), 9)

    # Okounovita obsadka vyrazuje metriku 0+ ryb.
    okounova = ulovky + [{"nazev": "Perca fluviatilis", "sit": "PT",
                          "zona": "H", "val": 50, "biomasa": 200}]
    # BT: cejn 10 + okoun 10 + plotice 80 = 100 kg; PT: okoun 200 kg.
    # Celkem 300, z toho okoun 210 -> 70 %.
    zkontroluj("podíl okouna ve všech sítích [%]",
               podil_okouna_vsechny_site(okounova), 70.0)
    v = vyhodnot(hluboky, okounova)
    zkontroluj("metrika 0+ vyřazena", "RYJ05" in v["body"], False)
    zkontroluj("hluboký typ pak má 8 metrik", len(v["body"]), 8)
    zkontroluj("poznámka o okounovité obsádce",
               "okounovitá obsádka" in (v["poznamka"] or ""), True)

    # Pritomnost 0+ ryb - sjednoceni pres oba typy siti.
    juv = [
        {"nazev": "Abramis brama", "sit": "BT", "juv": 1, "biomasa": 1},
        {"nazev": "Rutilus rutilus", "sit": "PT", "juv": 1, "biomasa": 1},
        {"nazev": "Rutilus rutilus", "sit": "BT", "juv": 1, "biomasa": 1},
        {"nazev": "Squalius cephalus", "sit": "BT", "juv": 1, "biomasa": 1},
    ]
    zkontroluj("0+ ze šesti běžných druhů (jelec se nepočítá)",
               float(pocet_druhu_0plus(juv)), 2.0)

    # Rybniky se podle ryb nehodnoti.
    v = vyhodnot(hluboky, ulovky, rybnik=True)
    zkontroluj("rybník se podle ryb nehodnotí", v["eqr"], None)
    zkontroluj("s vysvětlením",
               "rybářské hospodaření" in (v["poznamka"] or ""), True)

    # Lososovite maji nad 700 m prisnejsi meze (Tab. 8, typ 3-*-2-*).
    horsky, _ = urci_typ(mnm=750, zmax=20, zprum=10, trt=0.3)
    lososi = [{"nazev": "Coregonus maraena", "sit": "BT", "biomasa": 3},
              {"nazev": "Rutilus rutilus", "sit": "BT", "biomasa": 97}]
    zkontroluj("3 % lososovitých pod 700 m → 5 bodů",
               vyhodnot(hluboky, lososi)["body"]["RYJ11"], 5)
    zkontroluj("3 % lososovitých nad 700 m → 3 body",
               vyhodnot(horsky, lososi)["body"]["RYJ11"], 3)


def test_fyzchem():
    """Vseobecne fyzikalne-chemicke slozky (Tabulka 3)."""
    from calc_index.jezera_fyzchem import DOBRY, HORSI, MAX, vyhodnot
    from calc_index.jezera_typologie import urci_typ

    print("\n9. Fyzikálně-chemické složky (Tabulka 3)")
    # typ 2-*-2: průhlednost 3,0 / 2,5; teplota 19-25 / 20-26; Pcelk 0,020 / 0,030
    typ, _ = urci_typ(mnm=400, zmax=20, zprum=10, trt=0.3)
    dobre = dict(pruhlednost=3.5, teplota_prumer=18, teplota_max=24,
                 kyslik_min=80, kyslik_max=110, ph_min=7.0, ph_max=8.0,
                 pcelk=0.015)
    v = vyhodnot(typ, **dobre)
    zkontroluj("vše v mezích M/D", v["vysledek"], MAX)

    v = vyhodnot(typ, **{**dobre, "pcelk": 0.025})
    zkontroluj("fosfor mezi M/D a D/S", v["vysledek"], DOBRY)
    v = vyhodnot(typ, **{**dobre, "pcelk": 0.035})
    zkontroluj("fosfor za D/S", v["vysledek"], HORSI)

    v = vyhodnot(typ, **{**dobre, "pruhlednost": 2.7})
    zkontroluj("průhlednost mezi mezemi", v["vysledek"], DOBRY)
    v = vyhodnot(typ, **{**dobre, "pruhlednost": 2.0})
    zkontroluj("průhlednost za D/S", v["vysledek"], HORSI)

    v = vyhodnot(typ, **{**dobre, "ph_min": 4.5})
    zkontroluj("pH pod dolní mezí D/S", v["vysledek"], HORSI)
    v = vyhodnot(typ, **{**dobre, "kyslik_max": 180})
    zkontroluj("přesycení kyslíkem mezi mezemi", v["vysledek"], DOBRY)

    v = vyhodnot(typ, **{**dobre, "pruhlednost": 1.0, "hloubka_profilu": 1.0})
    zkontroluj("průhlednost až na dno", v["ukazatele"]["pruhlednost"], MAX)
    zkontroluj("s poznámkou", "až na dno" in (v["poznamka"] or ""), True)

    # Vse ostatni je na maximalnim potencialu, jen maximalni teplota 25,5
    # spada mezi meze M/D (25) a D/S (26) - vysledek musi klesnout na DOBRY.
    v = vyhodnot(typ, **{**dobre, "teplota_max": 25.5})
    zkontroluj("nejhorší ukazatel rozhoduje", v["vysledek"], DOBRY)
    v = vyhodnot(typ, **{**dobre, "teplota_max": 27})
    zkontroluj("teplota za mezí D/S", v["vysledek"], HORSI)


def main():
    test_typologie()
    test_hranice_typologie()
    test_eqr()
    test_fytoplankton()
    test_makrofyta()
    test_ryby()
    test_fyzchem()
    print(f"\nKontrol prošlo: {_stav['ok']}, selhalo: {_stav['chyba']}")
    return 1 if _stav["chyba"] else 0


if __name__ == "__main__":
    sys.exit(main())
