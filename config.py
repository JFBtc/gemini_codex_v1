# config.py
# Configuration des Paires pour le Dual-DOM

# Paramètres de connexion IB
IB_HOST = "127.0.0.1"
IB_PORT = 7497
CLIENT_ID = 99

# Définition des Paires (Gauche, Droite)
# Le robot affichera une fenêtre par paire.
PAIRS = [
    {
        "left":  {"symbol": "MNQ", "expiry": "202512", "exchange": "CME", "currency": "USD", "tick_size": 0.25},
        "right": {"symbol": "NQ",  "expiry": "202512", "exchange": "CME", "currency": "USD", "tick_size": 0.25}
    },
    {
        "left":  {"symbol": "MES", "expiry": "202512", "exchange": "CME", "currency": "USD", "tick_size": 0.25},
        "right": {"symbol": "ES",  "expiry": "202512", "exchange": "CME", "currency": "USD", "tick_size": 0.25}
    }
]

# Nous générons la liste plate TICKERS pour le controller
TICKERS = []
for p in PAIRS:
    TICKERS.append(p["left"])
    TICKERS.append(p["right"])

# Paramètres graphiques
ROW_HEIGHT = 20
MAX_ROWS = 120

# config.py (Ajout à la fin)

# --- STRATÉGIES PRÉDÉFINIES (PRESETS) ---
STRATEGIES = {
    "Scalp":   {"qty": 1, "sl": 10, "tp": 15, "be_active": True,  "be_trig": 4},
    "Sniper":  {"qty": 1, "sl": 6,  "tp": 20, "be_active": True,  "be_trig": 3},
    "Day":     {"qty": 1, "sl": 20, "tp": 60, "be_active": False, "be_trig": 10},
    "Runner":  {"qty": 1, "sl": 12, "tp": 40, "be_active": True,  "be_trig": 8},
}