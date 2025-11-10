import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os

# ---------------- CONFIG ----------------
OBS_CODE = "D65"  # Codice osservatorio
YEARS = [2024, 2025]  # Anni da scansionare
OUTPUT_JSON = "archive.json"
OUTPUT_MD = "archive_table.md"
BASE_URL = "https://www.minorplanetcenter.net/mpec/K{year}/"
# ----------------------------------------

def fetch_mpec_links(year):
    """Scarica tutti i link MPEC per un dato anno."""
    url = BASE_URL.format(year=str(year)[-2:])
    response = requests.get(url)
    if response.status_code != 200:
        print(f"⚠️ Errore nel recupero MPEC {year}: {response.status_code}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    links = [
        ("https://www.minorplanetcenter.net" + a["href"], a.text.strip())
        for a in soup.find_all("a") if a["href"].endswith(".html")
    ]
    print(f"📅 {year}: trovate {len(links)} MPEC")
    return links

def extract_info(link, code):
    """Estrae le info principali da una singola MPEC."""
    try:
        html = requests.get(link).text
        if code not in html:
            return None  # Non contiene D65
        
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title").text.strip()
        lines = [l.strip() for l in soup.text.splitlines() if l.strip()]
        date_line = next((l for l in lines if "M.P.E.C." in l), "")
        date = date_line.split()[-1] if date_line else "n/d"
        
        # Cerca magnitudine e MOID
        mag = "n/d"
        moid = "n/d"
        for l in lines:
            if "H =" in l:
                mag = l.split("H =")[1].split()[0]
            if "MOID" in l:
                moid = l.split("MOID")[1].split()[0]
        
        return {
            "mpec": title,
            "link": link,
            "date": date,
            "mag": mag,
            "moid": moid
        }
    except Exception as e:
        print(f"Errore su {link}: {e}")
        return None

def load_existing():
    """Carica archivio esistente se presente."""
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    """Salva archivio e tabella Markdown."""
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Genera tabella Markdown
    md = (
        "📊 **Archivio osservazioni D65**\n\n"
        "| Data | MPEC | Mag | MOID | Link |\n"
        "|------|------|-----|------|------|\n"
    )
    for item in sorted(data, key=lambda x: x["date"], reverse=True):
        md += f"| {item['date']} | {item['mpec']} | {item['mag']} | {item['moid']} | [Apri]({item['link']}) |\n"
    
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"✅ Archivio salvato ({len(data)} voci).")

def main():
    archive = load_existing()
    seen_links = {a["link"] for a in archive}
    total_found = 0

    for year in YEARS:
        for link, name in fetch_mpec_links(year):
            if link in seen_links:
                continue
            info = extract_info(link, OBS_CODE)
            if info:
                archive.append(info)
                total_found += 1
    
    if total_found:
        print(f"🛰️ Trovate {total_found} nuove MPEC contenenti {OBS_CODE}.")
        save_data(archive)
    else:
        print("ℹ️ Nessuna nuova MPEC trovata.")

if __name__ == "__main__":
    main()
