# core/sound.py
import threading
import winsound

def play_alert():
    """Joue un son bref dans un thread séparé pour ne pas bloquer l'UI"""
    def _beep():
        try:
            # Fréquence 800Hz, Durée 300ms
            winsound.Beep(800, 300)
        except:
            pass
    
    threading.Thread(target=_beep, daemon=True).start()