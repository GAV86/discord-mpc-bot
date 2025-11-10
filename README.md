# 🪐 Discord MPC Bot – Minor Planet Center Monitor

Questo bot controlla automaticamente le pubblicazioni MPEC del Minor Planet Center e invia un messaggio su Discord ogni volta che compare una nuova circolare con il codice osservatorio configurato (es. **D65**).

### Funzionalità:
- Controllo automatico due volte al giorno (08:00 e 20:00 UTC)
- Ricerca per codice osservatorio (es. D65)
- Link diretto alle MPEC trovate
- Notifica automatica su Discord

### Struttura:
discord-mpc-bot/
├── mpc_monitor.py
└── .github/workflows/mpc.yml

shell
Copia codice

### Esempio messaggio su Discord:
🪐 Nuove MPEC contenenti l'osservatorio D65:
📅 2025-11-10 08:00 UTC

🔗 https://www.minorplanetcenter.net/mpec/K25/K25A10.html
🔗 https://www.minorplanetcenter.net/mpec/K25/K25A11.html

---

## ✅ DOPO IL SETUP

Una volta pushato tutto su GitHub:
- Il workflow parte **alle 08:00 e 20:00 UTC ogni giorno**
- Puoi testarlo subito cliccando **“Run workflow”** dal tab **Actions**

---

Vuoi che ti aggiunga anche la **memoria locale** (per evitare notifiche doppie sulle stesse MPEC)?  
Così salva gli ID già notificati in un piccolo file `seen.json` e li salta nei run successivi.# discord-mpc-bot
