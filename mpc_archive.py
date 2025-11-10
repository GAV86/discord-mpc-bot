import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

# ---------------- CONFIG ----------------
MPC_RECENT_URL = "https://www.minorplanetcenter.net/mpec/RecentMPECs.html"
BASE_URL = "https://www.minorplanetcenter.net/mpec/"
ARCHIVE_FILE = "mpc_data.json"
TABLE_FILE = "mpc_table.md"
MESSAGE_ID_FILE = "discord_message_id.txt"
# ----------------------------------------

# ⚠️ Filtri per saltare MPEC non rilevanti (solo NEO e asteroidi)
EXCLUDED_KEYWORDS = [
    "COMET", "SATELLITE", "DAILY ORBIT UPDATE", "EDITORIAL", "CIRCULAR",
    "RETRACTION", "EPHEMERIS", "CORRIGENDA"
]

# 🔭 Nome ufficiale dell’osservatorio
OBSERVATORY_NAME = "Osservatorio Astronomico “G. Beltrame”"


# 🛰️ ————————————————————————————————————————————————————————————————
# Funzione per inviare o aggiornare il messaggio su Discord
# ————————————————————————————————————————————————————————————————
def send_to_discord(file_path):
    """Aggiorna o invia la tabella su Discord, mantenendo lo stesso messaggio"""
    webhook_url = os.getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        print("❌ Errore: variabile DISCORD_WEBHOOK non trovata.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if len(content) > 1900:
        content = content[:1900] + "\n*(troncato per lunghezza Discord)*"

    # Controlla se esiste un ID messaggio salvato
    message_id = None
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            message_id = f.read().strip()

    # Se esiste un messaggio precedente → PATCH per aggiornarlo
    if message_id:
        patch_url = webhook_url + f"/messages/{message_id}"
        response = requests.patch(
            patch_url,
            json={"content": content},
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            print(f"✅ Messaggio Discord aggiornato (ID {message_id})")
            return
        else:
            print(f"⚠️ Errore aggiornamento messaggio ({response.status_code}), ne invio uno nuovo...")

    # Se non esiste o fallisce → crea nuovo messaggio
    response = requests.post(webhook_url, json={"content": content}, headers={"Content-Type": "application/json"})
    if response.status_code in (200, 204):
        data = response.json() if response.text else {}
        new_id = data.get("id")
        if new_id:
            with open(MESSAGE_ID_FILE, "w") as f:
                f.write(new_id)
            print(f"✅ Nuovo messaggio creato e ID salvato ({new_id})")
        else:
            print("⚠️ Messaggio creato ma nessun ID restituito dal webhook.")
    else:
        print(f"❌ Errore invio Discord: {response.status_code}")


# 🪐 ————————————————————————————————————————————————————————————————
# Funzioni MPC
# ————————————————————————————————————————————————————————————————
def fetch_recent_mpecs():
    """Scarica la pagina RecentMPECs e restituisce la lista delle MPEC più recenti"""
    r = requests.get(MPC_RECENT_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    pattern = re.compile(r"MPEC\s+(20\d{2}-[A-Z]\d{2,3})\s+\((.*?)\)", re.IGNORECASE)
    found = pattern.findall(text)

    mpecs = []
    for code, title in found:
        # Filtra solo le MPEC con oggetto asteroidale o NEO
        if any(bad in title.upper() for bad in EXCLUDED_KEYWORDS):
            continue

        year = code.split("-")[0]
        short = "K" + year[-2:]  # esempio: 2025 → K25
        link = f"{BASE_URL}{short}/{short}{code[-3:]}.html"

        mpecs.append({
            "code": code,
            "title": title.strip(),
            "url": link
        })

    return mpecs


def fetch_mpec_details(url):
    """Scarica e analizza una singola MPEC"""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None

    if r.status_code != 200:
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
    obs_match = re.findall(r"[A-Z]\d{2,3}\s+([A-Z][A-Za-z .'-]+)", text)
    if obs_match:
        data["observers"] = list(set(o.strip() for o in obs_match))

    # Codice MPEC
    title = re.search(r"M\.?P\.?E\.?C\.?\s*(\d{4}-[A-Z]\d{2,3})", clean)
    if title:
        data["mpec_code"] = title.group(1)

    # Data emissione
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
    """Crea la tabella Markdown per Discord con riepilogo e firma"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(data)

    header = [
        f"**📅 Archivio MPEC aggiornato al {now}**",
        f"Totale MPEC NEO registrate: **{total}**",
        "",
        "| MPEC | Oggetto | H | e | i (°) | MOID (AU) | Scopritori | Data |",
        "|------|----------|---|---|-------|------------|-------------|------|"
    ]

    lines = []
    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        lines.append(
            f"| [{d.get('mpec_code','n/d')}]({d.get('url','')}) "
            f"| {d.get('object','?')} "
            f"| {d.get('H','?')} | {d.get('e','?')} "
            f"| {d.get('i','?')} | {d.get('MOID','?')} "
            f"| {', '.join(d.get('observers', [])[:3])} "
            f"| {d.get('issued','?')} |"
        )

    footer = [
        "",
        "---",
        f"🪐 Generato automaticamente dal **{OBSERVATORY_NAME}**",
        f"🌐 Fonte dati: [Minor Planet Center](https://www.minorplanetcenter.net/mpec/RecentMPECs.html)"
    ]

    full_table = "\n".join(header + lines + footer)
    with open(TABLE_FILE, "w", encoding="utf-8") as f:
        f.write(full_table)

    print(f"📄 Tabella aggiornata salvata in {TABLE_FILE} ({total} voci totali)")


def main():
    print(f"📅 Scansione MPEC da {MPC_RECENT_URL}")
    existing = load_existing_data()
    known_codes = {d.get("mpec_code") for d in existing}
    new_data = []

    mpecs = fetch_recent_mpecs()
    print(f"🔍 Trovate {len(mpecs)} MPEC rilevanti (asteroidi / NEO).")

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

    # ✅ Invia o aggiorna il messaggio su Discord
    send_to_discord(TABLE_FILE)


if __name__ == "__main__":
    main()
