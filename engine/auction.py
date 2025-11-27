# engine/auction.py
import logging

log = logging.getLogger("Auction")

class AuctionMonitor:
    """
    Surveille les Plus Hauts / Plus Bas de la session pour l'affichage UI.
    NE DÉCLENCHE PLUS DE RESET (Mode Rolling pur).
    """
    def __init__(self, aggregator):
        self.aggr = aggregator
        # Stockage des extrêmes : { "MNQ": {"high": 18500.0, "low": 18400.0}, ... }
        self.extremes = {}

    def sync_with_existing_data(self, symbol):
        """Récupère les H/L historiques au démarrage"""
        # On regarde dans le VBP Session de l'agrégateur
        vbp = self.aggr.volume_by_price.get(symbol, {})
        if not vbp: return
        
        prices = list(vbp.keys())
        if not prices: return
        
        self.extremes[symbol] = {
            "high": max(prices),
            "low": min(prices)
        }

    def on_tick(self, symbol, price):
        if not price: return
        
        # Initialisation
        if symbol not in self.extremes:
            self.sync_with_existing_data(symbol)
            if symbol not in self.extremes:
                self.extremes[symbol] = {"high": price, "low": price}
                return

        current_high = self.extremes[symbol]["high"]
        current_low = self.extremes[symbol]["low"]

        # 1. Nouveau Plus Haut
        if price > current_high:
            self.extremes[symbol]["high"] = price
            # ON NE RESET PLUS RIEN ! On note juste le nouveau record.
            # log.info(f"📈 New HIGH [{symbol}] @ {price:.2f}")
            
        # 2. Nouveau Plus Bas
        elif price < current_low:
            self.extremes[symbol]["low"] = price
            # log.info(f"📉 New LOW [{symbol}] @ {price:.2f}")

    def _trigger_reset(self, symbol, side, price):
        # Désactivé pour compatibilité avec le mode Rolling
        pass