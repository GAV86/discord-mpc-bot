import requests
from bs4 import BeautifulSoup
import json
import os
import re
import math
from datetime import datetime
import plotly.graph_objects as go

# ---------------- CONFIG ----------------
MPC_RECENT_URL = "https://www.minorplanetcenter.net/mpec/RecentMPECs.html"
BASE_URL = "https://www.minorplanetcenter.net/mpec/"
ARCHIVE_FILE = "mpc_data.json"
MESSAGE_ID_FILE = "discord_message_id.txt"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# 🔭 Codice e nome dell’osservatorio
OBSERVATORY_CODE = "L47"
OBSERVATORY_NAME = "Osservatorio Astronomico, Piobbico"
ORBIT_FOLDER = "orbits"
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


# ---------------- ORBIT 3D GENERATOR ----------------
def generate_orbit_plot(d):
    """Crea un file HTML Plotly con orbita della Terra e dell'asteroide"""
    if not os.path.exists(ORBIT_FOLDER):
        os.makedirs(ORBIT_FOLDER)

    try:
        a = float(d.get("a", 1.0))  # semiasse maggiore (in AU)
        e = float(d.get("e", 0.0))
        i = math.radians(float(d.get("i", 0.0)))
        Omega = math.radians(float(d.get("Node", 0.0)))
    except Exception:
        return None

    # Calcolo punti orbita
    theta = [t for t in range(0, 361)]
    r = [a * (1 - e**2) / (1 + e * math.cos(math.radians(t))) for t in theta]

    x_orb = [r[j] * math.cos(math.radians(theta[j])) for j in range(len(theta))]
    y_orb = [r[j] * math.sin(math.radians(theta[j])) for j in range(len(theta))]
    z_orb = [0 for _ in theta]

    # Rotazione per inclinazione e nodo ascendente
    x_rot, y_rot, z_rot = [], [], []
    for x, y, z in zip(x_orb, y_orb, z_orb):
        y1 = y * math.cos(i) - z * math.sin(i)
        z1 = y * math.sin(i) + z * math.cos(i)
        x2 = x * math.cos(Omega) - y1 * math.sin(Omega)
        y2 = x * math.sin(Omega) + y1 * math.cos(Omega)
        x_rot.append(x2)
        y_rot.append(y2)
        z_rot.append(z1)

    # Orbita terrestre (1 AU piano XY)
    t_earth = [t for t in range(0, 361)]
    x_e = [math.cos(math.radians(t)) for t in t_earth]
    y_e = [math.sin(math.radians(t)) for t in t_earth]
    z_e = [0 for _ in t_earth]

    fig = go.Figure()

    fig.add_trace(go.Scatter3d(
        x=[0], y=[0], z=[0],
        mode="markers+text",
        text=["☀️ Sole"],
        textposition="top center",
        marker=dict(size=6, color="gold", symbol="circle"),
        name="Sole"
    ))

    fig.add_trace(go.Scatter3d(
        x=x_e, y=y_e, z=z_e,
        mode="lines",
        line=dict(color="blue", width=3),
        name="Orbita Terra"
    ))

    fig.add_trace(go.Scatter3d(
        x=x_rot, y=y_rot, z=z_rot,
        mode="lines",
        line=dict(color="red", width=4),
        name=f"Orbita {d.get('object','Asteroide')}"
    ))

    fig.update_layout(
        scene=dict(
            xaxis_title="X (AU)",
            yaxis_title="Y (AU)",
            zaxis_title="Z (AU)",
            aspectmode="data",
        ),
        title=f"Orbita 3D — {d.get('object','Asteroide')}",
        showlegend=True,
        template="plotly_dark",
    )

    filename = f"{ORBIT_FOLDER}/orbit_{d.get('mpec_code','unknown')}.html"
    fig.write_html(filename, include_plotlyjs="cdn")
    return filename


# ---------------- FETCH MPEC DETAILS ----------------
def fetch_mpec_details(url):
    """Scarica e analizza una singola MPEC"""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    text = r.text
    data = {"url": url}

    obs_block = re.search(r"Observer details:(.*?)(Orbital elements|Ephemeris|Residuals|M\. P\. C\.|$)", text, re.S | re.I)
    if not obs_block or OBSERVATORY_CODE not in obs_block.group(1):
        return None

    obj_match = re.search(r"\b(20\d{2}\s+[A-Z]{1,2}\d{0,3})\b", text)
    if obj_match:
        data["object"] = obj_match.group(1).strip()

    issued = re.search(r"Issued\s+(\d{4}\s+[A-Z][a-z]+\s+\d{1,2})", text)
    if issued:
        data["issued"] = issued.group(1)

    orb = re.search(r"Orbital elements:(.*?)(Residuals|Ephemeris|M\. P\. C\.|$)", text, re.S | re.I)
    if orb:
        block = orb.group(1).replace("\r", " ")
        fields = {
            "a": r"\ba\s*=?\s*([\d.]+)",
            "e": r"\be\s*=?\s*([\d.]+)",
            "i": r"Incl\.\s*([\d.]+)",
            "H": r"\bH\s*=?\s*([\d.]+)",
            "MOID": r"MOID\s*=?\s*([\d.]+)",
            "G": r"\bG\s*=?\s*([\d.]+)",
            "U": r"\bU\s*=?\s*(\d+)",
            "Node": r"Node\s+([\d.]+)"
        }
        for key, pattern in fields.items():
            m = re.search(pattern, block)
            if m:
                data[key] = m.group(1).strip()

    # 🔭 Genera orbita 3D
    orbit_file = generate_orbit_plot(data)
    if orbit_file:
        data["orbit_file"] = orbit_file

    details_section = re.search(r"Observer details:(.*?)(Orbital elements:|Ephemeris:|Residuals:|$)", text, re.S | re.I)
    if details_section:
        raw = BeautifulSoup(details_section.group(1), "html.parser").get_text(" ", strip=True)
        raw = re.sub(r"\s{2,}", " ", raw)
        if OBSERVATORY_CODE in raw:
            section = re.search(rf"{OBSERVATORY_CODE}\s+(.*?)(?=\s[A-Z0-9]{{3,}}\s|$)", raw)
            if section:
                raw = section.group(1)

        instr = re.search(r"(\d+\.\d+-m\s.*?(?:Cassegrain|Reflector|Schmidt).*?(?:CMOS|CCD))", raw, re.I)
        if instr:
            data["instrument_line"] = instr.group(1).strip().rstrip(".")

        observers = re.search(r"Observers?\s+([A-Za-z.,\s]+)", raw)
        measurer = re.search(r"Measurer\s+([A-Za-z.,\s]+)", raw)
        obs_names = []
        if observers:
            obs_names.append(observers.group(1).strip().rstrip("."))
        if measurer:
            obs_names.append("Misuratore " + measurer.group(1).strip().rstrip("."))
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

    for d in sorted(data, key=lambda x: x.get("issued", ""), reverse=True):
        moid = float(d.get("MOID", 1.0))
        color = 0x3388ff if moid >= 0.05 else (0xFFD700 if moid >= 0.01 else 0xFF5555)
        emoji = "🔵" if moid >= 0.05 else ("🟡" if moid >= 0.01 else "🔴")

        H = d.get("H", "?")
        emoji_H = "🌑"
        if isinstance(H, (int, float)):
            if H < 20: emoji_H = "☀️"
            elif H < 26: emoji_H = "🌕"

        title_text = f"{emoji} MPEC {d.get('mpec_code','?')} — [{d.get('object','?')}]({d.get('url','')})"

        desc = [
            f"{emoji_H} Magnitudine assoluta (H): {H}",
            f"🌀 Eccentricità (e): {d.get('e','?')}",
            f"📐 Inclinazione (i): {d.get('i','?')}°",
            f"🌍 MOID: {d.get('MOID','?')} AU",
            f"🧭 Nodo ascendente (Ω): {d.get('Node','?')}°",
            f"📅 Data di emissione: {d.get('issued','?')}",
            "─────────────────────────"
        ]

        if d.get("orbit_file"):
            orbit_url = f"https://gav86.github.io/discord-mpc-bot/{d['orbit_file']}"
            desc.append(f"🪐 [Visualizza orbita 3D]({orbit_url})")

        if d.get("instrument_line"):
            desc.append(f"🔭 Strumento: {d['instrument_line']}")
        desc.append(f"🏛️ Osservatorio: {OBSERVATORY_NAME}")
        if d.get("observer_names"):
            desc.append(f"👥 Osservatori: {d['observer_names']}")
        desc.append(f"🕒 Aggiornato al {now}")

        embeds.append({
            "title": title_text,
            "description": "\n".join(desc),
            "color": color
        })

    payload = {"content": f"🪐 Archivio MPEC — {OBSERVATORY_NAME}\nAggiornato al {now}", "embeds": embeds}
    headers = {"Content-Type": "application/json"}
    requests.post(DISCORD_WEBHOOK, json=payload, headers=headers)


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
            print(f"✅ Aggiunta {m['code']} ({d.get('object','?')}) con orbita 3D")
            new_data.append(d)

    if new_data:
        all_data = existing + new_data
        save_data(all_data)
        send_to_discord(new_data)
        print("✅ Nuove orbite generate e inviate su Discord.")
    else:
        print("ℹ️ Nessuna nuova MPEC trovata.")


if __name__ == "__main__":
    main()
