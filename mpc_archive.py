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
OBSERVATORY_CODE = "L47"
OBSERVATORY_NAME = "Osservatorio Astronomico, Piobbico"
# OBSERVATORY_CODE = "D65"
# OBSERVATORY_NAME = "Osservatorio Astronomico G. Beltrame"
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
    """Scarica e analizza una singola MPEC: orbita + osservazioni del tuo osservatorio"""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    text = r.text
    data = {"url": url}

    # ✅ Verifica presenza osservatorio nel blocco 'Observer details'
    obs_block = re.search(r"Observer details:(.*?)(Orbital elements|Ephemeris|Residuals|M\. P\. C\.|$)",
                          text, re.S | re.I)
    if not obs_block or OBSERVATORY_CODE not in obs_block.group(1):
        return None

    # Oggetto
    obj_match = re.search(r"\b(20\d{2}\s+[A-Z]{1,2}\d{0,3})\b", text)
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
            "e": r"\be\s*=?\s*([\d.]+)",
            "i": r"Incl\.\s*([\d.]+)",
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

    # Osservazioni
    obs_section = re.search(r"Observations:(.*?)(Observer details:|Orbital elements:|Residuals:|Ephemeris:|$)",
                            text, re.S | re.I)
    if obs_section:
        obs_text = obs_section.group(1)
        obs_pattern = re.compile(rf"^.*{OBSERVATORY_CODE}.*$", re.M)
        obs_lines = obs_pattern.findall(obs_text)
        if obs_lines:
            data["observations"] = [line.strip() for line in obs_lines]

    # Estrattore dettagli osservatorio
    details_section = re.search(r"Observer details:(.*?)(Orbital elements:|Ephemeris:|Residuals:|$)",
                                text, re.S | re.I)
    if details_section:
        raw = BeautifulSoup(details_section.group(1), "html.parser").get_text(" ", strip=True)
        raw = re.sub(r"\s{2,}", " ", raw)
        if OBSERVATORY_CODE in raw:
            section = re.search(rf"{OBSERVATORY_CODE}\s+(.*?)(?=\s[A-Z0-9]{{3,}}\s|$)", raw)
            if section:
                raw = section.group(1)
        instr = re.search(r"(\d+\.\d+-m\s.*?CMOS|CCD|Cassegrain.*?)(?:\.|$)", raw, re.I)
        observers = re.search(r"Observers?\s+([A-Za-z.,\s]+)", raw)
        measurer = re.search(r"Measurer\s+([A-Za-z.,\s]+)", raw)
        data["instrument_line"] = instr.group(1).strip() if instr else None
        obs_names = []
        if observers: obs_names.append(observers.group(1).strip().rstrip("."))
        if measurer: obs_names.append("Misuratore " + measurer.group(1).strip().rstrip("."))
        data["observer_names"] = "; ".join(obs_names) if obs_names else None

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

    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        moid = float(d.get("MOID", 1.0)) if isinstance(d.get("MOID"), (int, float, str)) else 1.0
        color = 0x3388ff if moid >= 0.05 else (0xFFD700 if moid >= 0.01 else 0xFF5555)
        emoji = "🔵" if moid >= 0.05 else ("🟡" if moid >= 0.01 else "🔴")

        H = d.get("H", "?")
        emoji_H = "🌑"
        if isinstance(H, (int, float)):
            if H < 20: emoji_H = "☀️"
            elif H < 26: emoji_H = "🌕"

        title_text = f"{emoji} MPEC {d.get('mpec_code','?')} — [{d.get('object','?')}]({d.get('url','')})"

        # 🌌 Parametri orbitali
        desc = [
            f"{emoji_H} Magnitudine assoluta (H): {H} — Luminosità intrinseca",
            f"🌀 Eccentricità (e): {d.get('e','?')} — Forma dell’orbita",
            f"📐 Inclinazione (i): {d.get('i','?')}° — Angolo rispetto all’eclittica",
            f"🌍 MOID: {d.get('MOID','?')} AU — Distanza minima orbitale dalla Terra",
            f"📅 Data di emissione: {d.get('issued','?')}",
            f"🔗 [Pagina MPEC]({d.get('url','')})",
            "─────────────────────────"
        ]

        # 👁️ Osservazioni formattate correttamente
        if d.get("observations"):
            lines = []
            for line in d["observations"]:
                line = re.sub(r"\s+", " ", line.strip())
                parts = re.split(r"\s+", line)
                if len(parts) >= 10:
                    code = parts[0]
                    date = f"2025-{parts[2]}-{parts[3]}" if len(parts[2]) == 2 else f"{parts[2]}-{parts[3]}"
                    # Ricostruzione pulita di RA e DEC
                    ra = " ".join(parts[4:7])
                    dec = " ".join(parts[7:10])
                    mag = parts[9] if re.match(r"^\d", parts[9]) else "—"
                    cod = parts[-1]
                    lines.append(
                        f"• **{code} — {date}**\n"
                        f"🧭 RA: {ra}\n"
                        f"📈 DEC: {dec}\n"
                        f"💡 Magnitudine: {mag}\n"
                        f"📄 Codice: {cod}"
                    )
                else:
                    lines.append("• " + line)
            desc.append(f"📷 **Osservazioni ({OBSERVATORY_CODE})**\n" + "\n\n".join(lines))

        # 🔭 Strumento e osservatorio
        if d.get("instrument_line") or d.get("observer_names"):
            desc.append("─────────────────────────")
            if d.get("instrument_line"):
                desc.append(f"🔭 **Strumento:** {d['instrument_line']}")
            desc.append(f"🏛️ **Osservatorio:** {OBSERVATORY_NAME}")
            if d.get("observer_names"):
                desc.append(f"👥 **Osservatori:** {d['observer_names']}")

        # Footer
        desc.append(f"\n🕒 Aggiornato al {now}")

        embeds.append({
            "title": title_text,
            "description": "\n".join(desc),
            "color": color
        })

    # 🪐 Header principale
    header = (
        f"🪐 **Archivio MPEC — {OBSERVATORY_NAME}**\n"
        f"Aggiornato al **{now}**\n"
        f"Totale MPEC con codice **{OBSERVATORY_CODE}: {len(data)}**\n\n"
        f"📊 **Statistiche generali**\n"
        f"• Oggetti con MOID < 0.05 AU: **{close_approaches}**\n"
        f"• Potenzialmente pericolosi (MOID < 0.01 AU): **{hazardous}**\n"
        f"• Magnitudine media (H): **{avg_H}**\n"
        "> ────────────────────────"
    )

    headers = {"Content-Type": "application/json"}
    payload = {"content": header, "embeds": embeds}

    message_id = None
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            message_id = f.read().strip()

    if message_id:
        patch_url = DISCORD_WEBHOOK + f"/messages/{message_id}"
        r = requests.patch(patch_url, json=payload, headers=headers)
        if r.status_code == 200:
            print(f"✅ Messaggio Discord aggiornato (ID {message_id})")
            return
        else:
            print(f"⚠️ Errore aggiornamento messaggio ({r.status_code}), nuovo invio...")

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
