# engine/guardian.py
import asyncio
import logging
import time

log = logging.getLogger("Guardian")

class TradeGuardian:
    """
    Gardien avec Mémoire Locale.
    Gère l'Auto-BE en écoutant les exécutions (indépendant du portefeuille IB).
    """
    def __init__(self, ib_manager, aggregator):
        self.ibm = ib_manager
        self.aggr = aggregator
        self.running = False
        self.configs = {} 
        
        # Mémoire locale : { "MES": {"pos": 1, "avgCost": 6780.0} }
        self._local_positions = {}

    @property
    def ib(self):
        return self.ibm.ib

    async def start(self):
        self.running = True
        log.info("🛡️ Guardian activé : Mode MÉMOIRE LOCALE")
        
        # Abonnement aux exécutions
        self.ib.execDetailsEvent += self._on_execution
        
        while self.running:
            try:
                if self.ib.isConnected():
                    await self._monitor_risk()
            except Exception as e:
                log.error(f"❌ Erreur boucle Guardian : {e}")
            
            await asyncio.sleep(0.1) # Réactif

    def update_config(self, symbol, active, trigger_ticks):
        self.configs[symbol] = {"active": active, "trigger": trigger_ticks, "offset": 0}
        if active:
            # Petit log utile pour confirmer l'activation
            pass 

    def _on_execution(self, trade, fill):
        """
        Mise à jour instantanée de la position locale.
        """
        try:
            sym = trade.contract.symbol
            exec_detail = fill.execution
            
            qty = exec_detail.shares
            if exec_detail.side == 'SLD': 
                qty = -qty
            
            price = exec_detail.avgPrice
            
            current = self._local_positions.get(sym, {"pos": 0, "avgCost": 0.0})
            new_pos_size = current["pos"] + qty
            
            # Mise à jour du prix moyen si on ouvre/renforce
            if abs(new_pos_size) > abs(current["pos"]):
                current["avgCost"] = price
            
            current["pos"] = new_pos_size
            
            # Reset si position fermée
            if new_pos_size == 0:
                current["avgCost"] = 0.0
                
            self._local_positions[sym] = current

        except Exception as e:
            log.error(f"❌ Erreur traitement exécution : {e}")

    def _get_price_tolerant(self, sym):
        return self.aggr.get_last_price(sym)

    async def _monitor_risk(self):
        # On parcourt la mémoire locale
        for sym, data in list(self._local_positions.items()):
            size = data["pos"]
            avg_cost = data["avgCost"]
            
            if size == 0: continue

            # 1. Config
            cfg = self.configs.get(sym)
            if not cfg or not cfg["active"]: continue

            # 2. Prix
            last_price = self._get_price_tolerant(sym)
            if not last_price: continue 
            
            # 3. Cost
            if avg_cost <= 0: continue

            # 4. Calcul PnL
            tick_size = 0.25 
            if size > 0: # LONG
                pnl_ticks = (last_price - avg_cost) / tick_size
                target = avg_cost + (cfg["offset"] * tick_size)
            else: # SHORT
                pnl_ticks = (avg_cost - last_price) / tick_size
                target = avg_cost - (cfg["offset"] * tick_size)
            
            # Log Silencieux (décommenter pour debug)
            # if pnl_ticks > 0:
            #      log.info(f"👀 {sym} Gain: +{pnl_ticks:.1f}")

            # 5. Action
            if pnl_ticks >= cfg["trigger"]:
                await self._move_stop_to_be(sym, size, target)

    async def _move_stop_to_be(self, symbol, position_size, target_price):
        open_trades = self.ib.openTrades()
        stop_trade = None
        
        for t in open_trades:
            if t.contract.symbol != symbol: continue
            if t.order.orderType not in ('STP', 'STP LMT', 'TRAIL'): continue
            
            if position_size > 0 and t.order.action != 'SELL': continue
            if position_size < 0 and t.order.action != 'BUY': continue
            
            stop_trade = t
            break
        
        if not stop_trade:
            return 

        current_stop = stop_trade.order.auxPrice
        target_price = round(target_price / 0.25) * 0.25
        
        needs_update = False
        if position_size > 0:
            if current_stop < target_price - 0.0001: needs_update = True
        else:
            if current_stop > target_price + 0.0001: needs_update = True
                
        if needs_update:
            log.info(f"🛡️ >>> STOP {symbol} <<< {current_stop} -> {target_price} (BE)")
            stop_trade.order.auxPrice = target_price
            self.ib.placeOrder(stop_trade.contract, stop_trade.order)