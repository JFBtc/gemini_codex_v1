# core/ui_state.py
import json
import os

SETTINGS_FILE = "ui_settings.json"

def load_settings():
    """Charge les réglages depuis le JSON, ou retourne vide si inexistant."""
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_settings(data):
    """Sauvegarde le dict des réglages dans le JSON."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Erreur sauvegarde settings: {e}")

def get_widget_settings(symbol):
    """
    Récupère les réglages spécifiques. 
    DEFAULTS HARDCODÉS selon votre stratégie.
    """
    data = load_settings()
    
    # --- VOS REGLAGES PAR DEFAUT ---
    default_defaults = {
        "qty": "1", 
        "sl": "10",         # Stop Loss 10 ticks
        "tp": "20", 
        "zone_mode": "Ticks", 
        "zone_val": "10",   # Zone VBP 10 ticks
        "zone_src": "M",    # Source "M" (Medium)
        "rolling": "Vol",   # Fenêtres en Volume
        "be_trig": "8",     # BE après 8 ticks
        "group": "1"        # Grouping par défaut
    }
    
    # Petit ajustement pour NQ qui bouge vite
    if "NQ" in symbol: default_defaults["group"] = "4"
    if "MNQ" in symbol: default_defaults["group"] = "4"
    
    return data.get(symbol, default_defaults)

def update_widget_settings(symbol, qty, sl, tp, z_mode, z_val, grp, z_src, roll_mode, be_trig):
    """Met à jour et sauvegarde TOUS les paramètres"""
    data = load_settings()
    data[symbol] = {
        "qty": str(qty),
        "sl": str(sl),
        "tp": str(tp),
        "zone_mode": str(z_mode),
        "zone_val": str(z_val),
        "group": str(grp),
        "zone_src": str(z_src),
        "rolling": str(roll_mode),
        "be_trig": str(be_trig)
    }
    save_settings(data)