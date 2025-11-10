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
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# 🔭 Codice e nome dell’osservatorio
OBSERVATORY_CODE = "L47"
OBSERVATORY_NAME = "Osservatorio Astronomico, Piobbico"
#BSERVATORY_CODE = "D65"//
#OBSERVATORY_NAME = "Osservatorio Astronomico G. Beltrame"//
# ----------------------------------------

EXCLUDED_KEYWORDS = [
    "COMET", "SATELLITE", "DAILY ORBIT UPDATE", "EDITORIAL",
    "CIRCULAR", "RETRACTION", "EPHEMERIS", "CORRIGENDA"
]

# --------------- UTILS -----------------
def fetch_recent_mpecs():
    r = requests.get(MPC_RECENT_URL, timeout=15)
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
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    text = r.text
    if OBSERVATORY_CODE not in text:
        return None

    data = {"url": url}

    obj_match = re.search(r"\b(20\d{2}\s+[A-Z]{1,2}\d{0,3})\b", text)
    if obj_match:
        data["object"] = obj_match.group(1).strip()

    orb_section = re.search(r"Orbital elements.*?(?:(Residuals|Ephemeris|M\. P\. C\.|$))", text, re.S | re.I)
    if orb_section:
        orb = orb_section.group(0).replace("\r", " ")
        def f(rgx):
            m = re.search(rgx, orb)
            return m.group(1).strip() if m else "?"
        data["H"] = f(r"\bH\s*=?\s*([\d.]+)")
        data["e"] = f(r"\be\s*=?\s*([\d.]+)")
        data["i"] = f(r"Incl\.\s*([\d.]+)")
        data["MOID"] = f(r"MOID\s*=?\s*([\d.]+)")

    issued = re.search(r"Issued\s+(\d{4}\s+[A-Z][a-z]+\s+\d{1,2})", text)
    if issued:
        data["issued"] = issued.group(1)

    obs_lines = []
    for line in text.splitlines():
        if OBSERVATORY_CODE in line and re.search(r"\d{4}\s+[A-Z]{1,2}\d{0,3}", line) is None:
            clean = re.sub(r"\s+", " ", line.strip())
            obs_lines.append(clean)
    data["observations"] = obs_lines
    mpec_code = re.search(r"MPEC\s*(\d{4}-[A-Z]\d{2,3})", text)
    if mpec_code:
        data["mpec_code"] = mpec_code.group(1)
    return data


def load_existing_data():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------- DISCORD ----------------
def send_embeds_to_discord(main_embed, embeds):
    """Invia più embed su Discord via webhook"""
    if not DISCORD_WEBHOOK:
        print("❌ Errore: variabile DISCORD_WEBHOOK non trovata.")
        return

    payload = {"embeds": [main_embed] + embeds[:9]}  # max 10 embed
    r = requests.post(DISCORD_WEBHOOK, json=payload)
    if r.status_code in (200, 204):
        print("✅ Messaggio Discord inviato con successo.")
    else:
        print(f"❌ Errore invio Discord: {r.status_code} {r.text}")


def build_embeds(data):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(data)
    if total == 0:
        return [], {
            "title": f"🪐 Archivio MPEC ({OBSERVATORY_NAME})",
            "description": f"Nessuna MPEC trovata per codice {OBSERVATORY_CODE}.",
            "footer": {"text": f"{OBSERVATORY_NAME} • Aggiornato al {now}"}
        }

    # STATISTICHE
    moid_values = [float(d["MOID"]) for d in data if d.get("MOID", "?") not in ("?", "")] or [0]
    h_values = [float(d["H"]) for d in data if d.get("H", "?") not in ("?", "")]
    stats = {
        "moid_lt_0_05": sum(1 for m in moid_values if m < 0.05),
        "moid_lt_0_01": sum(1 for m in moid_values
