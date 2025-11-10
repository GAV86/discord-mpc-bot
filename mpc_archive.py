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

# 🔭 Codice e nome dell’osservatorio (attivo)
OBSERVATORY_CODE = "L47"
OBSERVATORY_NAME = "Osservatorio Astronomico, Piobbico"

# 👇 Se vuoi cambiare osservatorio, basta commentare/scommentare:
# OBSERVATORY_CODE = "D65"
# OBSERVATORY_NAME = "Osservatorio Astronomico G. Beltrame"
# ----------------------------------------

EXCLUDED_KEYWORDS = [
    "COMET", "SATELLITE", "DAILY ORBIT UPDATE", "EDITORIAL",
    "CIRCULAR", "RETRACTION", "EPHEMERIS", "CORRIGENDA"
]


# ---------------- FUNZIONI ----------------
def fetch_recent_mpecs():
    """Scarica la pagina RecentMPECs e restituisce l'elenco delle MPEC rilevanti"""
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
    """Estrae i dati di una singola MPEC solo se contiene il codice osservatorio"""
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

    # Estrai le linee di osservazione specifiche dell’osservatorio
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

    payload = {"embeds": [main_embed] + embeds[:9]}  # massimo 10 embed per messaggio
    r = requests.post(DISCORD_WEBHOOK, json=payload)
    if r.status_code in (200, 204):
        print("✅ Messaggio Discord inviato con successo.")
    else:
        print(f"❌ Errore invio Discord: {r.status_code} {r.text}")


def build_embeds(data):
    """Costruisce l'embed principale e quelli individuali"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(data)

    if total == 0:
        return [], {
            "title": f"🪐 Archivio MPEC ({OBSERVATORY_NAME})",
            "description": f"Nessuna MPEC trovata per codice {OBSERVATORY_CODE}.",
            "footer": {"text": f"{OBSERVATORY_NAME} • Aggiornato al {now}"}
        }

    # Helper per convertire numeri in sicurezza
    def safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    moid_values = [safe_float(d.get("MOID")) for d in data if safe_float(d.get("MOID")) is not None]
    h_values = [safe_float(d.get("H")) for d in data if safe_float(d.get("H")) is not None]

    stats = {
        "moid_lt_0_05": sum(1 for m in moid_values if m < 0.05),
        "moid_lt_0_01": sum(1 for m in moid_values if m < 0.01),
        "h_avg": round(sum(h_values) / len(h_values), 2) if h_values else 0.0,
    }

    main_embed = {
        "title": f"🪐 Archivio MPEC ({OBSERVATORY_NAME})",
        "description": f"Aggiornato al {now}\nTotale MPEC con codice {OBSERVATORY_CODE}: **{total}**",
        "color": 0x3498db,
        "fields": [
            {"name": "📊 Statistiche generali",
             "value": f"• Oggetti con MOID < 0.05 AU: **{stats['moid_lt_0_05']}**\n"
                      f"• Potenzialmente pericolosi (MOID < 0.01 AU): **{stats['moid_lt_0_01']}**\n"
                      f"• Magnitudine media (H): **{stats['h_avg']}**",
             "inline": False}
        ],
        "footer": {"text": f"{OBSERVATORY_NAME} • Aggiornato al {now}"}
    }

    embeds = []
    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        desc = (
            f"🌑 **Magnitudine assoluta (H):** {d.get('H','?')} — Luminosità intrinseca\n"
            f"🌀 **Eccentricità (e):** {d.get('e','?')} — Forma dell’orbita\n"
            f"📐 **Inclinazione (i):** {d.get('i','?')}° — Angolo rispetto all’eclittica\n"
            f"🌍 **MOID:** {d.get('MOID','?')} AU — Distanza minima orbitale dalla Terra\n"
            f"📅 **Data di emissione:** {d.get('issued','?')}\n"
            f"[🔗 Apri su Minor Planet Center]({d.get('url','')})"
        )
        obs_block = "\n".join(d.get("observations", [])) or "*Nessuna osservazione registrata*"
        desc += f"\n\n👁️ **Osservazioni ({OBSERVATORY_CODE}):**\n```plaintext\n{obs_block}\n```"
        embeds.append({
            "title": f"🧾 {d.get('mpec_code','?')} — {d.get('object','?')}",
            "description": desc,
            "color": 0x2ecc71
        })
    return embeds, main_embed


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

    all_data = existing + new_data
    save_data(all_data)

    embeds, main_embed = build_embeds(all_data)
    send_embeds_to_discord(main_embed, embeds)


if __name__ == "__main__":
    main()
