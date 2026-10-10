"""
Troficka optima a taxonomicke zarazeni fytoplanktonu (Priloha 2 metodiky).

Zdroj:
    Borovec J. a kol. (2014): Metodika pro hodnoceni ekologickeho potencialu
    silne ovlivnenych a umelych vodnich utvaru - kategorie jezero, Priloha 2.
    Hodnoty prevzaty z Phillips a kol. (2013).

Priloha 2 vede u kazdeho rodu troficke optimum, rad a tridu. Vsechny tri
udaje jsou tady zachovane, protoze trida se pouziva jeste jednou - pri
vypoctu podilu sinic na celkove biomase. Aplikace tak nepotrebuje zvlastni
taxalist fytoplanktonu stojatych vod.

Zalozni hodnoty na urovni radu a tridy se pouziji, kdyz rod v seznamu neni.
Poradi vyhledavani (viz `troficke_optimum`):

    rod -> rad -> trida -> 0.0

Metodika rika: "Taxonum, jejichz troficka optima nejsou znama, byla
prirazena hodnota s = 0." Nula je stredni hodnota skaly, takze takovy taxon
vysledny index neposouva ani nahoru, ani dolu - jen zredi vahu ostatnich.

POZOR: soubor je generovan z PDF, needitujte rucne.
"""

#: Rody: nazev -> (troficke optimum, rad, trida). 196 polozek.
OPTIMA_RODY = {
    "Acanthoceras": (0.561, 'Centrales', 'Bacillariophyceae'),
    "Achnanthes": (-0.504, 'Pennales', 'Bacillariophyceae'),
    "Achnanthidium": (0.1, 'Pennales', 'Bacillariophyceae'),
    "Achroonema": (1.364, None, 'Cyanobacteria'),
    "Actinastrum": (2.608, 'Chlorococcales', 'Chlorophyceae'),
    "Actinocyclus": (3.43, 'Centrales', 'Bacillariophyceae'),
    "Amphidinium": (-0.14, 'Gymnodiniales', 'Dinophyceae'),
    "Amphora": (0.463, 'Pennales', 'Bacillariophyceae'),
    "Anabaena": (0.984, 'Nostocales', 'Cyanobacteria'),
    "Anabaenopsis": (3.311, 'Nostocales', 'Cyanobacteria'),
    "Ankistrodesmus": (0.47, 'Chlorococcales', 'Chlorophyceae'),
    "Ankyra": (-0.071, 'Chlorococcales', 'Chlorophyceae'),
    "Aphanizomenon": (1.595, 'Nostocales', 'Cyanobacteria'),
    "Aphanocapsa": (0.562, 'Chroococcales', 'Cyanobacteria'),
    "Aphanothece": (0.154, 'Chroococcales', 'Cyanobacteria'),
    "Asterionella": (-0.227, 'Pennales', 'Bacillariophyceae'),
    "Aulacoseira": (0.847, 'Centrales', 'Bacillariophyceae'),
    "Bitrichia": (-1.586, 'Stylococcales', 'Chrysophyceae'),
    "Botryococcus": (-1.008, 'Chlorococcales', 'Chlorophyceae'),
    "Carteria": (-0.48, 'Volvocales', 'Chlorophyceae'),
    "Centritractus": (0.992, None, 'MischococcaleXanthophyceae'),
    "Ceratium": (0.583, 'Peridiniales', 'Dinophyceae'),
    "Chlamydocapsa": (-0.139, 'Tetrasporales', 'Chlorophyceae'),
    "Chlamydomonas": (0.182, 'Volvocales', 'Chlorophyceae'),
    "Chlorella": (1.373, 'Chlorellales', 'Trebouxiophyceae'),
    "Chlorogonium": (2.624, 'Volvocales', 'Chlorophyceae'),
    "Chlorotetraedron": (1.367, 'Chlorococcales', 'Chlorophyceae'),
    "Chromulina": (-1.28, 'Chromulinales', 'Chrysophyceae'),
    "Chroococcus": (0.559, 'Chroococcales', 'Cyanobacteria'),
    "Chroomonas": (-1.042, None, 'CryptomonadaCryptophyceae'),
    "Chrysamoeba": (-0.151, 'Chromulinales', 'Chrysophyceae'),
    "Chrysidiastrum": (-1.32, 'Chromulinales', 'Chrysophyceae'),
    "Chrysochromulina": (-0.472, 'Prymnesiales', None),
    "Chrysococcus": (-0.468, 'Chromulinales', 'Chrysophyceae'),
    "Chrysolykos": (-1.992, 'Chromulinales', 'Chrysophyceae'),
    "Chrysosphaerella": (-0.59, 'Chromulinales', 'Chrysophyceae'),
    "Chrysostephanospha": (-1.583, 'Chromulinales', 'Chrysophyceae'),
    "Clos": (1.595, 'teriopsisChlorococcales', 'Chlorophyceae'),
    "Closterium": (0.732, 'Desmidiales', 'Conjugatophyceae'),
    "Cocconeis": (1.148, 'Pennales', 'Bacillariophyceae'),
    "Coelastrum": (1.078, 'Chlorococcales', 'Chlorophyceae'),
    "Coelosphaerium": (0.827, 'Chroococcales', 'Cyanobacteria'),
    "Coenochloris": (0.372, 'Chlorococcales', 'Chlorophyceae'),
    "Coenococcus": (-0.919, 'Chlorococcales', 'Chlorophyceae'),
    "Coenocystis": (0.98, 'Chlorococcales', 'Chlorophyceae'),
    "Colacium": (0.098, 'Euglenales', 'Euglenophyceae'),
    "Cosmarium": (0.081, 'Desmidiales', None),
    "Crucigenia": (0.056, 'Chlorococcales', 'Chlorophyceae'),
    "Crucigeniella": (0.17, 'Chlorococcales', 'Chlorophyceae'),
    "Cryptomonas": (0.189, 'Cryptomonadales', 'Cryptophyceae'),
    "Cyanodictyon": (0.318, 'Chroococcales', 'Cyanobacteria'),
    "Cyanonephron": (1.289, 'Chroococcales', 'Cyanobacteria'),
    "Cyclostephanos": (2.223, 'Centrales', 'Bacillariophyceae'),
    "Cyclotella": (-0.21, 'Centrales', 'Bacillariophyceae'),
    "Cylindrospermopsis": (2.121, 'Nostocales', 'Cyanobacteria'),
    "Cylindrotheca": (2.132, 'Pennales', 'Bacillariophyceae'),
    "Cymatopleura": (1.577, 'Pennales', 'Bacillariophyceae'),
    "Cymbella": (0.353, 'Pennales', 'Bacillariophyceae'),
    "Diatoma": (1.082, 'Pennales', 'Bacillariophyceae'),
    "Dictyosphaerium": (0.094, 'Chlorococcales', 'Chlorophyceae'),
    "Didymocystis": (0.637, 'Chlorococcales', 'Chlorophyceae'),
    "Dinobryon": (-0.73, 'Chromulinales', 'Chrysophyceae'),
    "Diplochloris": (3.853, 'Chlorococcales', 'Chlorophyceae'),
    "Discostella": (-1.58, 'Centrales', 'Bacillariophyceae'),
    "Elakatothrix": (-1.0, None, 'Klebsormidiophyceae'),
    "Epipyxis": (-1.25, 'Chromulinales', 'Chrysophyceae'),
    "Erkenia": (0.797, 'Chromulinales', 'Chrysophyceae'),
    "Euastrum": (-0.49, 'Desmidiales', 'Conjugatophyceae'),
    "Eudorina": (0.694, 'Volvocales', 'Chlorophyceae'),
    "Euglena": (2.095, 'Euglenales', 'Euglenophyceae'),
    "Eunotia": (-0.32, 'Pennales', 'Bacillariophyceae'),
    "Eutetramorus": (2.048, 'Chlorococcales', 'Chlorophyceae'),
    "Fragilaria": (0.317, 'Pennales', 'Bacillariophyceae'),
    "Franceia": (0.504, 'Chlorococcales', 'Chlorophyceae'),
    "Frustulia": (-1.39, 'Pennales', 'Bacillariophyceae'),
    "Geitlerinema": (2.695, 'Oscillatoriales', 'Cyanobacteria'),
    "Glenodinium": (0.192, 'Peridiniales', 'Dinophyceae'),
    "Gloeocapsa": (0.559, 'Chroococcales', 'Cyanobacteria'),
    "Gloeocystis": (-1.64, 'Chlorococcales', 'Chlorophyceae'),
    "Gloeotila": (-1.25, 'Ulotrichales', 'Ulvophyceae'),
    "Gloeotrichia": (1.232, 'Nostocales', 'Cyanobacteria'),
    "Golenkinia": (1.053, 'Chlorococcales', 'Chlorophyceae'),
    "Golenkiniopsis": (1.752, 'Chlorococcales', 'Chlorophyceae'),
    "Gomphonema": (0.903, 'Pennales', 'Bacillariophyceae'),
    "Gomphosphaeria": (1.363, 'Chroococcales', 'Cyanobacteria'),
    "Goniochloris": (1.984, 'Mischococcales', 'Xanthophyceae'),
    "Gonium": (0.671, 'Volvocales', 'Chlorophyceae'),
    "Gonyostomum": (-0.07, 'Chattonellales', 'Raphidophyceae'),
    "Gymnodinium": (-1.0, 'Gymnodiniales', 'Dinophyceae'),
    "Gyrosigma": (0.49, 'Pennales', 'Bacillariophyceae'),
    "Isthmochloron": (-2.02, 'Mischococcales', 'Xanthophyceae'),
    "Katodinium": (0.343, 'Gymnodiniales', 'Dinophyceae'),
    "Kephyrion": (-1.14, 'Chromulinales', 'Chrysophyceae'),
    "Keratococcus": (0.579, 'Chlorococcales', 'Chlorophyceae'),
    "Kirchneriella": (1.056, 'Chlorococcales', 'Chlorophyceae'),
    "Koliella": (-0.9, None, 'Klebsormidiophyceae'),
    "Lagerheimia": (1.306, 'Chlorococcales', 'Chlorophyceae'),
    "Lepocinclis": (1.951, 'Euglenales', 'Euglenophyceae'),
    "Limnothrix": (1.441, 'Oscillatoriales', 'Cyanobacteria'),
    "Lyngbya": (1.345, 'Oscillatoriales', 'Cyanobacteria'),
    "Mallomonas": (-0.77, 'Synurales', 'Chrysophyceae'),
    "Melosira": (1.711, 'Centrales', None),
    "Merismopedia": (-1.24, 'Chroococcales', 'Cyanobacteria'),
    "Micractinium": (1.444, 'Chlorococcales', 'Chlorophyceae'),
    "Microcystis": (1.788, 'Chroococcales', 'Cyanobacteria'),
    "Monochrysis": (-1.24, 'Chromulinales', 'Chrysophyceae'),
    "Monomastix": (-0.6, 'Mamiellales', 'Prasinophyceae'),
    "Monomorphina": (2.296, 'Euglenales', 'Euglenophyceae'),
    "Monoraphidium": (-0.74, 'Chlorococcales', 'Chlorophyceae'),
    "Mougeotia": (-0.11, 'Zygnematales', 'Conjugatophyceae'),
    "Navicula": (0.687, 'Pennales', None),
    "Nephrochlamys": (3.322, 'Chlorococcales', 'Chlorophyceae'),
    "Nephrocytium": (-0.65, 'Chlorococcales', 'Chlorophyceae'),
    "Nephroselmis": (1.363, None, 'PolyblepharidalePrasinophyceae'),
    "Nitzschia": (1.674, 'Pennales', 'Bacillariophyceae'),
    "Ochromonas": (-1.35, 'Chromulinales', 'Chrysophyceae'),
    "Oocystis": (-0.41, 'Chlorococcales', 'Chlorophyceae'),
    "Ophiocytium": (0.582, 'Mischococcales', 'Xanthophyceae'),
    "Oscillatoria": (1.575, 'Oscillatoriales', 'Cyanobacteria'),
    "Pandorina": (1.763, 'Volvocales', 'Chlorophyceae'),
    "Paulschulzia": (0.121, 'Tetrasporales', 'Chlorophyceae'),
    "Pediastrum": (1.26, 'Chlorococcales', 'Chlorophyceae'),
    "Peridiniopsis": (-0.06, 'Peridiniales', 'Dinophyceae'),
    "Peridinium": (-0.13, 'Peridiniales', 'Dinophyceae'),
    "Phacotus": (1.134, 'Volvocales', 'Chlorophyceae'),
    "Phacus": (1.912, 'Euglenales', 'Euglenophyceae'),
    "Phormidium": (1.666, 'Oscillatoriales', 'Cyanobacteria'),
    "Pinnularia": (-0.29, 'Pennales', 'Bacillariophyceae'),
    "Plagioselmis": (-0.62, None, 'CryptomonadaleCryptophyceae'),
    "Planctonema": (0.73, 'Ulotrichales', 'Ulvophyceae'),
    "Planktolyngbya": (1.513, 'Oscillatoriales', 'Cyanobacteria'),
    "Planktosphaeria": (0.755, 'Chlorococcales', 'Chlorophyceae'),
    "Planktothrix": (1.416, 'Oscillatoriales', 'Cyanobacteria'),
    "Podle": (3.0, None, 'Phillipsakol.(2013)1/'),
    "Pse": (0.985, 'udogoniochlorisMischococcales', 'Xanthophyceae'),
    "Pseudanabaena": (1.57, 'Oscillatoriales', 'Cyanobacteria'),
    "Pseudodictyosphaeri": (2.87, 'Chlorococcales', 'Chlorophyceae'),
    "Pseudokephyrion": (-1.88, 'Chromulinales', 'Chrysophyceae'),
    "Pseudopedinella": (-1.1, 'Pedinellales', 'Dictyochophycea'),
    "Pseudosphaerocystis": (0.027, 'Tetrasporales', 'Chlorophyceae'),
    "Pseudostaurastrum": (1.095, 'Mischococcales', 'Xanthophyceae'),
    "Pteromonas": (2.053, 'Volvocales', 'Chlorophyceae'),
    "Puncticulata": (-0.16, 'Centrales', 'Bacillariophyceae'),
    "Quadricoccus": (2.519, 'Chlorococcales', 'Chlorophyceae'),
    "Quadrigula": (-0.44, 'Chlorococcales', 'Chlorophyceae'),
    "Radiocystis": (-0.33, 'Chroococcales', 'Cyanobacteria'),
    "Raphidocelis": (0.008, 'Chlorococcales', 'Chlorophyceae'),
    "Rhabdoderma": (-0.45, 'Chroococcales', 'Cyanobacteria'),
    "Rhabdogloea": (-1.91, 'Chroococcales', 'Cyanobacteria'),
    "Rhodomonas": (0.632, None, 'Cryptophyceae'),
    "Romeria": (3.035, 'Oscillatoriales', 'Cyanobacteria'),
    "Scenedesmus": (1.34, 'Chlorococcales', 'Chlorophyceae'),
    "Schroederia": (1.477, 'Chlorococcales', 'Chlorophyceae'),
    "Scourfieldia": (-1.4, 'Scourfieldiales', 'Prasinophyceae'),
    "Siderocelis": (1.787, 'Chlorococcales', 'Chlorophyceae'),
    "Skeletonema": (2.853, 'Centrales', 'Bacillariophyceae'),
    "Snowella": (-0.16, 'Chroococcales', 'Cyanobacteria'),
    "Spermatozopsis": (2.214, 'Volvocales', 'Chlorophyceae'),
    "Sphaerocystis": (-0.28, 'Chlorococcales', 'Chlorophyceae'),
    "Spiniferomonas": (-1.44, 'Chromulinales', 'Chrysophyceae'),
    "Spirulina": (2.954, 'Oscillatoriales', 'Cyanobacteria'),
    "Spondylosium": (-0.48, 'Desmidiales', 'Conjugatophyceae'),
    "Staurastrum": (0.526, 'Desmidiales', 'Conjugatophyceae'),
    "Staurodesmus": (-1.16, 'Desmidiales', None),
    "Stauroneis": (2.554, 'Pennales', 'Bacillariophyceae'),
    "Staurosira": (1.801, 'Pennales', 'Bacillariophyceae'),
    "Stephanodiscus": (1.427, 'Centrales', 'Bacillariophyceae'),
    "Stichococcus": (1.708, 'Prasiolales', None),
    "Stichogloea": (-1.46, 'Chromulinales', 'Chrysophyceae'),
    "Strombomonas": (3.715, 'Euglenales', 'Euglenophyceae'),
    "Surirella": (1.626, 'Pennales', 'Bacillariophyceae'),
    "Syncrypta": (1.195, 'Chromulinales', 'Chrysophyceae'),
    "Synechococcus": (1.167, 'Chroococcales', 'Cyanobacteria'),
    "Synechocystis": (0.92, 'Chroococcales', 'Cyanobacteria'),
    "Synura": (-0.32, 'Synurales', 'Chrysophyceae'),
    "Tabellaria": (-0.79, 'Pennales', 'Bacillariophyceae'),
    "Teilingia": (-0.72, 'Desmidiales', 'Conjugatophyceae'),
    "Tetra": (-0.6, 'ëdriellaMischococcales', 'Xanthophyceae'),
    "Tetrachlorella": (0.832, 'Chlorococcales', 'Chlorophyceae'),
    "Tetraedron": (0.476, 'Chlorococcales', 'Chlorophyceae'),
    "Tetraselmis": (1.015, 'Volvocales', 'Chlorophyceae'),
    "Tetrastrum": (1.1, 'Chlorococcales', 'Chlorophyceae'),
    "Thalassiosira": (3.035, 'Centrales', 'Bacillariophyceae'),
    "Trachelomonas": (1.227, 'Euglenales', 'Euglenophyceae'),
    "Treubaria": (1.054, 'Chlorococcales', 'Chlorophyceae'),
    "Tribonema": (1.124, 'Tribonematales', 'Xanthophyceae'),
    "Trichormus": (1.248, 'Nostocales', 'Cyanobacteria'),
    "Ulnaria": (0.881, 'Pennales', 'Bacillariophyceae'),
    "Ulothrix": (1.43, 'Ulotrichales', 'Ulvophyceae'),
    "Uroglena": (-0.77, 'Chromulinales', 'Chrysophyceae'),
    "Urosolenia": (-0.8, 'Centrales', 'Bacillariophyceae'),
    "Volvox": (1.032, 'Volvocales', 'Chlorophyceae'),
    "Westella": (0.503, 'Chlorococcales', 'Chlorophyceae'),
    "Willea": (-0.94, 'Chlorococcales', 'Chlorophyceae'),
    "Woronichinia": (0.043, 'Chroococcales', 'Cyanobacteria'),
    "Xanthidium": (-0.06, 'Desmidiales', 'Conjugatophyceae'),
}

#: Zalozni hodnoty na urovni radu (7 polozek).
OPTIMA_RADY = {
    "Centrales": 1.063, "Chlorococcales": -0.44, "Cryptomonadales": 1.055,
    "Ochromonadales": -1.77, "Oscillatoriales": 1.6, "Pennales": 0.577,
    "Volvocales": 0.93,
}

#: Zalozni hodnoty na urovni tridy (8 polozek).
OPTIMA_TRIDY = {
    "Chlorophyceae": 1.336, "Chrysophyceae": -1.47, "Cryptophyceae": 1.562,
    "Cyanobacteria": 1.455, "Dinophyceae": -1.32, "Euglenophyceae": 1.689,
    "Picoplankton": -1.48, "Xanthophyceae": 0.998,
}


def zarazeni(rod):
    """Vrati (rad, trida) rodu z Prilohy 2; (None, None) pri neznamem rodu."""
    zaznam = OPTIMA_RODY.get(rod)
    return (zaznam[1], zaznam[2]) if zaznam else (None, None)


def troficke_optimum(rod=None, rad=None, trida=None):
    """Najde troficke optimum taxonu s postupnym zalohovanim.

    Args:
        rod: rodove jmeno (napr. "Microcystis")
        rad: rad (napr. "Chroococcales") - dohleda se, kdyz neni zadan
        trida: trida (napr. "Cyanobacteria") - dtto

    Returns:
        (optimum, uroven) kde uroven je "rod", "rad", "trida" nebo "vychozi"
    """
    if rod and rod in OPTIMA_RODY:
        return OPTIMA_RODY[rod][0], "rod"
    if rod and (rad is None or trida is None):
        vlastni_rad, vlastni_trida = zarazeni(rod)
        rad = rad or vlastni_rad
        trida = trida or vlastni_trida
    if rad and rad in OPTIMA_RADY:
        return OPTIMA_RADY[rad], "rad"
    if trida and trida in OPTIMA_TRIDY:
        return OPTIMA_TRIDY[trida], "trida"
    return 0.0, "vychozi"
