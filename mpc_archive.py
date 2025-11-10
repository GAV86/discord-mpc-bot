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
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# 🔭 Codice e nome dell’osservatorio
OBSERVATORY_CODE = "D65"
OBSERVATORY_NAME = "Osservatorio Astronomico “G. Beltrame”"
# ----------------------------------------

# Parole da escludere (non NEO)
EXCLUDED_KEYWORDS = [
    "COMET", "SATELLITE", "DAILY ORBIT UPDATE", "EDITORIAL",
    "CIRCULAR", "RETRACTION", "EPHEMERIS", "CORRIGENDA"
]


# ---------------- FUNZIONI ----------------

def send_to_discord(file_path):
    """Aggiorna o invia la tabella su Discord, mantenendo lo stesso messaggio"""
    if not DISCORD_WEBHOOK:
        print("❌ Errore: variabile DISCORD_WEBHOOK non trovata.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if len(content) > 1900:
        content = content[:1900] + "\n*(troncato per lunghezza Discord)*"

    message_id = None
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            message_id = f.read().strip()

    headers = {"Content-Type": "application/json"}

    if message_id:
        patch_url = DISCORD_WEBHOOK + f"/messages/{message_id}"
        r = requests.patch(patch_url, json={"content": content}, headers=headers)
        if r.status_code == 200:
            print(f"✅ Messaggio Discord aggiornato (ID {message_id})")
            return
        else:
            print(f"⚠️ Errore aggiornamento messaggio ({r.status_code}), ne invio uno nuovo...")

    r = requests.post(DISCORD_WEBHOOK, json={"content": content}, headers=headers)
    if r.status_code in (200, 204):
        try:
            data = r.json()
            if "id" in data:
                with open(MESSAGE_ID_FILE, "w") as f:
                    f.write(data["id"])
        except Exception:
            pass
        print("✅ Nuovo messaggio Discord creato.")
    else:
        print(f"❌ Errore invio Discord: {r.status_code}")


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
        if any(bad in title.upper() for bad in EXCLUDED_KEYWORDS):
            continue
        year = code.split("-")[0]
        short = "K" + year[-2:]
        link = f"{BASE_URL}{short}/{short}{code[-3:]}.html"
        mpecs.append({"code": code, "title": title.strip(), "url": link})

    return mpecs


def fetch_mpec_details(url):
    """Scarica e analizza una singola MPEC (solo se contiene D65 in 'Observer details')"""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    text = r.text

    # cerca la sezione 'Observer details'
    obs_block = re.search(r"Observer details:(.*?)(Orbital elements|Ephemeris|Residuals|M\. P\. C\.|$)", text, re.S | re.I)
    if not obs_block or OBSERVATORY_CODE not in obs_block.group(1):
        return None

    data = {"url": url}

    obj_match = re.search(r"\b(20\d{2}\s+[A-Z]{1,2}\d{0,3})\b", text)
    if obj_match:
        data["object"] = obj_match.group(1).strip()

    orb_section = re.search(r"Orbital elements.*?(?:(Residuals|Ephemeris|M\. P\. C\.|$))", text, re.S | re.I)
    if orb_section:
        orb = orb_section.group(0).replace("\r", " ")
        H = re.search(r"\bH\s*=?\s*([\d.]+)", orb)
        e = re.search(r"\be\s*=?\s*([\d.]+)", orb)
        i = re.search(r"Incl\.\s*([\d.]+)", orb)
        moid = re.search(r"MOID\s*=?\s*([\d.]+)", orb)
        if H: data["H"] = float(H.group(1))
        if e: data["e"] = float(e.group(1))
        if i: data["i"] = float(i.group(1))
        if moid: data["MOID"] = float(moid.group(1))

    issued = re.search(r"Issued\s+(\d{4}\s+[A-Z][a-z]+\s+\d{1,2})", text)
    if issued:
        data["issued"] = issued.group(1)

    data["observers"] = [OBSERVATORY_CODE]
    title = re.search(r"M\.?P\.?E\.?C\.?\s*(\d{4}-[A-Z]\d{2,3})", text)
    if title:
        data["mpec_code"] = title.group(1)
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
    """Crea una versione compatta e leggibile per Discord"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(data)

    lines = [
        f"**📅 Archivio MPEC (solo {OBSERVATORY_NAME}) aggiornato al {now}**",
        f"Totale MPEC con codice {OBSERVATORY_CODE}: **{total}**",
        ""
    ]

    if total == 0:
        lines.append("Nessuna MPEC trovata per questo osservatorio.")
    else:
        for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
            lines.append(
                f"📄 **[{d.get('mpec_code','?')}]** — {d.get('object','?')}\n"
                f"• 💡 H={d.get('H','?')} e={d.get('e','?')} i={d.get('i','?')}° MOID={d.get('MOID','?')} AU\n"
                f"• 📅 {d.get('issued','?')}\n"
                f"<{d.get('url','')}>"
            )

    lines += [
        "",
        "---",
        f"🪐 Generato automaticamente dal **{OBSERVATORY_NAME}**",
        f"🌐 Fonte dati: [Minor Planet Center](https://www.minorplanetcenter.net/mpec/RecentMPECs.html)"
    ]

    content = "\n".join(lines)
    with open(TABLE_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📄 Tabella aggiornata salvata in {TABLE_FILE} ({total} voci totali)")


# ---------------- MAIN ----------------
def main():
    print(f"📅 Scansione MPEC da {MPC_RECENT_URL}")
    existing = load_existing_data()
    known = {d.get("mpec_code") for d in existing}
    new_data = []

    mpecs = fetch_recent_mpecs()
    print(f"🔍 Trovate {len(mpecs)} MPEC totali, filtraggio per codice {OBSERVATORY_CODE}...")

    for m in mpecs:
        if m["code"] in known:
            continue
        d = fetch_mpec_details(m["url"])
        if d:
            print(f"✅ Aggiunta {m['code']} ({d.get('object','?')})")
            new_data.append(d)

    if new_data:
        all_data = existing + new_data
        save_data(all_data)
        generate_table(all_data)
        print(f"📈 Archivio aggiornato: {len(all_data)} voci totali.")
    else:
        print("ℹ️ Nessuna nuova MPEC trovata per D65.")
        generate_table(existing)

    send_to_discord(TABLE_FILE)


if __name__ == "__main__":
    main()
