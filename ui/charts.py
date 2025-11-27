# ui/charts.py
import tkinter as tk
from tkinter import ttk

# --- PALETTE GRAPHIQUE ---
COLOR_UP    = "#2e7d32"     # Vert (Bougie Haussière)
COLOR_DOWN  = "#c62828"     # Rouge (Bougie Baissière)
COLOR_WICK  = "#546e7a"     # Gris Bleu (Mèches)
COLOR_BG    = "#ffffff"     # Fond Blanc
COLOR_GRID  = "#eceff1"     # Grille très légère
COLOR_TXT   = "#37474f"     # Texte Principal
COLOR_MUTED = "#90a4ae"     # Texte Secondaire

# --- PALETTE ANALYSE (FVG & NIVEAUX) ---
# Couleurs beaucoup plus foncées pour visibilité optimale
COLOR_FVG_BULL = "#81c784"  # Vert Moyen (Support)
COLOR_FVG_BEAR = "#e57373"  # Rouge Moyen (Résistance)
COLOR_SESSION  = "#0288d1"  # Bleu (High/Low/Open)
COLOR_GAP      = "#ffa726"  # Orange (Gap)

class MiniChartWidget(tk.Frame):
    """
    Widget Graphique Canvas (Non-Bloquant)
    Affiche: Bougies + FVG + Niveaux Session
    Scaling: Priorité aux bougies visibles.
    """
    def __init__(self, parent, controller, symbol, width=300, height=250):
        super().__init__(parent, bg=COLOR_BG, bd=1, relief="solid")
        self.controller = controller
        self.sym = symbol
        self.aggr = controller.get_aggregator()
        
        self.pack_propagate(False)
        self.config(width=width, height=height)
        
        # Ajout des TFs en secondes pour le trigger
        self.mode_var = tk.StringVar(value="5m")
        self._setup_ui()

    def _setup_ui(self):
        # Header
        f_tool = tk.Frame(self, bg=COLOR_BG)
        f_tool.pack(fill="x", pady=2, padx=2)
        
        lbl = tk.Label(f_tool, text=f"{self.sym}", bg=COLOR_BG, fg=COLOR_TXT, font=("Segoe UI", 9, "bold"))
        lbl.pack(side="left", padx=5)
        
        # Sélecteur Timeframe étendu
        cb = ttk.Combobox(f_tool, textvariable=self.mode_var, 
                          values=["5s", "15s", "30s", "1m", "5m", "15m", "1h"], 
                          width=5, state="readonly")
        cb.pack(side="right", padx=5)
        cb.bind("<<ComboboxSelected>>", lambda e: self.update_chart())

        # Canvas
        self.canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<Double-1>", self._on_double_click)

    def _on_double_click(self, event):
        pass 

    def update_chart(self):
        # 1. PARAMÈTRES (Mapping TF -> Secondes)
        tf_str = self.mode_var.get()
        
        # Conversion en secondes pour l'aggrégateur
        if tf_str.endswith("s"):
            seconds = int(tf_str[:-1])
        elif tf_str.endswith("m"):
            seconds = int(tf_str[:-1]) * 60
        elif tf_str.endswith("h"):
            seconds = int(tf_str[:-1]) * 3600
        else:
            seconds = 300 # Default 5m

        # Mapping TF -> Radar Key (Quel FVG afficher ?)
        radar_key = "M5"
        if seconds >= 900: radar_key = "H1"    # >= 15m
        elif seconds >= 300: radar_key = "M15" # >= 5m

        # 2. RÉCUPÉRATION DONNÉES
        # CORRECTION MAJEURE: On passe 'seconds' comme résolution, pas comme durée totale.
        # L'aggrégateur renvoie par défaut les 100 dernières bougies de cette résolution.
        candles = self.aggr.get_candles_data(self.sym, "time", seconds)
        radar = self.controller.analyzer.get_radar_snapshot(self.sym)

        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()

        if not candles: 
            self.canvas.create_text(w/2, h/2, text="Waiting for ticks...", fill=COLOR_MUTED, font=("Segoe UI", 10))
            return

        # 3. CALCULS ÉCHELLE (Y) - BASÉ UNIQUEMENT SUR LES BOUGIES
        prices = [c["high"] for c in candles] + [c["low"] for c in candles]
        
        max_p = max(prices)
        min_p = min(prices)
        rng = max_p - min_p
        if rng == 0: rng = 1
        
        max_p += rng * 0.1
        min_p -= rng * 0.1
        rng = max_p - min_p

        pad_top = 20
        pad_bot = 20
        pad_right = 50 

        def to_y(p):
            return pad_top + (1 - (p - min_p) / rng) * (h - pad_top - pad_bot)

        # 4. DESSIN : ARRIÈRE-PLAN (FVG & Niveaux)
        
        # A. FVG 
        if radar:
            fvgs = radar.get(radar_key, {}).get("fvgs", [])
            for fvg in fvgs:
                top, bot = fvg['top'], fvg['bot']
                
                y1 = to_y(top)
                y2 = to_y(bot)
                
                col = COLOR_FVG_BULL if fvg['type'] == "BULL" else COLOR_FVG_BEAR
                # Stipple retiré pour couleur plus franche, ou gardé léger
                self.canvas.create_rectangle(0, y1, w, y2, fill=col, outline="", stipple="gray50")
                
                if 0 < y1 < h or 0 < y2 < h:
                    self.canvas.create_text(5, y1, text=f"FVG {radar_key}", anchor="nw", fill=col, font=("Segoe UI", 6, "bold"))

        # B. NIVEAUX SESSION
        session_lvls = radar.get("SESSION", {}) if radar else {}
        for k, v in session_lvls.items():
            if k == "Gap": continue
            if v and isinstance(v, (int, float)):
                y = to_y(v)
                
                if -20 < y < h + 20:
                    dash = (4, 2)
                    width = 1
                    col = COLOR_SESSION
                    if "High" in k or "Low" in k: 
                        width = 2
                        dash = None 
                    elif "Open" in k:
                        dash = (2, 4)
                    
                    self.canvas.create_line(0, y, w-pad_right, y, fill=col, width=width, dash=dash)
                    self.canvas.create_text(w-pad_right-5, y-5, text=k, anchor="e", fill=col, font=("Segoe UI", 7, "bold"))

        # C. GAP
        prev_close = session_lvls.get("Prev Close")
        gap = session_lvls.get("Gap", 0)
        if prev_close and abs(gap) > 0:
             y_pc = to_y(prev_close)
             if 0 < y_pc < h:
                 self.canvas.create_line(0, y_pc, w, y_pc, fill=COLOR_GAP, dash=(1, 2))
                 self.canvas.create_text(10, y_pc+2, text=f"GAP {gap:+.2f}", anchor="nw", fill=COLOR_GAP, font=("Segoe UI", 7))

        # 5. DESSIN : BOUGIES (Avant-Plan)
        n_candles = len(candles)
        area_w = w - pad_right
        candle_w = area_w / max(n_candles, 10)
        candle_w = min(candle_w, 20) 
        start_x = w - pad_right - (n_candles * candle_w)

        self.canvas.create_line(0, to_y(max_p), w, to_y(max_p), fill=COLOR_GRID)
        self.canvas.create_line(0, to_y(min_p), w, to_y(min_p), fill=COLOR_GRID)

        for i, c in enumerate(candles):
            cx = start_x + i * candle_w + (candle_w / 2)
            
            yh = to_y(c["high"])
            yl = to_y(c["low"])
            yo = to_y(c["open"])
            yc = to_y(c["close"])
            
            col = COLOR_UP if c["close"] >= c["open"] else COLOR_DOWN
            
            self.canvas.create_line(cx, yh, cx, yl, fill=COLOR_WICK)
            
            rect_w = max(1, candle_w - 2)
            x1 = cx - rect_w/2
            x2 = cx + rect_w/2
            
            if abs(yo - yc) < 1: 
                self.canvas.create_line(x1, yo, x2, yo, fill=col)
            else:
                self.canvas.create_rectangle(x1, yo, x2, yc, fill=col, outline=col)

        # 6. PRIX ACTUEL
        last_px = candles[-1]["close"]
        y_last = to_y(last_px)
        
        self.canvas.create_line(0, y_last, w, y_last, fill=COLOR_MUTED, dash=(1, 3))
        
        tag_bg = COLOR_UP if candles[-1]["close"] >= candles[-1]["open"] else COLOR_DOWN
        self.canvas.create_rectangle(w-pad_right, y_last-9, w, y_last+9, fill=tag_bg, outline="")
        self.canvas.create_text(w-25, y_last, text=f"{last_px:.2f}", fill="white", font=("Segoe UI", 8, "bold"))