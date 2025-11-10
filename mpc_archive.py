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
MESSAGE_ID_FILE = "discord_message_id.txt"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# 🔭 Codice e nome dell’osservatorio
OBSERVATORY_CODE = "D65"
OBSERVATORY_NAME = "Osservatorio Astronomico G. Beltrame"
# ----------------------------------------

EXCLUDED_KEYWORDS = [
    "COMET", "SATELLITE", "DAILY ORBIT UPDATE", "EDITORIAL",
    "CIRCULAR", "RETRACTION", "EPHEMERIS", "CORRIGENDA"
]

# ---------------- FETCH ----------------
def fetch_recent_mpecs():
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
    """Scarica e analizza una singola MPEC: orbita + osservazioni D65"""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    text = r.text
    clean = re.sub(r"\s+", " ", text)
    data = {"url": url}

    # Oggetto
    obj_match = re.search(r"\b(20\d{2}\s+[A-Z]{1,2}\d{0,3})\b", clean)
    if obj_match:
        data["object"] = obj_match.group(1).strip()

    # Data emissione
    issued = re.search(r"Issued\s+(\d{4}\s+[A-Z][a-z]+\s+\d{1,2})", text)
    if issued:
        data["issued"] = issued.group(1)

    # Parametri orbitali
    orb = re.search(r"Orbital elements:(.*?)(Residuals|Ephemeris|M\. P\. C\.|$)", text, re.S | re.I)
    if orb:
        block = orb.group(1).replace("\r", " ")
        fields = {
            "a": r"\ba\s*=?\s*([\d.]+)",
            "e": r"\be\s*=?\s*([\d.]+)",
            "i": r"Incl\.\s*([\d.]+)",
            "Omega": r"Node\s*([\d.]+)",
            "omega": r"Peri\.\s*([\d.]+)",
            "q": r"\bq\s*=?\s*([\d.]+)",
            "P": r"\bP\s*=?\s*([\d.]+)",
            "H": r"\bH\s*=?\s*([\d.]+)",
            "MOID": r"MOID\s*=?\s*([\d.]+)"
        }
        for key, pattern in fields.items():
            m = re.search(pattern, block)
            if m:
                try:
                    data[key] = float(m.group(1))
                except ValueError:
                    data[key] = m.group(1)

    # Osservazioni del tuo osservatorio
    obs_pattern = re.compile(rf"^.*{OBSERVATORY_CODE}.*$", re.M)
    obs_lines = obs_pattern.findall(text)
    if obs_lines:
        data["observations"] = [line.strip() for line in obs_lines]

    # Dettagli strumenti
    obs_details = re.search(
        rf"{OBSERVATORY_CODE}\s+(.*?)\.\s*(?:Observers|Observer|Measurer|$)",
        text, re.S | re.I
    )
    if obs_details:
        data["observatory_details"] = obs_details.group(1).strip()

    # Codice MPEC
    code_match = re.search(r"M\.?P\.?E\.?C\.?\s*(\d{4}-[A-Z]\d{2,3})", text)
    if code_match:
        data["mpec_code"] = code_match.group(1)

    return data


# ---------------- STORAGE ----------------
def load_existing_data():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------- DISCORD ----------------
def send_to_discord(data):
    """Crea embed compatti, ben leggibili e con statistiche"""
    if not DISCORD_WEBHOOK:
        print("❌ Errore: variabile DISCORD_WEBHOOK non trovata.")
        return

    embeds = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 📊 Statistiche globali
    moid_vals = [d.get("MOID", 0) for d in data if isinstance(d.get("MOID"), (int, float))]
    close_approaches = sum(1 for m in moid_vals if m < 0.05)
    hazardous = sum(1 for m in moid_vals if m < 0.01)
    avg_H = round(sum(d.get("H", 0) for d in data if isinstance(d.get("H"), (int, float))) / len(data), 2) if data else 0

    # Crea un embed per ciascun oggetto
    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        moid = d.get("MOID", 1.0)
        try:
            moid = float(moid)
        except:
            moid = 1.0

        # 🎨 Colore dinamico
        color = 0x3388ff  # blu
        if moid < 0.05:
            color = 0xFFD700  # giallo
        if moid < 0.01:
            color = 0xFF5555  # rosso

        # 🌕 Emoji per H
        H = d.get("H", "?")
        emoji_H = "🌑"
        if isinstance(H, (int, float)):
            if H < 20:
                emoji_H = "☀️"
            elif H < 26:
                emoji_H = "🌕"

        desc = [
            f"{emoji_H} **Magnitudine assoluta (H):** {H} — Luminosità intrinseca",
            f"🌀 **Eccentricità (e):** {d.get('e','?')} — Forma dell’orbita",
            f"📐 **Inclinazione (i):** {d.get('i','?')}° — Angolo rispetto all’eclittica",
            f"🌍 **MOID:** {d.get('MOID','?')} AU — Distanza minima orbitale dalla Terra",
            f"📅 **Data di emissione:** {d.get('issued','?')}",
            f"🔗 [Pagina MPEC]({d.get('url','')})"
        ]

        if d.get("observations"):
            obs_preview = "\n".join(d["observations"][:2])
            desc.append(f"\n👁️ **Osservazioni ({OBSERVATORY_CODE}):**\n```{obs_preview}```")

        if d.get("observatory_details"):
            desc.append(f"🔭 **Strumento:** {d['observatory_details']}")

        embeds.append({
            "title": f"MPEC {d.get('mpec_code','?')} — {d.get('object','?')}",
            "description": "\n".join(desc),
            "color": color,
            "footer": {"text": f"{OBSERVATORY_NAME} • Aggiornato al {now}"}
        })

    # Messaggio principale
    header = (
        f"🪐 **Archivio MPEC ({OBSERVATORY_NAME})**\n"
        f"Aggiornato al {now}\n"
        f"Totale MPEC con codice {OBSERVATORY_CODE}: **{len(data)}**\n\n"
        f"📊 **Statistiche generali:**\n"
        f"• Oggetti con MOID < 0.05 AU: {close_approaches}\n"
        f"• Potenzialmente pericolosi (MOID < 0.01 AU): {hazardous}\n"
        f"• Magnitudine media (H): {avg_H}"
    )

    message_id = None
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            message_id = f.read().strip()

    headers = {"Content-Type": "application/json"}
    payload = {"content": header, "embeds": embeds}

    if message_id:
        patch_url = DISCORD_WEBHOOK + f"/messages/{message_id}"
        r = requests.patch(patch_url, json=payload, headers=headers)
        if r.status_code == 200:
            print(f"✅ Messaggio Discord aggiornato (ID {message_id})")
            return
        else:
            print(f"⚠️ Errore aggiornamento messaggio ({r.status_code}), ne invio uno nuovo...")

    r = requests.post(DISCORD_WEBHOOK, json=payload, headers=headers)
    if r.status_code in (200, 204):
        try:
            data_json = r.json()
            if "id" in data_json:
                with open(MESSAGE_ID_FILE, "w") as f:
                    f.write(data_json["id"])
        except:
            pass
        print("✅ Nuovo messaggio Discord creato.")
    else:
        print(f"❌ Errore invio Discord: {r.status_code}")


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
        if d and d.get("observations"):
            print(f"✅ Aggiunta {m['code']} ({d.get('object','?')})")
            new_data.append(d)

    all_data = existing + new_data if new_data else existing
    save_data(all_data)
    send_to_discord(all_data)


if __name__ == "__main__":
    main()
