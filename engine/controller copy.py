# engine/controller.py
import asyncio
import logging
import math
import tkinter as tk
from ib_insync import Future, Contract, Order, Trade, LimitOrder, StopOrder, MarketOrder

from core.ib_resilient_manager import IBResilientManager
from engine.aggregator import Aggregator
from engine.guardian import TradeGuardian
from engine.auction import AuctionMonitor
from engine.market_analyzer import MarketAnalyzer 
import config

log = logging.getLogger("Controller")

class BotController:
    def __init__(self):
        self.loop = None  # <--- 1. INITIALISATION LOOP
        self.ib_manager = IBResilientManager(
            host=config.IB_HOST, 
            port=config.IB_PORT, 
            base_client_id=config.CLIENT_ID,
            auto_connect=False 
        )
        
        self.ib_manager.on_connected.append(self._on_connection_restored)
        self.ib_manager.on_resume.append(self._on_connection_restored)
        
        self.contracts_map = {}
        self.tick_sizes_map = {}
        
        for cfg in config.TICKERS:
            sym = cfg["symbol"]
            c = Future(
                symbol=sym,
                lastTradeDateOrContractMonth=cfg["expiry"],
                exchange=cfg["exchange"],
                currency=cfg["currency"]
            )
            self.contracts_map[sym] = c
            self.tick_sizes_map[sym] = cfg["tick_size"]
        
        self.ctx = {} 
        self.aggregator = Aggregator(
            ctx=self.ctx,
            autosave_secs=30,
            persist=True,
            tick_size_map=self.tick_sizes_map,
            prefer_mode="auto"
        )

        self.guardian = TradeGuardian(self.ib_manager, self.aggregator)
        self.auction = AuctionMonitor(self.aggregator)
        
        self.analyzer = MarketAnalyzer(self.ib_manager, self.tick_sizes_map)
        
        self.on_ui_update = None
        self._tk_vars = {}

    def get_shared_var(self, symbol, var_name, default_val, context="Session"):
        family = symbol
        if symbol in ["MNQ", "NQ"]: family = "NQ"
        elif symbol in ["MES", "ES"]: family = "ES"
        key = f"{family}_{context}_{var_name}"
        if key not in self._tk_vars:
            self._tk_vars[key] = tk.StringVar(value=str(default_val))
        return self._tk_vars[key]

    def _on_connection_restored(self):
        log.info("🔄 (Controller) Connexion restaurée.")

    async def start(self):
        self.loop = asyncio.get_running_loop() # <--- 2. CAPTURE DE LA BOUCLE ACTIVE
        
        log.info("🚀 Démarrage du Contrôleur Multi-Tickers...")
        await self.ib_manager.start()
        
        log.info("⏳ Attente de la connexion IB...")
        while not self.ib_manager.is_connected():
            await asyncio.sleep(0.5)
        
        log.info("✅ Connexion IB détectée.")
        self._on_connection_restored()

        asyncio.create_task(self.guardian.start())
        log.info("🛡️ Guardian activé.")

        # --- 3. DÉMARRAGE DU RADAR (Scan Continu) ---
        log.info("🧠 Lancement du RADAR de marché (M15/H1/H4)...")
        # On lance la tâche de fond qui va scanner les timeframes en boucle
        asyncio.create_task(self.analyzer.start_radar_loop(self.contracts_map))

        # --- GESTION DES QUOTAS IB (DOM & Ticks) ---
        priority_order = ["MES", "ES", "MNQ", "NQ"]
        depth_slots_remaining = 3 
        
        sorted_items = sorted(
            self.contracts_map.items(),
            key=lambda item: priority_order.index(item[0]) if item[0] in priority_order else 99
        )

        for sym, contract in sorted_items:
            log.info(f"🔍 Validation de {sym}...")
            try:
                details = await self.ib_manager.ib.qualifyContractsAsync(contract)
                if not details:
                    log.error(f"❌ CONTRAT INTROUVABLE : {sym}")
                    continue 
                
                self.ib_manager.subscribe(
                    key=f"Feed_{sym}",
                    contract=contract,
                    genericTickList="233", 
                    snapshot=False
                )

                self.ib_manager.ib.reqTickByTickData(contract, "AllLast", 0, False)
                log.info(f"⚡ TBT (Tick-By-Tick) activé pour {sym}")
                
                if depth_slots_remaining > 0:
                    log.info(f"🌊 DOM (Profondeur) activé pour {sym}")
                    self.ib_manager.ib.reqMktDepth(contract, numRows=20, isSmartDepth=False)
                    depth_slots_remaining -= 1
                else:
                    log.warning(f"⚠️ Quota DOM atteint. {sym} restera en Top-Of-Book.")

            except Exception as e:
                log.error(f"❌ Erreur validation {sym} : {e}")

        def _on_tick_received(ticker):
            try:
                contract = ticker.contract
                if not contract: return
                found_sym = None
                for s, c in self.contracts_map.items():
                    if c.conId == contract.conId:
                        found_sym = s; break
                
                if found_sym:
                    self.aggregator.on_tick(found_sym, ticker)
                    try:
                        last = ticker.last
                        if last and last > 0:
                            if found_sym not in self.auction.extremes:
                                self.auction.sync_with_existing_data(found_sym)
                            self.auction.on_tick(found_sym, last)
                    except: pass

                    if ticker.domBids or ticker.domAsks:
                        bids = [(l.price, l.size) for l in ticker.domBids]
                        asks = [(l.price, l.size) for l in ticker.domAsks]
                        self.aggregator.on_dom_update(found_sym, bids, asks)
                    
                    if self.on_ui_update: self.on_ui_update()

            except Exception as e: pass

        tickers = self.ib_manager.tickers()
        for t in tickers.values():
            t.updateEvent += _on_tick_received
            log.info(f"✅ Flux connecté : {t.contract.localSymbol}")

    def get_aggregator(self): return self.aggregator
    def get_tick_size(self, symbol): return self.tick_sizes_map.get(symbol, 0.25)
    def update_guardian_config(self, symbol, active, trigger): self.guardian.update_config(symbol, active, trigger)
    def get_market_speed(self, symbol): return self.aggregator.get_speed(symbol)
    def get_auction_levels(self, symbol): return self.auction.extremes.get(symbol, {})
    
    # Accès au Radar
    def get_context(self, symbol): return self.analyzer.get_context(symbol)

    def get_trading_markers(self, symbol):
        markers = {}
        if not self.ib_manager.is_connected(): return markers
        contract = self.contracts_map.get(symbol)
        if not contract: return markers
        tick_size = self.get_tick_size(symbol)
        def snap(px): return round(px / tick_size) * tick_size

        try:
            for pos in self.ib_manager.ib.positions():
                is_match = (pos.contract.symbol == symbol) or (pos.contract.conId == contract.conId)
                if is_match and pos.position != 0: markers[snap(pos.avgCost)] = "ENTRY"
        except: pass

        try:
            for t in self.ib_manager.ib.openTrades():
                is_match = (t.contract.symbol == symbol) or (t.contract.conId == contract.conId)
                if is_match and not t.isDone():
                    o = t.order
                    if o.orderType in ('STP', 'TRAIL') and o.auxPrice: markers[snap(o.auxPrice)] = "SL"
                    elif o.orderType == 'LMT' and o.lmtPrice: markers[snap(o.lmtPrice)] = "TP"
                    elif o.orderType == 'STP LMT' and o.auxPrice: markers[snap(o.auxPrice)] = "SL"
        except: pass
        return markers

    def modify_order_price(self, symbol, tag_type, new_price):
        if not self.ib_manager.is_connected(): return
        contract = self.contracts_map.get(symbol)
        if not contract: return
        target_trade = None
        for t in self.ib_manager.ib.openTrades():
            is_match = (t.contract.symbol == symbol) or (t.contract.conId == contract.conId)
            if not is_match or t.isDone(): continue
            o = t.order
            if tag_type == "SL" and o.orderType in ('STP', 'TRAIL'): target_trade = t; break
            elif tag_type == "TP" and o.orderType == 'LMT' and not o.account: target_trade = t; break
        
        if target_trade:
            log.info(f"📝 MODIF {tag_type} {symbol} -> {new_price}")
            o = target_trade.order
            if tag_type == "SL": o.auxPrice = new_price
            else: o.lmtPrice = new_price
            
            # --- FORCE TRANSMIT + SLEEP ---
            o.transmit = True 
            self.ib_manager.ib.placeOrder(contract, o)
            self.ib_manager.ib.sleep(0.1) # Micro-pause pour flush

    def flatten(self, symbol):
        log.warning(f"🚨 FLATTEN {symbol} !")
        contract = self.contracts_map.get(symbol)
        if not contract: return
        ib = self.ib_manager.ib
        for t in ib.openTrades():
            is_match = (t.contract.symbol == symbol) or (t.contract.conId == contract.conId)
            if is_match and not t.isDone(): ib.cancelOrder(t.order)
        current_pos = 0
        try:
            for pos in ib.positions():
                is_match = (pos.contract.symbol == symbol) or (pos.contract.conId == contract.conId)
                if is_match: current_pos = pos.position; break
        except: pass
        if current_pos != 0:
            action = "SELL" if current_pos > 0 else "BUY"
            order = MarketOrder(action, abs(current_pos))
            order.outsideRth = True; order.tif = 'GTC' 
            ib.placeOrder(contract, order)

    def reset_data(self, symbol):
        log.info(f"🧹 RESET {symbol}")
        self.aggregator.reset_session(symbol)

    def place_order(self, symbol: str, action: str, qty: float, sl_ticks: int, tp_ticks: int):
        if not self.ib_manager.is_connected(): return
        contract = self.contracts_map.get(symbol)
        if not contract: return
        tick_size = self.get_tick_size(symbol)
        last_price = self.aggregator.get_last_price(symbol)
        if not last_price: return

        sl_price = last_price - (sl_ticks * tick_size) if action == "BUY" else last_price + (sl_ticks * tick_size)
        tp_price = last_price + (tp_ticks * tick_size) if action == "BUY" else last_price - (tp_ticks * tick_size)
        sl_price = round(sl_price / tick_size) * tick_size
        tp_price = round(tp_price / tick_size) * tick_size

        log.info(f"📤 [{symbol}] {action} {qty} @ MKT | SL:{sl_price} TP:{tp_price}")
        try:
            orders = self.ib_manager.ib.bracketOrder(action, qty, limitPrice=0, takeProfitPrice=tp_price, stopLossPrice=sl_price)
            for o in orders: o.outsideRth = True; o.tif = 'GTC'
            orders[0].orderType = 'MKT' 
            for o in orders: self.ib_manager.ib.placeOrder(contract, o)
        except Exception as e: log.error(f"❌ Erreur envoi ordre {symbol} : {e}")