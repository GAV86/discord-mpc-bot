import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

# ==========================
# CONFIG
# ==========================
OBSERVATORY_CODE = "D65"  # Codice MPC del tuo osservatorio
YEARS = ["K24", "K25"]    # Anni da scansionare (K24=2024, K25=2025)
BASE_URL = "https://www.minorplanetcenter.net/mpec"
CACHE_FILE = "mpc_cache.json"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")  # webhook segreto GitHub
TABLE_FILE = "mpc_table.md"

# ==========================
# FUNZIONI
# ==========================

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def fetch_mpec_list(year_code):
    """Ottiene l'elenco delle MPEC per l'anno dato (es: K25)."""
    url = f"{BASE_URL}/{year_code}/"
    print(f"📅 Scansione MPEC {year_code} da {url}")
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            print(f"⚠️ Errore nel recupero MPEC {year_code}: {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".html")]
        return [f"{url}{link}" for link in links]
    except Exception as e:
        print(f"⚠️ Errore durante la scansione {year_code}: {e}")
        return []

def parse_mpec_page(url):
    """Analizza una singola pagina MPEC e restituisce dati se contiene il codice osservatorio."""
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        text = r.text
        if OBSERVATORY_CODE not in text:
            return None

        soup = BeautifulSoup(text, "html.parser")
        title = soup.find("title").text.strip() if soup.find("title") else url.split("/")[-1]
        lines = text.splitlines()

        # Cerca designazione e info base
        designation = ""
        h_mag = ""
        moid = ""
        orbit_type = ""
        for line in lines:
            if "Designation:" in line:
                designation = line.split(":")[-1].strip()
            if "H =" in line:
                h_mag = line.split("H =")[-1].split()[0]
            if "MOID" in line:
                moid = line.split("MOID")[-1].split()[0]
            if "Orbit type" in line or "Orbit class" in line:
                orbit_type = line.split(":")[-1].strip()

        # fallback se non trovate
        designation = designation or title.replace("MPEC", "").strip()

        return {
            "designation": designation,
            "title": title,
            "url": url,
            "h_mag": h_mag or "n/d",
            "moid": moid or "n/d",
            "orbit_type": orbit_type or "n/d",
            "date_found": datetime.utcnow().strftime("%Y-%m-%d")
        }
    except Exception as e:
        print(f"⚠️ Errore parsing {url}: {e}")
        return None

def build_table(data_dict):
    """Genera una tabella Markdown con tutti i NEO trovati."""
    header = "| Designazione | Data | Magnitudo H | MOID | Tipo Orbita | Link MPEC |\n"
    header += "|--------------|------|-------------|------|--------------|-----------|\n"
    rows = []
    for k, d in sorted(data_dict.items()):
        rows.append(
            f"| {d['designation']} | {d['date_found']} | {d['h_mag']} | {d['moid']} | {d['orbit_type']} | [Apri]({d['url']}) |"
        )
    return header + "\n".join(rows)

def send_to_discord(message, title="🪐 Aggiornamento archivio MPEC"):
    if not DISCORD_WEBHOOK:
        print("❌ Nessun webhook Discord trovato.")
        return
    payload = {
        "username": "MPC Bot",
        "embeds": [{
            "title": title,
            "description": message,
            "color": 10181046
        }]
    }
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload)
        print(f"✅ Inviato su Discord ({r.status_code})")
    except Exception as e:
        print("⚠️ Errore invio Discord:", e)

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    cache = load_cache()
    new_entries = {}

    for year in YEARS:
        links = fetch_mpec_list(year)
        for link in links:
            if link in cache:
                continue
            parsed = parse_mpec_page(link)
            if parsed:
                cache[link] = parsed
                new_entries[link] = parsed

    save_cache(cache)

    if new_entries:
        print(f"🆕 Trovate {len(new_entries)} nuove MPEC con codice {OBSERVATORY_CODE}")
        msg = "\n".join(
            [f"🔭 **{v['designation']}** – {v['orbit_type']}  (H={v['h_mag']}, MOID={v['moid']})\n🔗 {v['url']}" for v in new_entries.values()]
        )
        send_to_discord(msg, "🆕 Nuove MPEC rilevate!")
    else:
        print("ℹ️ Nessuna nuova MPEC trovata.")

    # Aggiorna tabella
    table = build_table(cache)
    with open(TABLE_FILE, "w", encoding="utf-8") as f:
        f.write(table)
    print("📄 Tabella aggiornata salvata in", TABLE_FILE)
