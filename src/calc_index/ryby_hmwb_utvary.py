"""
Zarazeni silne ovlivnenych vodnich utvaru do kategorii I-X (ryby).

Zdroj: Janac M. a kol. (2024): Metodika hodnoceni ekologickeho potencialu
silne ovlivnenych a umelych vodnich utvaru - kategorie reka podle biologicke
slozky ryby, Tabulky 3-11.
metodiky/OOV_Metodika hodnoceni ekologickeho potencialu_reka_ryby_20241204.pdf

Metodika neodvozuje ekologicky potencial z vlastnosti profilu, ale prirazuje
kazdemu silne ovlivnenemu utvaru jednu z deseti kategorii podle toho, jake
uzivani ho ovlivnuje. Kategorie je vyctem konkretnich vodnich utvaru, proto
je tady tabulka - odvodit ji z dat nelze.

Kategorie a jejich dopad na vypocet:

    I    male toky v rybnicnich oblastech
         CZI = (TA_EQR + AR_EQR) / 2; TD, ND1 a ND2 nepouzitelne
    II   velke toky v rybnicnich oblastech
         CZI = (TD_EQR + AR_EQR) / 2 se snizenymi mezemi
    III  kanalizovane a regulovane useky velkych rek
         standardni CZI typu G se snizenymi mezemi TD a AR
    IV   sekundarni pstruhova pasma
         prerazeni do typu A, jinak standardni vypocet
    V    toky pod vodni nadrzi bez sekundarniho pstruhoveho pasma
         standardni CZI s mezemi a vahami podle Tab. 8
    VI   toky s nizkym ekologickym potencialem - stejne jako kategorie I
    VII  utvary s dobrym a velmi dobrym ekologickym stavem
         nezmenena verze CZI (potencial = stav)
    VIII utvary, u nichz lze docilit dobreho ekologickeho stavu
         nezmenena verze CZI
    IX   stojate vodni utvary - hodnoti se podle metodik pro jezera
    X    velmi male toky (pod 4. rad) - nehodnoti se

Druha polozka dvojice je typ toku, ktery metodika u profilu uvadi. Slouzi
jako kontrola proti typu odvozenemu z abiotickych parametru; pri neshode
ma prednost typ z metodiky, protoze podle nej byly nastaveny meze.
"""

from __future__ import annotations

UTVARY_KATEGORIE = {
    "HVL_0400": ("I", "C"),                     # Dehtářský potok - Bavorovice
    "HVL_0420": ("I", "C"),                     # Olešník - Zbudov
    "HVL_0590": ("I", "C"),                     # Spolský potok - Spolský mlýn
    "HVL_0610": ("I", "C"),                     # Prostřední Stoka - Třeboň
    "HVL_0660": ("I", "C"),                     # Zlatá Stoka - Ponědraž pod
    "HVL_0710": ("I", "A"),                     # Počátecký potok - Kopejtkův Horní mlýn
    "HVL_0720": ("I", "B"),                     # Radouňský potok - Radouňka
    "HVL_0820": ("I", "C"),                     # Nová Řeka - Mláka
    "HVL_0870": ("I", "B"),                     # Doňovský potok - Řípec
    "HVL_1220": ("I", "B"),                     # Mlýnský potok - Zářečí u Horažďovic
    "HVL_1300": ("I", "B"),                     # Řepický potok - Strakonice
    "HVL_1310": ("I", "B"),                     # Vítkovský potok - Kestřany
    "HVL_1390": ("I", "C"),                     # Radomilický potok - Milenovice
    "HVL_2090": ("I", "A"),                     # Olšina - Olšina
    "HVL_2750": ("I", "C"),                     # Ponědražský potok - Ponědražský rybník pod
    "HVL_2930": ("I", "C"),                     # Holenský potok - rybník Vydýmač pod
    "MOV_0890": ("I", "B"),                     # Hloučela - Plumlov - přítok
    "HVL_0680": ("II", "F"),                    # Lužnice - Veselí nad Lužnicí
    "DVL_0730": ("III", "G"),                   # Vltava - Vrané
    "DVL_0830": ("III", "G"),                   # Vraňansko- Hořínský kanál - Vrbno
    "HSL_1180": ("III", "G"),                   # Labe - Valy
    "HSL_1320": ("III", "G"),                   # Labe - Veletov
    "HSL_1340": ("III", "G"),                   # Labe - Kolín pod
    "HSL_1680": ("III", "G"),                   # Labe - Lysá nad Labem
    "HSL_2090": ("III", "G"),                   # Labe - Obříství
    "HVL_0460": ("III", "F"),                   # Vltava - Hluboká nad Vltavou
    "MOV_1170": ("III", "G"),                   # Morava - Otrokovice
    "MOV_1290": ("III", "G"),                   # Morava - nad Olšavou
    "OHL_0030": ("III", "G"),                   # Labe - Litoměřice
    "OHL_0750": ("III", "G"),                   # Labe - Pod Lovosicemi
    "DVL_0500": ("IV", "F"),                    # Želivka - Soutice
    "DYJ_0160": ("IV", "E"),                    # Dyje - Vranov
    "DYJ_0170": ("IV", "F"),                    # Dyje - Znojmo - přítok (Devět Mlýnů)
    "DYJ_0380": ("IV", "B"),                    # Svratka - Borač
    "DYJ_0530": ("IV", "B"),                    # Křetínka - Letovice
    "DYJ_0570": ("IV", "B"),                    # Bělá - Lhota Rapotina
    "DYJ_1010": ("IV", "B"),                    # Oslava - nad Balinkou
    "HOD_0400": ("IV", "E"),                    # Moravice - Ústí
    "HOD_0480": ("IV", "B"),                    # Ostravice - nad Čeladenkou
    "BER_0430": ("V", "F"),                     # Radbuza - Plzeň město
    "BER_0810": ("V", "C"),                     # Klíčava (přítok Berounky) - Klíčava pod vodárnou
    "DYJ_0490": ("V", "F"),                     # Svratka - Přízřenice
    "HOD_0590": ("V", "E"),                     # Olešná - ústí
    "HOD_0670": ("V", "E"),                     # Lučina - Slezská Ostrava
    "HOD_0820": ("V", "E"),                     # Stonávka - ústí
    "HSL_0310": ("V", "F"),                     # Labe - Hořenice
    "HVL_0310": ("V", "C"),                     # Malše - Římov pod
    "MOV_0560": ("V", "A"),                     # Stanovnice (Velká Stanovnice) - Karolinka - přítok
    "MOV_0700": ("V", "B"),                     # Bystřička - Bystřička pod
    "MOV_0920": ("V", "D"),                     # Hloučela - Prostějov (ústí)
    "MOV_1200": ("V", "D"),                     # Dřevnice - nad Lutoninkou
    "MOV_1220": ("V", "D"),                     # Fryštácký potok - Fryšták - přítok
    "MOV_1320": ("V", "D"),                     # Luhačovický potok - Újezdec
    "HSL_0170": ("VI", "B"),                    # Borecký potok - Mostek
    "HSL_1570": ("VI", "C"),                    # Blatnice - Rašovice u Nymburka
    "LNO_0090": ("VI", "B"),                    # Harcovský potok - před ústím
    "OHL_0770": ("VI", None),                   # Podkrušnohorský přivaděč - Březenecká Chomutov
    "BER_0890": ("VII", "C"),                   # Červený potok - Zdice pod
    "BER_0900": ("VII", "F"),                   # Litavka - Beroun
    "BER_0940": ("VII", "G"),                   # Berounka - Lahovice
    "HOD_0080": ("VII", "E"),                   # Jičínka - Kunín
    "HOD_0180": ("VII", "F"),                   # Odra - Svinov
    "HOD_0370": ("VII", "B"),                   # Lobník - nad nádrží Kružberk
    "HOD_0430": ("VII", "F"),                   # Odra - pod Č. Příkopem
    "HOD_0680": ("VII", "E"),                   # Ostravice - Ostrava
    "HOD_0790": ("VII", "E"),                   # Olše - nad Stonávkou
    "HOD_0870": ("VII", "E"),                   # Olše - ústí
    "HSL_0370": ("VII", "F"),                   # Metuje - nad Střelou
    "HSL_1100": ("VII", "F"),                   # Chrudimka - Nemošice
    "HSL_1790": ("VII", "B"),                   # Popelka - Ústí u Staré Paky
    "MOV_0670": ("VII", "E"),                   # Vsetínská Bečva - Vsetín
    "MOV_0680": ("VII", "B"),                   # Ratibořka - ústí
    "MOV_0710": ("VII", "E"),                   # Vsetínská Bečva - Valašské Meziříčí
    "MOV_0740": ("VII", "E"),                   # Rožnovská Bečva - Valašské Meziříčí
    "MOV_1430": ("VII", "G"),                   # Morava - Lanžhot
    "DVL_0820": ("VIII", "G"),                  # Vltava - Zelčín
    "DYJ_0200": ("VIII", "F"),                  # Dyje - Jevišovka nad
    "DYJ_0650": ("VIII", "F"),                  # Svitava - ústí
    "DYJ_1240": ("VIII", "G"),                  # Dyje - Ladná
    "HOD_0260": ("VIII", "B"),                  # Čížina - ústí
    "HOD_0290": ("VIII", "B"),                  # Opava - Vávrovice
    "HOD_0700": ("VIII", "F"),                  # Odra - Antošovice
    "HOD_1090": ("VIII", "B"),                  # Bělá - Mikulovice
    "LNO_0170": ("VIII", "B"),                  # Mandava - Rumburk - hranice
    "LNO_0180": ("VIII", "B"),                  # Mandava - Varnsdorf
    "LNO_0220": ("VIII", "B"),                  # Smědá - Luh
    "MOV_0470": ("VIII", "D"),                  # Oskava - Pňovice
    "MOV_0780": ("VIII", "B"),                  # Juhyně - Choryně
    "MOV_0860": ("VIII", "D"),                  # Romže - Vrahovice (ústí)
    "MOV_0990": ("VIII", "D"),                  # Haná - Pazderna
    "MOV_1130": ("VIII", "D"),                  # Rusava - pod Roštěnkou
    "MOV_1140": ("VIII", "D"),                  # Rusava - Hulín pod
    "MOV_1240": ("VIII", "F"),                  # Dřevnice - Otrokovice
    "MOV_1270": ("VIII", "D"),                  # Březnice - Jarošov
    "MOV_1300": ("VIII", "F"),                  # Olšava - Šumice
    "MOV_1340": ("VIII", "F"),                  # Olšava - Kunovice
    "DVL_0030": ("IX", None),                   # Vltava - Kamýk
    "DVL_0110": ("IX", None),                   # Vltava - Štěchovice
    "HVL_3030": ("IX", None),                   # Vltava - Hněvkovice
    "HSL_2390": ("X", None),                    # Šonovský potok - Rozkoš
    "HVL_0620": ("X", None),                    # Kaňovský potok - Káňov nad
    "MOV_0200": ("X", None),                    # Ostrovský potok - Lanškroun
}


#: Kategorie, u kterych se ekologicky potencial vubec nepocita.
NEHODNOCENE_KATEGORIE = {
    "IX": "stojaty vodni utvar - hodnoti se podle metodiky pro jezera",
    "X": "velmi maly tok (pod 4. Strahleruv rad) - ryby se nehodnoti",
}


def kategorie_utvaru(kod_utvaru):
    """Vrati (kategorie, typ_toku) pro vodni utvar, nebo (None, None)."""
    return UTVARY_KATEGORIE.get(kod_utvaru, (None, None))


def pocty_podle_kategorii():
    """Kolik utvaru pripada na jednotlivé kategorie - pro kontrolu."""
    from collections import Counter
    return Counter(kat for kat, _ in UTVARY_KATEGORIE.values())
