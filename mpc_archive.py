import requests
from bs4 import BeautifulSoup
import json
import os

# ---------------- CONFIG ----------------
OBSERVATORY_CODE = "D65"  # codice MPC del tuo osservatorio
YEARS = [2024, 2025]      # anni da scansionare
BASE_URL = "https://www.minorplanetcenter.net/mpec/{year}/"
ARCHIVE_FILE = "archive.json"
TABLE_FILE = "archive_table.md"
# ----------------------------------------

def fetch_mpec_links(year: int):
    """Scarica tutti i link MPEC per un determinato anno"""
    url = BASE_URL.format(year=year)
    print(f"📅 Scansione MPEC {year} da {url}")
    r = requests.get(url)
    if r.status_code != 200:
        print(f"⚠️ Errore nel recupero MPEC {year}: {r.status_code}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and href.endswith(".html"):
            full_url = f"{url}{href}"
            links.append(full_url)
    print(f"✅ Trovate {len(links)} MPEC nel {year}")
    return links


def fetch_mpec_data(url: str):
    """Scarica il contenuto di una MPEC e verifica se contiene il codice osservatorio"""
    try:
        r = requests.get(url)
        if r.status_code != 200:
            return None
        text = r.text
        if OBSERVATORY_CODE in text:
            soup = BeautifulSoup(text, "html.parser")
            title = soup.find("title").get_text(strip=True) if soup.find("title") else "Senza titolo"
            return {"title": title, "url": url}
    except Exception as e:
        print(f"⚠️ Errore su {url}: {e}")
    return None


def load_archive():
    """Carica l’archivio locale JSON"""
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive(data):
    """Salva l’archivio e aggiorna la tabella Markdown"""
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    with open(TABLE_FILE, "w", encoding="utf-8") as f:
        f.write("| # | Titolo | Link |\n")
        f.write("|---|---------|------|\n")
        for i, entry in enumerate(data, 1):
            f.write(f"| {i} | {entry['title']} | [Apri]({entry['url']}) |\n")

    print(f"✅ Archivio salvato ({len(data)} voci totali).")


def main():
    archive = load_archive()
    known_urls = {item["url"] for item in archive}
    new_entries = []

    for year in YEARS:
        links = fetch_mpec_links(year)
        for link in links:
            if link in known_urls:
                continue
            entry = fetch_mpec_data(link)
            if entry:
                print(f"🛰️ Nuova MPEC trovata: {entry['title']}")
                new_entries.append(entry)

    if new_entries:
        archive.extend(new_entries)
        save_archive(archive)
        print(f"✨ Aggiunte {len(new_entries)} nuove MPEC con codice {OBSERVATORY_CODE}.")
    else:
        print("ℹ️ Nessuna nuova MPEC trovata.")


if __name__ == "__main__":
    main()
