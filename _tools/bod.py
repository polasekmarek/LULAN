"""Popis libovolneho bodu na vodnim toku podle GPS."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
sys.path.insert(0, "src")
from ricni_sit import RicniSit
import abiotic_params as ap

lat, lon = float(sys.argv[1]), float(sys.argv[2])
with RicniSit() as sit:
    d = sit.popis_bodu(lat, lon)
    osa = sit.osa_okolo(lat, lon, ap.USEK_SKLONU, ap.VZORKU_SKLONU)

x, y = ap.pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5514",
                                      always_xy=True).transform(lon, lat)
mnm = ap._vyska_z_dmr(x, y)

mereni = []
for vzdal, bx, by in osa:
    v = ap._vyska_z_dmr(bx, by)
    if v is not None:
        mereni.append((vzdal, v))
sklon = ap._theil_sen(mereni) if len(mereni) >= 3 else None

print(f"  tok              {d['tok']}   (IDVT {d['idvt']})")
print(f"  Strahler         {d['strahler']}")
print(f"  úmoří            {d['umori']} - {d['umori_popis']}")
print(f"  km od pramene    {d['km_od_pramene']}")
print(f"  plocha povodí    {d['plocha_povodi']} km²")
print(f"  ČHP              {d['chp']}")
print(f"  MNM              {mnm if mnm is None else round(mnm, 1)} m")
print(f"  SLOPE            {sklon if sklon is None else round(abs(sklon) * 1000, 2)} ‰"
      f"   ({len(mereni)}/{len(osa)} odečtů)")
print(f"  odsazení od osy  {d['odsazeni']} m")
