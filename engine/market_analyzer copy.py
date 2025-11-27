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
        """Lance la surveillance continue (Multi-TF + Session Levels)"""
        self.is_running = True
        log.info("📡 [Radar] Démarrage du scan étendu (M5/M15/H1/H4 + Session)...")
        
        # Liste des TFs à surveiller
        timeframes = ["M5", "M15", "H1", "H4"]

        while self.is_running:
            for sym, contract in contracts_map.items():
                # 1. Analyse des Structures (FVG, RSI, EMA, VWAP) sur chaque TF
                for tf in timeframes:
                    await self._scan_timeframe(sym, contract, tf)
                    await asyncio.sleep(0.2) 
                
                # 2. Analyse du Contexte Session (Une fois par cycle)
                await self._scan_session_levels(sym, contract)
            
            # Pause de cycle (15s pour être réactif sans spammer)
            await asyncio.sleep(15) 

    async def _scan_session_levels(self, sym, contract):
        """
        Récupère les niveaux clés de la journée :
        - Open 18:00 (Globex)
        - Open 09:30 (RTH)
        - High / Low du jour (depuis 18h la veille)
        - Gap (Différence Close 17h veille vs Open 18h)
        """
        # On demande 2 jours de bougies 30 mins pour trouver facilement 18h et 9h30
        bars = await self._fetch_history(contract, "2 D", "30 mins")
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 10: return
        
        # Conversion index datetime
        df['date'] = pd.to_datetime(df['date'])
        
        # --- LOGIQUE DE DÉTECTION ---
        levels = {}
        tick_size = self.tick_sizes_map.get(sym, 0.25)
        
        # 1. Identifier le début de la session courante (18:00 la veille ou aujourd'hui)
        
        # Trouver Open 18:00 (Globex)
        mask_18h = df['date'].dt.hour == 18
        # Trouver Open 09:30 (RTH)
        mask_09h30 = (df['date'].dt.hour == 9) & (df['date'].dt.minute == 30)
        
        # Niveaux par défaut
        globex_open = None
        rth_open = None
        prev_close_17h = None
        
        # Globex Open (Dernier 18h trouvé)
        if any(mask_18h):
            globex_row = df[mask_18h].iloc[-1]
            globex_open = globex_row['open']
            
            # Gap : Close de la bougie AVANT 18h
            idx_18h = df.index[df['date'] == globex_row['date']][0]
            if idx_18h > 0:
                prev_close_17h = df.iloc[idx_18h - 1]['close']

        # RTH Open (Dernier 09h30 trouvé)
        if any(mask_09h30):
            rth_row = df[mask_09h30].iloc[-1]
            # On vérifie que ce 09h30 est bien APRES le dernier Globex Open
            if globex_open and rth_row['date'] > df[mask_18h].iloc[-1]['date']:
                rth_open = rth_row['open']
        
        # High / Low Session (Depuis le dernier Globex Open jusqu'à maintenant)
        day_high = df['high'].max()
        day_low = df['low'].min()
        
        if globex_open:
            # Filtrer le DF pour ne garder que ce qui est après le Globex Open
            globex_date = df[mask_18h].iloc[-1]['date']
            session_df = df[df['date'] >= globex_date]
            day_high = session_df['high'].max()
            day_low = session_df['low'].min()

        # Stockage
        levels = {
            "Globex Open": self._snap(globex_open, tick_size) if globex_open else None,
            "RTH Open": self._snap(rth_open, tick_size) if rth_open else None,
            "Prev Close": self._snap(prev_close_17h, tick_size) if prev_close_17h else None,
            "Day High": self._snap(day_high, tick_size),
            "Day Low": self._snap(day_low, tick_size),
            "Gap": 0.0
        }
        
        if levels["Globex Open"] and levels["Prev Close"]:
            levels["Gap"] = levels["Globex Open"] - levels["Prev Close"]

        # Mise à jour atomique
        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym]["SESSION"] = levels
        # log.info(f"📅 [Session {sym}] H:{levels['Day High']} L:{levels['Day Low']} Gap:{levels['Gap']:.2f}")

    async def _scan_timeframe(self, sym, contract, tf):
        params = {
            "M5":  ("1 D", "5 mins"),
            "M15": ("2 D", "15 mins"),
            "H1":  ("5 D", "1 hour"),
            "H4":  ("10 D", "4 hours"),
        }
        duration, bar_size = params.get(tf, ("2 D", "1 hour"))
        
        bars = await self._fetch_history(contract, duration, bar_size)
        if not bars: return

        df = util.df(bars)
        if df is None or len(df) < 20: return

        tick_size = self.tick_sizes_map.get(sym, 0.25)

        # 1. Indicateurs (RSI + EMAs + VWAP SD)
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        current_rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        # EMAs
        ema_9 = df['close'].ewm(span=9, adjust=False).mean().iloc[-1]
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # VWAP & Deviation (SD)
        # Calcul VWAP simplifié sur la fenêtre (pour la déviation locale)
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # Standard Deviation locale (20 périodes) pour estimer l'extension
        df['std'] = df['close'].rolling(window=20).std()
        current_std = df['std'].iloc[-1]
        dist_vwap = df['close'].iloc[-1] - df['vwap'].iloc[-1]
        
        sd_score = 0
        if current_std and current_std != 0:
            sd_score = dist_vwap / current_std # Ex: +2.0 = 2 écarts-types au dessus

        # 2. Structures (FVG + Patterns)
        fvgs = self._detect_smart_fvgs(df, tick_size)
        patterns = self._detect_patterns(df, tick_size)
        
        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym][tf] = {
            "rsi": current_rsi,
            "ema_9": ema_9,
            "ema_20": ema_20,
            "sd_score": sd_score,  # Stockage du Score SD
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

    def _detect_patterns(self, df, tick_size):
        patterns = []
        curr = df.iloc[-1]; prev = df.iloc[-2]
        
        # Inside Bar
        if curr['high'] <= prev['high'] and curr['low'] >= prev['low']:
            patterns.append({"name": "INSIDE BAR ⚠️", "levels": {}})
            
        return patterns

    def _detect_smart_fvgs(self, df, tick_size):
        fvgs = []
        start_index = max(2, len(df)-100) 
        for i in range(start_index, len(df)-1): 
            c1, c3 = df.iloc[i-2], df.iloc[i]
            c2 = df.iloc[i-1]
            pot = None
            if c1['high'] < c3['low']:
                pot = {"type": "BULL", "top": self._snap(c3['low'], tick_size), "bot": self._snap(c1['high'], tick_size), "time": c2['date']}
            elif c1['low'] > c3['high']:
                pot = {"type": "BEAR", "top": self._snap(c1['low'], tick_size), "bot": self._snap(c3['high'], tick_size), "time": c2['date']}
            
            if pot and pot['top'] > pot['bot']:
                is_alive = True
                for j in range(i + 1, len(df)):
                    if (pot['type'] == "BULL" and df.iloc[j]['close'] < pot['bot']) or \
                       (pot['type'] == "BEAR" and df.iloc[j]['close'] > pot['top']):
                        is_alive = False; break
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