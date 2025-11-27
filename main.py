# main.py
import threading
import asyncio
import logging
import tkinter as tk
from engine.controller import BotController
from ui.dashboard import ModernDashboard
from core.logger import setup_logging

# Intervalle de rafraîchissement écran en millisecondes
# 100ms = 10 FPS (Très fluide pour l'oeil, très léger pour le CPU)
GUI_REFRESH_RATE_MS = 100 

def start_async_loop(loop, controller, logger):
    """Fonction qui tourne dans un thread séparé pour gérer IB"""
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(controller.start())
        loop.run_forever()
    except Exception:
        logger.exception("Erreur dans le thread asynchrone")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # 1. Instancier le contrôleur
    controller = BotController()
    
    # 2. Configurer l'interface
    root = tk.Tk()
    root.title("Robot VBP - Mur de Trading Multi-Actifs")
    root.geometry("1000x800")
    
    dashboard = ModernDashboard(root, controller)
    dashboard.pack(fill="both", expand=True)
    
    # --- MODIFICATION MAJEURE ICI (THROTTLING) ---
    
    # Ancienne méthode (A supprimer dans ton esprit) :
    # On ne lie PLUS directement le tick au refresh.
    # controller.on_ui_update = trigger_refresh  <-- ON ENLÈVE ÇA
    
    # Nouvelle méthode : La boucle de jeu (Game Loop)
    def gui_loop():
        # 1. On met à jour l'interface
        dashboard.refresh()
        # 2. On reprogramme la prochaine mise à jour dans X ms
        root.after(GUI_REFRESH_RATE_MS, gui_loop)
    
    # On lance la boucle
    gui_loop()
    
    # ---------------------------------------------
    
    # 3. Démarrer le moteur IB (Arrière-plan)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=start_async_loop, args=(loop, controller, logger), daemon=True)
    thread.start()
    
    # 4. Lancer l'UI
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if loop.is_running() and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        if thread.is_alive():
            logger.warning("Le thread asynchrone ne s'est pas arrêté proprement avant le timeout.")

if __name__ == "__main__":
    main()