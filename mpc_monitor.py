import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

# CONFIGURAZIONE
OBS_CODE = "D65"  # <--- Inserisci qui il tuo codice osservatorio
MPEC_URL = "https://www.minorplanetcenter.net/mpec/RecentMPECs.html"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

def fetch_recent_mpecs():
    """Scarica e analizza la pagina con le ultime MPEC"""
    r = requests.get(MPEC_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Trova tutti i link alle MPEC giornaliere
    links = [a["href"] for a in soup.select("a[href*='MPEC']") if a["href"].endswith(".html")]
    return ["https://www.minorplanetcenter.net/mpec/" + l for l in links]

def check_observatory_mentions():
    """Controlla quali MPEC citano il codice osservatorio"""
    matches = []
    for url in fetch_recent_mpecs():
        r = requests.get(url)
        if OBS_CODE in r.text:
            matches.append(url)
    return matches

def send_to_discord(urls):
    if not urls or not WEBHOOK_URL:
        print("Nessuna nuova MPEC trovata.")
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    content = (
        f"🪐 **Nuove MPEC contenenti l'osservatorio {OBS_CODE}:**\n"
        f"📅 {now}\n\n"
        + "\n".join(f"🔗 {u}" for u in urls)
    )

    payload = {"username": "MPC Bot", "content": content}
    r = requests.post(WEBHOOK_URL, json=payload)
    print(f"Inviato su Discord: {r.status_code}")

if __name__ == "__main__":
    found = check_observatory_mentions()
    send_to_discord(found)
