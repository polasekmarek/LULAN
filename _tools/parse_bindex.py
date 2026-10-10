"""Parser vystupu oficialniho nastroje CHMU pro B-index."""
import re

def nacti(cesta="/sessions/beautiful-zen-pasteur/mnt/uploads/VysledkyBINDEX.txt"):
    txt = open(cesta, encoding="cp1250").read()
    bloky = txt.split("TEST PREDIKCE TAXON")
    zaznamy = []
    for b in bloky[1:]:
        z = {}
        m = re.search(r"PRO LOKALITU:\s*(\S+)", b)
        if not m: continue
        z["lokalita"] = m.group(1)
        m = re.search(r"Datum odběru vzorku MzB:\s*(\S+)", b)
        z["datum"] = m.group(1) if m else None
        m = re.search(r"Počet taxonů:\s*(\d+)", b)
        z["pocet_taxonu"] = int(m.group(1)) if m else None
        m = re.search(r"SEZÓNA:\s*(\w)", b)
        z["sezona"] = m.group(1) if m else None

        def sekce(nazev, dalsi):
            mm = re.search(rf"{nazev}(.*?)(?:{dalsi}|$)", b, re.S)
            return mm.group(1) if mm else ""

        vstup = sekce(r"1\. VSTUPNÍ ABIOTICKÉ PARAMETRY", r"2\. TRANSFORMOVANÝ")
        z["vstup"] = {k: float(v) for k, v in re.findall(r"(\w+):\s*(-?[\d.]+)", vstup)}
        trans = sekce(r"2\. TRANSFORMOVANÝ VEKTOR", r"3\. SKÓRY")
        z["trans"] = {k: float(v) for k, v in re.findall(r"(\w+):\s*(-?[\d.]+)", trans)}
        skory = sekce(r"3\. SKÓRY", r"4\. MAHALANOBIS")
        z["skory"] = [float(v) for v in re.findall(r"Skor\s*\d+:\s*(-?[\d.eE+]+)", skory)]
        vzd = sekce(r"4\. MAHALANOBISSOVY VZDÁLENOSTI", r"5\. PRAVDĚPODOBNOSTI")
        z["vzdalenosti"] = [float(v) for v in re.findall(r"Vzdalenost\(\s*\d+\)\s*=\s*(-?[\d.eE+]+)", vzd)]
        prav = sekce(r"5\. PRAVDĚPODOBNOSTI ZAŘAZENÍ DO TYPU", r"<<<")
        z["pravdepodobnosti"] = [float(v) for v in re.findall(r"postPravd\(\s*\d+\)=(-?[\d.eE+]+)", prav)]
        zaznamy.append(z)
    return zaznamy

if __name__ == "__main__":
    z = nacti()
    print(f"zaznamu: {len(z)}")
    print(f"lokalit: {len({x['lokalita'] for x in z})}")
    from collections import Counter
    print("sezony:", Counter(x["sezona"] for x in z))
    print("\nprvni zaznam:")
    for k, v in z[0].items():
        print(f"  {k}: {v if not isinstance(v,list) else v[:4]}")
