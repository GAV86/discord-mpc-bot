import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

# ---------------- CONFIG ----------------
YEAR = 2025
OBS_CODE = "D65"  # codice osservatorio
BASE_URL = f"https://www.minorplanetcenter.net/mpec/{YEAR}/"
ARCHIVE_FILE = "archive.json"
# ----------------------------------------

def fetch_mpec_links():
    """Scarica la lista di tutte le MPEC dell'anno."""
    index_url = BASE_URL
    r = requests.get(index_url)
    if r.status_code != 200:
        print(f"❌ Errore caricando {index_url}: {r.status_code}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    links = [
        BASE_URL + a["href"]
        for a in soup.find_all("a", href=True)
        if a["href"].endswith(".html")
    ]
    print(f"🔗 Trovate {len(links)} MPEC nel {YEAR}")
    return links

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_archive(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def parse_mpec_page(url):
    """Legge una singola MPEC e verifica se contiene l'osservatorio."""
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        if OBS_CODE not in r.text:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("title").text.strip() if soup.find("title") else "MPEC sconosciuto"
        date = None
        for line in r.text.splitlines():
            if "M.P.E.C." in line:
                date = line.strip()
                break
        return {
            "url": url,
            "title": title,
            "date": date or "Data non trovata",
        }
    except Exception as e:
        print("⚠️ Errore leggendo", url, e)
        return None

def generate_table(entries):
    """Crea una tabella Markdown per Discord."""
    lines = [
        "| 📄 MPEC | 📅 Data | 🔗 Link |",
        "|:--------|:--------|:--------|",
    ]
    for e in sorted(entries, key=lambda x: x["url"], reverse=True):
        lines.append(f"| {e['title']} | {e['date']} | [Apri]({e['url']}) |")
    return "\n".join(lines)

def main():
    archive = load_archive()
    known_urls = {a["url"] for a in archive}
    print(f"📚 Archivio iniziale: {len(archive)} voci")

    links = fetch_mpec_links()
    new_entries = []
    for url in links:
        if url in known_urls:
            continue
        entry = parse_mpec_page(url)
        if entry:
            print(f"✅ Nuova MPEC trovata: {entry['title']}")
            new_entries.append(entry)
            archive.append(entry)

    if new_entries:
        save_archive(archive)
        print(f"💾 Salvate {len(new_entries)} nuove MPEC in {ARCHIVE_FILE}")
    else:
        print("📭 Nessuna nuova MPEC trovata.")

    # genera tabella
    table = generate_table(archive)
    with open("archive_table.md", "w", encoding="utf-8") as f:
        f.write(table)
    print("📄 Tabella aggiornata in archive_table.md")

if __name__ == "__main__":
    main()
