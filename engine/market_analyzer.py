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
        Scan précis des niveaux institutionnels avec bougies 15m
        """
        bars = await self._fetch_history(contract, "3 D", "15 mins")
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 20: return
        
        df['date'] = pd.to_datetime(df['date'])
        
        levels = {}
        tick_size = self.tick_sizes_map.get(sym, 0.25)

        is_0930 = (df['date'].dt.hour == 9)  & (df['date'].dt.minute == 30)
        is_1545 = (df['date'].dt.hour == 15) & (df['date'].dt.minute == 45)
        is_1645 = (df['date'].dt.hour == 16) & (df['date'].dt.minute == 45)
        is_1800 = (df['date'].dt.hour == 18) & (df['date'].dt.minute == 0)

        rth_open_val = None; last_rth_date = None
        if any(is_0930):
            row = df[is_0930].iloc[-1]
            rth_open_val = row['open']; last_rth_date = row['date']
            
        globex_open_val = None; last_globex_date = None
        if any(is_1800):
            row = df[is_1800].iloc[-1]
            globex_open_val = row['open']; last_globex_date = row['date']

        rth_close_val = None
        if any(is_1545):
            row = df[is_1545].iloc[-1]
            rth_close_val = row['close']
            if last_rth_date and row['date'] > last_rth_date:
                if len(df[is_1545]) >= 2: rth_close_val = df[is_1545].iloc[-2]['close']
            
        settlement_val = None
        if any(is_1645):
            row = df[is_1645].iloc[-1]
            settlement_val = row['close']
            if last_globex_date and row['date'] > last_globex_date:
                if len(df[is_1645]) >= 2: settlement_val = df[is_1645].iloc[-2]['close']

        day_high = df['high'].max()
        day_low = df['low'].min()
        if last_globex_date:
            session_df = df[df['date'] >= last_globex_date]
            if not session_df.empty:
                day_high = session_df['high'].max(); day_low = session_df['low'].min()

        levels = {
            "RTH Open": self._snap(rth_open_val, tick_size) if rth_open_val else None,
            "RTH Close": self._snap(rth_close_val, tick_size) if rth_close_val else None,
            "Globex Open": self._snap(globex_open_val, tick_size) if globex_open_val else None,
            "Settlement": self._snap(settlement_val, tick_size) if settlement_val else None,
            "Day High": self._snap(day_high, tick_size),
            "Day Low": self._snap(day_low, tick_size),
        }
        
        if levels["RTH Open"] and levels["RTH Close"]: levels["Gap RTH"] = levels["RTH Open"] - levels["RTH Close"]
        else: levels["Gap RTH"] = 0.0
            
        if levels["Globex Open"] and levels["Settlement"]: levels["Gap Maint"] = levels["Globex Open"] - levels["Settlement"]
        else: levels["Gap Maint"] = 0.0

        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym]["SESSION"] = levels

    async def _scan_timeframe(self, sym, contract, tf):
        params = {
            "M1":  ("14400 S", "1 min"),
            "M5":  ("2 D", "5 mins"),
            "M15": ("5 D", "15 mins"),
            "M30": ("5 D", "30 mins"),
            "H1":  ("10 D", "1 hour"),
            "H4":  ("20 D", "4 hours"),
            "D1":  ("60 D", "1 day"),   
        }
        duration, bar_size = params.get(tf, ("2 D", "1 hour"))
        
        bars = await self._fetch_history(contract, duration, bar_size)
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 30: return

        tick_size = self.tick_sizes_map.get(sym, 0.25)

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        current_rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # STRUCTURES
        fvgs = self._detect_smart_fvgs(df, tick_size)
        
        # PATTERNS INTELLIGENTS (Avec Persistance)
        patterns = self._detect_smart_patterns(df, tick_size)
        
        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym][tf] = {
            "rsi": current_rsi,
            "ema_20": ema_20,
            "fvgs": fvgs,
            "patterns": patterns, 
            "last_close": df['close'].iloc[-1],
            "updated": pd.Timestamp.now()
        }

    def get_radar_snapshot(self, symbol):
        return self.radar_data.get(symbol, {})

    def _snap(self, val, step):
        if step <= 0: return val
        return round(val / step) * step

    def _analyze_candle_pair(self, curr, prev):
        """
        Analyse une paire de bougies (Récente, Référence) pour trouver un pattern.
        Retourne une liste de patterns ou [] si Inside Bar (Neutre).
        """
        patterns = []
        
        # --- A. ANALYSE SWING (High/Low Précédent) ---
        ref_low = prev['low']
        ref_high = prev['high']
        
        # A1. BULLISH SWEEP (Rejection Low)
        # On a cassé le bas, mais on clôture au-dessus
        if curr['low'] < ref_low and curr['close'] > ref_low:
            patterns.append({
                "name": "SWEEP LOW", "side": "BULL", "level_price": ref_low, 
                "desc": f"Sweep {ref_low}"
            })
            
        # A2. BEARISH BREAKOUT (Continuation)
        # On clôture EN-DESSOUS du bas
        elif curr['close'] < ref_low:
            patterns.append({
                "name": "BREAK LOW", "side": "BEAR", "level_price": ref_low, 
                "desc": f"Break {ref_low}"
            })

        # B1. BEARISH SWEEP (Rejection High)
        if curr['high'] > ref_high and curr['close'] < ref_high:
            patterns.append({
                "name": "SWEEP HIGH", "side": "BEAR", "level_price": ref_high, 
                "desc": f"Sweep {ref_high}"
            })
            
        # B2. BULLISH BREAKOUT
        elif curr['close'] > ref_high:
            patterns.append({
                "name": "BREAK HIGH", "side": "BULL", "level_price": ref_high, 
                "desc": f"Break {ref_high}"
            })

        # --- B. ANALYSE ENGULFING (Force Interne) ---
        # Bullish Engulfing
        if curr['close'] > curr['open'] and prev['close'] < prev['open']: 
            if curr['close'] > prev['high'] and curr['open'] < prev['low']:
                patterns.append({
                    "name": "ENGULFING BULL", "side": "BULL", "level_price": curr['low']
                })

        # Bearish Engulfing
        if curr['close'] < curr['open'] and prev['close'] > prev['open']:
            if curr['close'] < prev['low'] and curr['open'] > prev['high']:
                patterns.append({
                    "name": "ENGULFING BEAR", "side": "BEAR", "level_price": curr['high']
                })

        return patterns

    def _detect_smart_patterns(self, df, tick_size):
        """
        Détection avec Mémoire (Persistance) :
        1. Regarde la bougie LIVE vs PREV.
        2. Si aucun pattern (Inside Bar), regarde PREV vs PREV-1.
        3. Remonte jusqu'à 5 bougies pour trouver le dernier état actif.
        """
        if len(df) < 10: return []
        
        # On remonte le temps jusqu'à trouver un pattern significatif
        # i=1 : Live vs Prev
        # i=2 : Prev vs Prev-1 (Bougie fermée)
        # etc.
        
        for i in range(1, 6): # On scanne les 5 dernières opportunités
            curr = df.iloc[-i]
            prev = df.iloc[-(i+1)]
            
            found_patterns = self._analyze_candle_pair(curr, prev)
            
            if found_patterns:
                # Si on trouve un pattern, on le retourne immédiatement.
                # C'est le "Dernier État Connu".
                # On ajoute un suffixe (Live) si c'est la bougie en cours (i=1)
                
                final_pats = []
                for p in found_patterns:
                    if i == 1: 
                        p['name'] += " (Live)"
                    else:
                        # Optionnel : Ajouter (Closed) ou laisser tel quel
                        pass 
                    final_pats.append(p)
                
                return final_pats

        # Si après 5 bougies on est toujours dans un "Inside Bar" géant (très rare), on ne retourne rien.
        return []

    def _detect_smart_fvgs(self, df, tick_size):
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
                    pot = {"type": "BULL", "top": self._snap(c3['low'], tick_size), "bot": self._snap(c1['high'], tick_size), "time": c2['date'], "mitigated": False}
            elif c1['low'] > c3['high']:
                gap_size = c1['low'] - c3['high']
                if gap_size >= (MIN_GAP_TICKS * tick_size):
                    pot = {"type": "BEAR", "top": self._snap(c1['low'], tick_size), "bot": self._snap(c3['high'], tick_size), "time": c2['date'], "mitigated": False}
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