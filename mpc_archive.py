import requests
from bs4 import BeautifulSoup
import json
import os
import re

# ---------------- CONFIG ----------------
MPC_RECENT_URL = "https://www.minorplanetcenter.net/mpec/RecentMPECs.html"
BASE_URL = "https://www.minorplanetcenter.net/mpec/"
ARCHIVE_FILE = "mpc_data.json"
TABLE_FILE = "mpc_table.md"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
# ----------------------------------------

def fetch_recent_mpecs():
    """Scarica la pagina RecentMPECs e restituisce la lista delle MPEC più recenti"""
    r = requests.get(MPC_RECENT_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    pattern = re.compile(r"MPEC\s+(20\d{2}-[A-Z]\d{2,3})")
    found = pattern.findall(text)

    mpecs = []
    for code in found:
        year = code.split("-")[0]
        short = "K" + year[-2:]  # K25 per 2025
        link = f"{BASE_URL}{short}/{short}{code[-3:]}.html"
        mpecs.append({
            "code": code,
            "url": link
        })

    return mpecs

def fetch_mpec_details(url):
    """Scarica e analizza una singola MPEC"""
    r = requests.get(url)
    if r.status_code != 200:
        print(f"⚠️ Errore {r.status_code} per {url}")
        return None

    text = r.text
    clean = re.sub(r"\s+", " ", text)
    data = {}

    # Oggetto principale
    obj_match = re.search(r"([12]\d{3}\s+[A-Z]{1,2}\d{0,3})", clean)
    if obj_match:
        data["object"] = obj_match.group(1)

    # Magnitudine assoluta H
    H_match = re.search(r"H\s+(\d+\.\d+)", clean)
    if H_match:
        data["H"] = float(H_match.group(1))

    # Eccentricità
    e_match = re.search(r"e\s+(\d+\.\d+)", clean)
    if e_match:
        data["e"] = float(e_match.group(1))

    # Inclinazione
    i_match = re.search(r"Incl\.\s+(\d+\.\d+)", clean)
    if i_match:
        data["i"] = float(i_match.group(1))

    # MOID
    moid_match = re.search(r"MOID\s*=\s*([0-9.]+)\s*AU", clean)
    if moid_match:
        data["MOID"] = float(moid_match.group(1))

    # Osservatori
    obs_match = re.findall(r"([A-Z]\d{2,3})\s+([A-Z][A-Za-z .'-]+)", text)
    if obs_match:
        data["observers"] = list(set(o[1].strip() for o in obs_match))

    # Titolo / intestazione
    title = re.search(r"M\.?P\.?E\.?C\.?\s*(\d{4}-[A-Z]\d{2,3})", clean)
    if title:
        data["mpec_code"] = title.group(1)

    # Epoch (data)
    epoch = re.search(r"Issued\s+(\d{4}\s+[A-Z][a-z]+\s+\d{1,2})", clean)
    if epoch:
        data["issued"] = epoch.group(1)

    data["url"] = url
    return data

def load_existing_data():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def generate_table(data):
    """Crea la tabella Markdown per Discord"""
    lines = [
        "| MPEC | Oggetto | H | e | i (°) | MOID (AU) | Scopritori | Data |",
        "|------|----------|---|---|-------|------------|-------------|------|"
    ]
    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        lines.append(
            f"| [{d.get('mpec_code','n/d')}]({d.get('url','')}) "
            f"| {d.get('object','?')} "
            f"| {d.get('H','?')} | {d.get('e','?')} "
            f"| {d.get('i','?')} | {d.get('MOID','?')} "
            f"| {', '.join(d.get('observers', [])[:3])} "
            f"| {d.get('issued','?')} |"
        )
    with open(TABLE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"📄 Tabella aggiornata salvata in {TABLE_FILE}")

def main():
    print(f"📅 Scansione MPEC da {MPC_RECENT_URL}")
    existing = load_existing_data()
    known_codes = {d.get("mpec_code") for d in existing}
    new_data = []

    mpecs = fetch_recent_mpecs()
    print(f"🔍 Trovate {len(mpecs)} MPEC nella pagina recente.")

    for m in mpecs:
        code = m["code"]
        if code in known_codes:
            continue
        details = fetch_mpec_details(m["url"])
        if details:
            print(f"✅ Aggiunta {code} ({details.get('object','?')})")
            new_data.append(details)

    if new_data:
        all_data = existing + new_data
        save_data(all_data)
        generate_table(all_data)
        print(f"📈 Archivio aggiornato: {len(all_data)} voci totali.")
    else:
        print("ℹ️ Nessuna nuova MPEC trovata.")
        generate_table(existing)

if __name__ == "__main__":
    main()
