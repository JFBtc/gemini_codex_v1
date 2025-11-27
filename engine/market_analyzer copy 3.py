# engine/market_analyzer.py
import asyncio
import logging
import pandas as pd
import numpy as np
from ib_insync import Contract, util

log = logging.getLogger("MarketAnalyzer")

class MarketAnalyzer:
    def __init__(self, ib_manager, tick_sizes_map):
        self.ib_manager = ib_manager
        self.tick_sizes_map = tick_sizes_map
        self.radar_data = {} 
        self.is_running = False

    async def start_radar_loop(self, contracts_map):
        """Lance la surveillance continue (Multi-Scale + Precision Session)"""
        self.is_running = True
        log.info("📡 [Radar] Démarrage du scan multi-timeframe étendu (M1->D1)...")
        
        # Liste COMPLÈTE des TFs à surveiller
        timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

        while self.is_running:
            for sym, contract in contracts_map.items():
                # 1. Analyse des Structures (FVG, RSI, EMA) sur chaque TF
                for tf in timeframes:
                    await self._scan_timeframe(sym, contract, tf)
                    # Petite pause pour fluidité
                    await asyncio.sleep(0.05) 
                
                # 2. Analyse du Contexte Session (Une fois par cycle)
                await self._scan_session_levels(sym, contract)
            
            # Pause de cycle (15s pour respecter le Pacing IB)
            await asyncio.sleep(15) 

    async def _scan_session_levels(self, sym, contract):
        """
        Scan précis des niveaux institutionnels avec bougies 15m :
        - RTH Close (16:00 ET) : Clôture Cash
        - Futures Close (17:00 ET) : Settlement
        - Globex Open (18:00 ET) : Ouverture Overnight
        - RTH Open (09:30 ET) : Ouverture Cash
        """
        # On demande 3 jours de bougies 15 mins pour avoir l'historique précis
        bars = await self._fetch_history(contract, "3 D", "15 mins")
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 20: return
        
        df['date'] = pd.to_datetime(df['date'])
        
        # --- LOGIQUE DE DÉTECTION (Basée sur l'heure locale de l'échange) ---
        levels = {}
        tick_size = self.tick_sizes_map.get(sym, 0.25)

        # Masques horaires précis
        is_0930 = (df['date'].dt.hour == 9)  & (df['date'].dt.minute == 30)
        is_1545 = (df['date'].dt.hour == 15) & (df['date'].dt.minute == 45) # Finie à 16:00
        is_1645 = (df['date'].dt.hour == 16) & (df['date'].dt.minute == 45) # Finie à 17:00
        is_1800 = (df['date'].dt.hour == 18) & (df['date'].dt.minute == 0)

        # 1. RTH OPEN (09:30)
        rth_open_val = None
        last_rth_date = None
        if any(is_0930):
            row = df[is_0930].iloc[-1]
            rth_open_val = row['open']
            last_rth_date = row['date']
            
        # 2. GLOBEX OPEN (18:00)
        globex_open_val = None
        last_globex_date = None
        if any(is_1800):
            row = df[is_1800].iloc[-1]
            globex_open_val = row['open']
            last_globex_date = row['date']

        # 3. RTH CLOSE (16:00) -> Close de la bougie 15:45
        rth_close_val = None
        if any(is_1545):
            row_1545 = df[is_1545].iloc[-1]
            rth_close_val = row_1545['close']
            
            # Si ce 15:45 est POSTÉRIEUR au dernier RTH Open, la session est finie ou en cours de cloture.
            # Pour calculer le Gap RTH du matin, on veut le close de la VEILLE.
            if last_rth_date and row_1545['date'] > last_rth_date:
                if len(df[is_1545]) >= 2:
                    rth_close_val = df[is_1545].iloc[-2]['close']
            
        # 4. FUTURES SETTLEMENT (17:00) -> Close de la bougie 16:45
        settlement_val = None
        if any(is_1645):
            row_1645 = df[is_1645].iloc[-1]
            settlement_val = row_1645['close']
            
            # Idem, on veut le settlement qui précède le Globex Open actuel
            if last_globex_date and row_1645['date'] > last_globex_date:
                if len(df[is_1645]) >= 2:
                    settlement_val = df[is_1645].iloc[-2]['close']

        # 5. HIGH / LOW (Session en cours)
        day_high = df['high'].max()
        day_low = df['low'].min()
        
        if last_globex_date:
            session_df = df[df['date'] >= last_globex_date]
            if not session_df.empty:
                day_high = session_df['high'].max()
                day_low = session_df['low'].min()

        # Stockage
        levels = {
            "RTH Open": self._snap(rth_open_val, tick_size) if rth_open_val else None,
            "RTH Close": self._snap(rth_close_val, tick_size) if rth_close_val else None,
            "Globex Open": self._snap(globex_open_val, tick_size) if globex_open_val else None,
            "Settlement": self._snap(settlement_val, tick_size) if settlement_val else None,
            "Day High": self._snap(day_high, tick_size),
            "Day Low": self._snap(day_low, tick_size),
        }
        
        # Calcul des Gaps
        # Gap RTH : Open 09:30 vs Close 16:00 (Veille)
        if levels["RTH Open"] and levels["RTH Close"]:
            levels["Gap RTH"] = levels["RTH Open"] - levels["RTH Close"]
        else: 
            levels["Gap RTH"] = 0.0
            
        # Gap Maintenance : Open 18:00 vs Close 17:00
        if levels["Globex Open"] and levels["Settlement"]:
            levels["Gap Maint"] = levels["Globex Open"] - levels["Settlement"]
        else:
            levels["Gap Maint"] = 0.0

        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym]["SESSION"] = levels

    async def _scan_timeframe(self, sym, contract, tf):
        # Configuration optimisée des requêtes IB
        params = {
            "M1":  ("14400 S", "1 min"),# 4 Heures en secondes
            "M5":  ("2 D", "5 mins"),   # 2 Jours
            "M15": ("5 D", "15 mins"),
            "M30": ("5 D", "30 mins"),
            "H1":  ("10 D", "1 hour"),
            "H4":  ("20 D", "4 hours"),
            "D1":  ("60 D", "1 day"),   # Long terme (Swing)
        }
        duration, bar_size = params.get(tf, ("2 D", "1 hour"))
        
        bars = await self._fetch_history(contract, duration, bar_size)
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 30: return

        tick_size = self.tick_sizes_map.get(sym, 0.25)

        # 1. Indicateurs (RSI + EMAs)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        current_rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # 2. Structures (FVG + Smart Patterns)
        fvgs = self._detect_smart_fvgs(df, tick_size)
        
        # ICI : Nouvelle détection Patterns avec la logique "LIVE vs PREVIOUS"
        patterns = self._detect_smart_patterns(df, tick_size)
        
        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym][tf] = {
            "rsi": current_rsi,
            "ema_20": ema_20,
            "fvgs": fvgs,
            "patterns": patterns, # Contient {name, side, level_price}
            "last_close": df['close'].iloc[-1],
            "updated": pd.Timestamp.now()
        }

    def get_radar_snapshot(self, symbol):
        return self.radar_data.get(symbol, {})

    def _snap(self, val, step):
        if step <= 0: return val
        return round(val / step) * step

    def _detect_smart_patterns(self, df, tick_size):
        """
        Détection avancée : Break vs Rejection (Sweep) en TEMPS RÉEL
        Compare la bougie LIVE (curr) avec la bougie FERMÉE (prev).
        """
        patterns = []
        if len(df) < 3: return []
        
        # curr = LIVE (bougie en formation)
        # prev = REFERENCE (mur en béton)
        curr = df.iloc[-1]
        prev = df.iloc[-2] 

        # --- A. ANALYSE SWING (High/Low Précédent) ---
        
        # 1. BULLISH SCENARIOS (Bas du range)
        ref_low = prev['low']
        
        # A1. BULLISH SWEEP (Rejection Low)
        # On a cassé le bas (low < ref), MAIS on est revenu au-dessus (close > ref)
        if curr['low'] < ref_low and curr['close'] > ref_low:
            patterns.append({
                "name": "SWEEP LOW (Rejection)", 
                "side": "BULL", 
                "level_price": ref_low, # Le niveau clé est l'ancien bas
                "desc": f"Sweep {ref_low}"
            })
            
        # A2. BEARISH BREAKOUT (Continuation)
        # On est EN-DESSOUS du bas
        elif curr['close'] < ref_low:
            patterns.append({
                "name": "BREAK LOW (Continuation)", 
                "side": "BEAR", 
                "level_price": ref_low, 
                "desc": f"Break {ref_low}"
            })

        # 2. BEARISH SCENARIOS (Haut du range)
        ref_high = prev['high']
        
        # B1. BEARISH SWEEP (Rejection High)
        # On a cassé le haut (high > ref), MAIS on est revenu dessous (close < ref)
        if curr['high'] > ref_high and curr['close'] < ref_high:
            patterns.append({
                "name": "SWEEP HIGH (Rejection)", 
                "side": "BEAR", 
                "level_price": ref_high, 
                "desc": f"Sweep {ref_high}"
            })
            
        # B2. BULLISH BREAKOUT
        # On est AU-DESSUS du haut
        elif curr['close'] > ref_high:
            patterns.append({
                "name": "BREAK HIGH (Continuation)", 
                "side": "BULL", 
                "level_price": ref_high, 
                "desc": f"Break {ref_high}"
            })

        # --- B. ANALYSE ENGULFING (Force Interne) ---
        
        # Bullish Engulfing (La bougie verte LIVE avale la rouge précédente)
        if curr['close'] > curr['open'] and prev['close'] < prev['open']: 
            if curr['close'] > prev['high'] and curr['open'] < prev['low']:
                patterns.append({
                    "name": "ENGULFING BULL", 
                    "side": "BULL", 
                    "level_price": curr['low'], 
                    "desc": "Engulf Zone"
                })

        # Bearish Engulfing
        if curr['close'] < curr['open'] and prev['close'] > prev['open']:
            if curr['close'] < prev['low'] and curr['open'] > prev['high']:
                patterns.append({
                    "name": "ENGULFING BEAR", 
                    "side": "BEAR", 
                    "level_price": curr['high'],
                    "desc": "Engulf Zone"
                })

        return patterns

    def _detect_smart_fvgs(self, df, tick_size):
        """Détection FVG avec filtrage"""
        fvgs = []
        if len(df) < 5: return []
        MIN_GAP_TICKS = 1 
        start_index = max(2, len(df)-100) 
        for i in range(start_index, len(df)-1): 
            c1 = df.iloc[i-2]; c2 = df.iloc[i-1]; c3 = df.iloc[i]
            pot = None; gap_size = 0
            if c1['high'] < c3['low']:
                gap_size = c3['low'] - c1['high']
                if gap_size >= (MIN_GAP_TICKS * tick_size):
                    pot = {"type": "BULL", "top": self._snap(c3['low'], tick_size), 
                           "bot": self._snap(c1['high'], tick_size), "time": c2['date'], "mitigated": False}
            elif c1['low'] > c3['high']:
                gap_size = c1['low'] - c3['high']
                if gap_size >= (MIN_GAP_TICKS * tick_size):
                    pot = {"type": "BEAR", "top": self._snap(c1['low'], tick_size), 
                           "bot": self._snap(c3['high'], tick_size), "time": c2['date'], "mitigated": False}
            if pot:
                is_alive = True
                for j in range(i + 1, len(df)):
                    bar = df.iloc[j]
                    if pot['type'] == "BULL":
                        if bar['low'] < pot['bot']: is_alive = False; break
                        if bar['low'] <= pot['top']: pot['mitigated'] = True
                    elif pot['type'] == "BEAR":
                        if bar['high'] > pot['top']: is_alive = False; break
                        if bar['high'] >= pot['bot']: pot['mitigated'] = True
                if is_alive: fvgs.append(pot)
        return fvgs[::-1]

    async def _fetch_history(self, contract, duration, bar_size):
        if not self.ib_manager.is_connected(): return None
        try:
            return await self.ib_manager.ib.reqHistoricalDataAsync(
                contract, endDateTime='', durationStr=duration,
                barSizeSetting=bar_size, whatToShow='TRADES', useRTH=False, formatDate=1
            )
        except: return None
    
    # Méthodes de compatibilité
    async def initialize_symbol(self, s, c): pass 
    async def get_detailed_analysis(self, c, tf): pass
    def get_context(self, s): return {}