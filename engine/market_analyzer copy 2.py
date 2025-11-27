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
        
        timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

        while self.is_running:
            for sym, contract in contracts_map.items():
                for tf in timeframes:
                    await self._scan_timeframe(sym, contract, tf)
                    await asyncio.sleep(0.05) 
                
                await self._scan_session_levels(sym, contract)
            
            await asyncio.sleep(10) 

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
        
        # --- LOGIQUE DE DÉTECTION (Basée sur l'heure locale de l'échange, souvent ET) ---
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
            if last_rth_date and row_1545['date'] > last_rth_date:
                if len(df[is_1545]) >= 2:
                    rth_close_val = df[is_1545].iloc[-2]['close']
            
        # 4. FUTURES SETTLEMENT (17:00) -> Close de la bougie 16:45
        settlement_val = None
        if any(is_1645):
            row_1645 = df[is_1645].iloc[-1]
            settlement_val = row_1645['close']
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
        if levels["RTH Open"] and levels["RTH Close"]:
            levels["Gap RTH"] = levels["RTH Open"] - levels["RTH Close"]
        else: levels["Gap RTH"] = 0.0
            
        if levels["Globex Open"] and levels["Settlement"]:
            levels["Gap Maint"] = levels["Globex Open"] - levels["Settlement"]
        else: levels["Gap Maint"] = 0.0

        if sym not in self.radar_data: self.radar_data[sym] = {}
        self.radar_data[sym]["SESSION"] = levels

    async def _scan_timeframe(self, sym, contract, tf):
        # Configuration optimisée des requêtes IB
        # Pour M1/M5, on veut plus d'historique pour trouver les vieux FVGs non comblés
        params = {
            "M1":  ("14400 S", "1 min"), # 4h
            "M5":  ("2 D", "5 mins"),    # 2 Jours (Augmenté pour trouver FVGs)
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

        # 1. Indicateurs
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        current_rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # 2. Structures (FVG + Patterns)
        fvgs = self._detect_smart_fvgs(df, tick_size)
        patterns = self._detect_patterns(df, tick_size)
        
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

    def _detect_patterns(self, df, tick_size):
        """Détection de patterns de bougies et cassures"""
        patterns = []
        if len(df) < 3: return []
        
        # On analyse la dernière bougie CLÔTURÉE (avant-dernière de la liste)
        # La dernière (iloc[-1]) est en cours de formation.
        curr = df.iloc[-1] # En cours (Live)
        prev = df.iloc[-2] # Fermée
        prev2 = df.iloc[-3] # Fermée N-2
        
        # 1. INSIDE BAR (Sur la bougie fermée)
        if prev['high'] <= prev2['high'] and prev['low'] >= prev2['low']:
            patterns.append({"name": "INSIDE BAR", "side": "NEUTRAL"})

        # 2. ENGULFING (Avalement)
        # Bullish : La précédente est rouge, l'actuelle (fermée) est verte et l'englobe
        is_green = prev['close'] > prev['open']
        is_red_prev = prev2['close'] < prev2['open']
        if is_green and is_red_prev:
            if prev['close'] > prev2['open'] and prev['open'] < prev2['close']:
                patterns.append({"name": "ENGULFING BULL", "side": "BULL"})
        
        # Bearish
        is_red = prev['close'] < prev['open']
        is_green_prev = prev2['close'] > prev2['open']
        if is_red and is_green_prev:
            if prev['close'] < prev2['open'] and prev['open'] > prev2['close']:
                patterns.append({"name": "ENGULFING BEAR", "side": "BEAR"})

        # 3. REJECTION (Pinbar / Hammer)
        # Une longue mèche par rapport au corps
        body_size = abs(prev['close'] - prev['open'])
        wick_up = prev['high'] - max(prev['open'], prev['close'])
        wick_dn = min(prev['open'], prev['close']) - prev['low']
        
        # Rejection du Bas (Bullish) -> Longue mèche basse
        if wick_dn > (2.5 * body_size) and wick_dn > wick_up:
            patterns.append({"name": "REJECTION LOW (Hammer)", "side": "BULL"})
            
        # Rejection du Haut (Bearish) -> Longue mèche haute
        if wick_up > (2.5 * body_size) and wick_up > wick_dn:
            patterns.append({"name": "REJECTION HIGH (Shooting Star)", "side": "BEAR"})

        # 4. BREAK OF STRUCTURE (Simple - Cassure des 3 dernières bougies)
        # Break High
        last_3_high = max(prev2['high'], df.iloc[-4]['high'])
        if prev['close'] > last_3_high:
             patterns.append({"name": "BREAK HIGH", "side": "BULL"})
             
        # Break Low
        last_3_low = min(prev2['low'], df.iloc[-4]['low'])
        if prev['close'] < last_3_low:
             patterns.append({"name": "BREAK LOW", "side": "BEAR"})

        return patterns

    def _detect_smart_fvgs(self, df, tick_size):
        """
        Détection FVG améliorée : Scan plus profond + Filtre bruit adapté
        """
        fvgs = []
        if len(df) < 5: return []

        # Filtre : On accepte des gaps plus petits sur M1/M5
        # Sur M1, 1 tick suffit pour être un gap technique
        MIN_GAP_TICKS = 1 
        
        # On scanne BEAUCOUP plus loin pour les petits TF (car 100 bougies = 1h40 en M1)
        # On scanne tout le DF chargé (défini dans _scan_timeframe)
        start_index = 2 

        for i in range(start_index, len(df)-1): 
            c1 = df.iloc[i-2]; c2 = df.iloc[i-1]; c3 = df.iloc[i]
            pot = None; gap_size = 0

            # BULLISH FVG
            if c1['high'] < c3['low']:
                gap_size = c3['low'] - c1['high']
                if gap_size >= (MIN_GAP_TICKS * tick_size):
                    pot = {"type": "BULL", "top": self._snap(c3['low'], tick_size), 
                           "bot": self._snap(c1['high'], tick_size), "time": c2['date'], "mitigated": False}
            # BEARISH FVG
            elif c1['low'] > c3['high']:
                gap_size = c1['low'] - c3['high']
                if gap_size >= (MIN_GAP_TICKS * tick_size):
                    pot = {"type": "BEAR", "top": self._snap(c1['low'], tick_size), 
                           "bot": self._snap(c3['high'], tick_size), "time": c2['date'], "mitigated": False}

            if pot:
                is_alive = True
                # Vérification mitigation sur TOUTES les bougies suivantes
                for j in range(i + 1, len(df)):
                    bar = df.iloc[j]
                    if pot['type'] == "BULL":
                        if bar['low'] < pot['bot']: is_alive = False; break # Invalidé
                        if bar['low'] <= pot['top']: pot['mitigated'] = True # Touché
                    elif pot['type'] == "BEAR":
                        if bar['high'] > pot['top']: is_alive = False; break # Invalidé
                        if bar['high'] >= pot['bot']: pot['mitigated'] = True # Touché
                
                # On garde s'il est vivant (même mitigé, on le garde en mémoire, le filtre d'affichage décidera)
                if is_alive: fvgs.append(pot)
        
        # On retourne les plus récents en premier
        return fvgs[::-1]

    async def _fetch_history(self, contract, duration, bar_size):
        if not self.ib_manager.is_connected(): return None
        try:
            return await self.ib_manager.ib.reqHistoricalDataAsync(
                contract, endDateTime='', durationStr=duration,
                barSizeSetting=bar_size, whatToShow='TRADES', useRTH=False, formatDate=1
            )
        except: return None
    
    async def initialize_symbol(self, s, c): pass 
    async def get_detailed_analysis(self, c, tf): pass
    def get_context(self, s): return {}