"""
Prevod nazvu taxonu z kalibracniho sesitu vysychavych toku na taxalist.

Sesit pouziva misty jinou konvenci zapisu nez `taxalist_MZB`. Nejde
o odlisne taxony, jen o odlisny zpusob, jak se tentyz taxon pise.
Bez prevodu z vypoctu vypadne 63 taxonu, coz je 4,53 % celkove
abundance - a hlavne to zkresli Margalefuv index, ktery pocita taxony.

Prevod je zamerne zapsany jako vycet, ne jako automaticke parovani
podle podobnosti. U kazde polozky je tak videt, co se s cim spojilo,
a da se to odborne posoudit. Vzory, podle kterych vznikl:

    podrod          taxalist vklada podrod: `Simulium ornatum`
                    -> `Simulium (Simulium) ornatum`
    celed/podceled  jina uroven zarazeni: `Tubificidae Gen. sp.`
                    -> `Tubificinae Gen. sp.`
    pripona         doplneni nebo odebrani `-Gr.`, ` sp.`, ` Lv.`,
                    ` Ad.`, ` juv.`, `cf.`
    pravopis        pravopisna varianta: `Oxycera meigeni`
                    -> `Oxycera meigenii`
    velikost pismen `gen. sp.` -> `Gen. sp.`

Prevod pokryva 51 taxonu = 4,45 % abundance. Zbylych 12 taxonu
(0,07 % abundance) v taxalistu neni vubec - viz NEPRIRAZENO.

Pouziva se prepinacem `--nazvy` skriptu `import_vysychave.py` a
srovnavaci report ukazuje obe varianty vedle sebe.
"""

#: {nazev v kalibracnim sesitu: nazev v taxalist_MZB}
PREVOD = {
    # --- celed / podceled ---------------------------------------------
    "Tubificidae Gen. sp.": "Tubificinae Gen. sp.",

    # --- vlozeny podrod -----------------------------------------------
    "Simulium ornatum": "Simulium (Simulium) ornatum",
    "Simulium vernum": "Simulium (Nevermannia) vernum",
    "Simulium cryophilum": "Simulium (Nevermannia) cryophilum",
    "Simulium angustipes": "Simulium (Eusimulium) angustipes",
    "Simulium angustitarse": "Simulium (Nevermannia) angustitarse",
    "Simulium noelleri": "Simulium (Simulium) noelleri",
    "Simulium costatum": "Simulium (Nevermannia) costatum",
    "Simulium erythrocephalum": "Simulium (Boophthora) erythrocephalum",
    "Simulium trifasciatum": "Simulium (Simulium) trifasciatum",
    "Simulium argyreatum": "Simulium (Simulium) argyreatum",
    "Simulium lundstromi": "Simulium (Nevermannia) lundstromi",
    "Simulium reptans": "Simulium (Simulium) reptans",
    "Simulium variegatum": "Simulium (Simulium) variegatum",
    "Simulium aureum": "Simulium (Eusimulium) aureum",
    "Simulium brevidens": "Simulium (Nevermannia) brevidens",
    "Simulium rostratum": "Simulium (Simulium) rostratum",
    "Simulium equinum": "Simulium (Wilhelmia) equinum",
    "Simulium lineatum": "Simulium (Wilhelmia) lineatum",
    "Simulium velutinum": "Simulium (Eusimulium) velutinum",
    "Simulium degrangei": "Simulium (Simulium) degrangei",
    "Simulium morsitans": "Simulium (Simulium) morsitans",
    "Simulium vulgare": "Simulium (Simulium) vulgare",
    "Cricotopus bicinctus": "Cricotopus (Cricotopus) bicinctus",
    "Cricotopus triannulatus": "Cricotopus (Cricotopus) triannulatus",
    "Cricotopus annulator": "Cricotopus (Cricotopus) annulator",
    "Cricotopus trifascia": "Cricotopus (Cricotopus) trifascia",
    "Psectrocladius limbatellus-Gr.":
        "Psectrocladius (Psectrocladius) limbatellus-Gr.",
    "Psectrocladius sordidellus-Gr.":
        "Psectrocladius (Psectrocladius) sordidellus-Gr.",
    "Polypedilum nubeculosum-Gr.": "Polypedilum (Polypedilum) nubeculosum-Gr.",
    "Polypedilum laetum-Gr.": "Polypedilum (Polypedilum) laetum-Gr.",
    "Polypedilum sordens": "Polypedilum (Pentapedilum) sordens",
    "Rheocricotopus glabricollis":
        "Rheocricotopus (Psilocricotopus) glabricollis",

    # --- doplnena pripona ----------------------------------------------
    "Procladius (Holotanypus)": "Procladius (Holotanypus) sp.",
    "Procladius (Psilotanypus)": "Procladius (Psilotanypus) sp.",
    "Eukiefferiella clypeata/pseudomontana":
        "Eukiefferiella clypeata/pseudomontana-Gr.",

    # --- odebrana pripona ----------------------------------------------
    "Tvetenia discoloripes-Gr.": "Tvetenia discoloripes",
    "Metriocnemus hygropetricus-Gr.": "Metriocnemus hygropetricus",
    "Plecoptera Lv.": "Plecoptera",
    "Ephemeroptera Lv.": "Ephemeroptera",
    "Apsectrotanypus/Macropelopia juv.": "Apsectrotanypus/Macropelopia sp.",
    "Tanypodinae g.sp. juv.": "Tanypodinae Gen. sp.",
    "Limnophila cf. schranki": "Limnophila schranki",
    "Euphylidorea cf. meigenii": "Euphylidorea meigenii",
    "Neopachygaster sp. cf.": "Neopachygaster sp.",

    # --- pravopisna varianta -------------------------------------------
    "Oxycera meigeni": "Oxycera meigenii",
    "Ilybius chalconotus Ad.": "Ilybius chalconatus Ad.",
    "Oreodytes sanmarki Ad.": "Oreodytes sanmarkii Ad.",
    "Chaetogaster cristalinus": "Chaetogaster cristallinus",

    # --- velikost pismen ------------------------------------------------
    "Mycetophilidae gen. sp.": "Mycetophilidae Gen. sp.",
    "Asilidae gen. sp.": "Asilidae Gen. sp.",
}

#: Taxony, ktere v `taxalist_MZB` nemaji protejsek ani po prevodu.
#: Dohromady 0,07 % abundance, na vysledky nemaji vliv. Nechavaji se
#: tak, jak jsou - dosazovat za ne neco podobneho by bylo hadani.
NEPRIRAZENO = (
    "Henlea/Fridericia sp.",           # 1496 jedinců
    "Micropterna lateralis/sequax",    # 71 - taxalist zná jen M. lateralis
    "Bythonomus lemani",               # 70
    "Paratrichocladius nivalis",       # 58
    "Duckhousiella ustulata",          # 8
    "Allocladius sp.",                 # 2
    "Centroptilum pennulatum",         # 2
    "Eukiefferiella rectangularis-Gr.",  # 2
    "Stercutus niveus",                # 2
    "Vestiplex sp.",                   # 2
    "Discobola cf. annulata",          # 0
    "Paratrichocladius skirwithensis",  # 0
)

#: Polozky, u kterych je prevod odbornym rozhodnutim, ne jen prepisem.
#: Stoji za to je pri revizi projit prednostne.
K_REVIZI = {
    "Tubificidae Gen. sp.": (
        "čeleď se mapuje na podčeleď; taxalist Tubificidae nezná, "
        "vede jen řád Tubificida a Tubificinae Gen. sp. "
        "Nejvydatnější položka převodu (69 826 jedinců)."
    ),
    "Tvetenia discoloripes-Gr.": (
        "skupina se mapuje na druh; taxalist vede i "
        "Tvetenia discoloripes/verralli, což může být bližší protějšek"
    ),
    "Metriocnemus hygropetricus-Gr.": (
        "skupina se mapuje na druh"
    ),
    "Tanypodinae g.sp. juv.": (
        "juvenilní stadium se slučuje s Tanypodinae Gen. sp."
    ),
}


def preved(nazev):
    """Vrati nazev podle taxalistu, nebo puvodni, kdyz prevod neni."""
    return PREVOD.get(nazev, nazev)


def kontrola(db_connection):
    """Overi, ze cile prevodu v taxalistu skutecne jsou.

    Returns:
        list nazvu, ktere v `taxalist_MZB` chybi (prazdny = v poradku)
    """
    cur = db_connection.execute("SELECT NAME FROM taxalist_MZB")
    znama = {r[0] for r in cur}
    return sorted(c for c in PREVOD.values() if c not in znama)
