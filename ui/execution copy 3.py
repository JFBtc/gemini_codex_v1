# ui/execution.py
import tkinter as tk
from tkinter import ttk
import time
import json
import os
from ui.book import MultiHorizonWidget, COLOR_BG_APP
from ui.charts import MiniChartWidget

# --- COULEURS & STYLES ---
BG_PANEL        = "#f7f9fc"
COL_H_LIGHT     = "#546e7a"
COL_VAL_BOLD    = "#263238"
COL_ACCENT_BULL = "#00c853" 
COL_ACCENT_BEAR = "#ff1744" 
COL_NEUTRAL     = "#b0bec5"

SETTINGS_FILE = "datalab_settings.json"

class ContextPanel(tk.Frame):
    """
    ZONE GAUCHE : HUD STRATÉGIQUE & NAVIGATION
    """
    def __init__(self, parent, controller, on_navigate_callback=None):
        super().__init__(parent, bg=BG_PANEL, width=340)
        self.controller = controller
        self.sym = None
        self.on_navigate = on_navigate_callback
        self.pack_propagate(False)

        # --- 1. BIAS GAUGE ---
        f_gauge = tk.Frame(self, bg=BG_PANEL, pady=5)
        f_gauge.pack(fill="x", padx=10, pady=(5,0))
        
        tk.Label(f_gauge, text="MARKET BIAS (Weighted)", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 7, "bold")).pack(anchor="w")
        
        self.canvas_bias = tk.Canvas(f_gauge, width=300, height=20, bg=BG_PANEL, highlightthickness=0)
        self.canvas_bias.pack(pady=2)
        
        self.lbl_bias_score = tk.Label(f_gauge, text="NEUTRAL", bg=BG_PANEL, fg=COL_VAL_BOLD, font=("Segoe UI", 11, "bold"))
        self.lbl_bias_score.pack()
        
        self.lbl_bias_reason = tk.Label(f_gauge, text="Waiting...", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8), wraplength=300, justify="center")
        self.lbl_bias_reason.pack(pady=(2,5))

        # --- 2. NEXT MAGNETS (Navigation Rapide) ---
        tk.Label(self, text="NEXT LIQUIDITY MAGNETS", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8, "bold")).pack(pady=(10,2), anchor="w", padx=10)
        
        self.f_magnets = tk.Frame(self, bg="white", bd=0, relief="flat")
        self.f_magnets.pack(fill="x", padx=10, ipady=5)
        
        # Resistance
        self.lbl_mag_up_val = tk.Label(self.f_magnets, text="---", bg="white", fg=COL_ACCENT_BEAR, font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.lbl_mag_up_val.pack(anchor="e", padx=10, pady=(5,0))
        self.lbl_mag_up_val.bind("<Button-1>", lambda e: self._on_click_magnet_label(self.lbl_mag_up_val))
        
        self.lbl_mag_up_txt = tk.Label(self.f_magnets, text="Resistance", bg="white", fg=COL_H_LIGHT, font=("Segoe UI", 7))
        self.lbl_mag_up_txt.pack(anchor="e", padx=10)
        
        ttk.Separator(self.f_magnets, orient="horizontal").pack(fill="x", pady=5, padx=20)
        
        # Support
        self.lbl_mag_dn_val = tk.Label(self.f_magnets, text="---", bg="white", fg=COL_ACCENT_BULL, font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.lbl_mag_dn_val.pack(anchor="w", padx=10)
        self.lbl_mag_dn_val.bind("<Button-1>", lambda e: self._on_click_magnet_label(self.lbl_mag_dn_val))

        self.lbl_mag_dn_txt = tk.Label(self.f_magnets, text="Support", bg="white", fg=COL_H_LIGHT, font=("Segoe UI", 7))
        self.lbl_mag_dn_txt.pack(anchor="w", padx=10, pady=(0,5))

        # --- 3. CONTEXTE GLOBAL (Liste complète) ---
        f_list_head = tk.Frame(self, bg=BG_PANEL)
        f_list_head.pack(fill="x", pady=(15,2), padx=10)
        tk.Label(f_list_head, text="SESSION & STRUCTURE MAP", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(f_list_head, text="(Double-Click to Snap)", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 7, "italic")).pack(side="right")
        
        self.tree_struct = ttk.Treeview(self, columns=("desc", "lvl", "dist"), show="headings", height=14)
        self.tree_struct.heading("desc", text="Level / Structure", anchor="w")
        self.tree_struct.heading("lvl", text="Price", anchor="c")
        self.tree_struct.heading("dist", text="Dist", anchor="e")
        
        self.tree_struct.column("desc", width=140, anchor="w")
        self.tree_struct.column("lvl", width=100, anchor="c")
        self.tree_struct.column("dist", width=60, anchor="e")
        
        self.tree_struct.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.tree_struct.tag_configure("bull", foreground=COL_ACCENT_BULL)
        self.tree_struct.tag_configure("bear", foreground=COL_ACCENT_BEAR)
        self.tree_struct.tag_configure("session", foreground="#0277bd", font=("Segoe UI", 9, "bold"))
        self.tree_struct.tag_configure("inactive", foreground=COL_NEUTRAL)
        self.tree_struct.tag_configure("active", background="#fff9c4", foreground="black") 

        self.tree_struct.bind("<Double-1>", self._on_tree_click)

        self._auto_refresh()

    def set_symbol(self, symbol):
        self.sym = symbol
        self._update_content()

    def _auto_refresh(self):
        if self.sym: self._update_content()
        self.after(1000, self._auto_refresh)

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    return json.load(f)
            except: return {}
        return {}

    def _is_enabled(self, settings, key, feature="act"):
        if not settings: return True
        return settings.get(key, {}).get(feature, False)

    def _on_click_magnet_label(self, lbl_widget):
        text = lbl_widget.cget("text")
        try:
            val = float(text)
            if self.on_navigate: self.on_navigate(val)
        except: pass

    def _on_tree_click(self, event):
        item_id = self.tree_struct.identify_row(event.y)
        if not item_id: return
        vals = self.tree_struct.item(item_id, "values")
        if not vals: return
        lvl_str = vals[1]
        try:
            if "-" in lvl_str:
                parts = lvl_str.split("-")
                val = (float(parts[0]) + float(parts[1])) / 2
            else:
                val = float(lvl_str)
            if self.on_navigate: self.on_navigate(val)
        except: pass

    def _draw_bias_gauge(self, score):
        w, h = 300, 20
        self.canvas_bias.delete("all")
        self.canvas_bias.create_rectangle(0, 8, w, 12, fill="#eceff1", outline="")
        cx = w / 2
        self.canvas_bias.create_line(cx, 5, cx, 15, fill=COL_H_LIGHT, width=1)
        pixels_per_unit = (w / 2) / 10
        bar_len = score * pixels_per_unit
        if score > 0:
            self.canvas_bias.create_rectangle(cx, 8, cx + bar_len, 12, fill=COL_ACCENT_BULL, outline="")
        elif score < 0:
            self.canvas_bias.create_rectangle(cx + bar_len, 8, cx, 12, fill=COL_ACCENT_BEAR, outline="")
        marker_x = cx + bar_len
        self.canvas_bias.create_oval(marker_x-4, 5, marker_x+4, 15, fill="white", outline=COL_VAL_BOLD, width=2)

    def _update_content(self):
        radar = self.controller.analyzer.get_radar_snapshot(self.sym)
        last_px = self.controller.aggregator.get_last_price(self.sym)
        vwap = self.controller.aggregator.get_rolling_vwap(self.sym, 60)
        
        if not radar or not last_px: return

        settings = self._load_settings()

        # --- SCORE BIAS PONDÉRÉ (Multi-Timeframe) ---
        score = 0
        reasons = []
        
        # Poids par Timeframe
        WEIGHTS = {
            "M1": 0.5, "M5": 1, "M15": 2, "M30": 3, 
            "H1": 4, "H4": 6, "D1": 8, "SESSION": 3
        }

        # 1. INDICATEURS ACTIVÉS DANS DATALAB (Bias)
        for key, cfg in settings.items():
            if not cfg.get("bias", False): continue
            
            if "RSI" in key:
                tf = key.split("_")[1] # RSI_M15 -> M15
                data = radar.get(tf, {})
                rsi = data.get("rsi", 50)
                w = WEIGHTS.get(tf, 1)
                
                if rsi > 60: score += w; reasons.append(f"{tf} RSI+")
                elif rsi < 40: score -= w; reasons.append(f"{tf} RSI-")
            
            elif "EMA" in key:
                tf = key.split("_")[-1] # EMA_20_M5 -> M5
                data = radar.get(tf, {})
                ema = data.get("ema_20")
                w = WEIGHTS.get(tf, 1)
                if ema:
                    if last_px > ema: score += w; reasons.append(f"{tf} Trend+")
                    else: score -= w; reasons.append(f"{tf} Trend-")

        # 2. PATTERNS (Bias)
        for tf in ["M1", "M5", "M15", "H1", "H4"]:
            pat_key = f"PAT_{tf}"
            if not self._is_enabled(settings, pat_key, "bias"): continue

            data = radar.get(tf, {})
            pats = data.get("patterns", [])
            w = WEIGHTS.get(tf, 1)
            
            for p in pats:
                # On ignore l'Inside Bar pour le biais car neutre
                if p["side"] == "BULL":
                    score += (w * 1.5)
                    reasons.append(f"{tf} {p['name']}")
                elif p["side"] == "BEAR":
                    score -= (w * 1.5)
                    reasons.append(f"{tf} {p['name']}")

        # 3. SESSION BREAKS (Bias)
        sess = radar.get("SESSION", {})
        day_h = sess.get("Day High")
        day_l = sess.get("Day Low")
        
        if self._is_enabled(settings, "DAY_HIGH", "bias") and day_h and last_px > day_h: 
            score += 5; reasons.append("BREAK DAY H")
        if self._is_enabled(settings, "DAY_LOW", "bias") and day_l and last_px < day_l: 
            score -= 5; reasons.append("BREAK DAY L")

        # Mise à jour Jauge
        score_norm = max(min(score / 2.5, 10), -10)
        self._draw_bias_gauge(score_norm)
        
        txt_state = "NEUTRAL"
        col_state = COL_VAL_BOLD
        if score_norm >= 5: txt_state = "STRONG BULL"; col_state = COL_ACCENT_BULL
        elif score_norm <= -5: txt_state = "STRONG BEAR"; col_state = COL_ACCENT_BEAR
        elif score_norm > 1: txt_state = "BULLISH"; col_state = "#66bb6a"
        elif score_norm < -1: txt_state = "BEARISH"; col_state = "#ef5350"
        
        self.lbl_bias_score.config(text=txt_state, fg=col_state)
        self.lbl_bias_reason.config(text=" | ".join(reasons[-3:]) if reasons else "Waiting...")

        # --- MAGNETS & MAP (DYNAMIQUE AVEC PATTERNS) ---
        sess_key_map = {
            "RTH Open": "RTH_OPEN", "RTH Close": "RTH_CLOSE",
            "Globex Open": "GLOBEX_OPEN", "Settlement": "SETTLEMENT",
            "Day High": "DAY_HIGH", "Day Low": "DAY_LOW",
            "Gap RTH": "GAP_RTH", "Gap Maint": "GAP_MAINT",
            "VWAP": "VWAP"
        }

        valid_magnets = [] 
        all_map_rows = [] 
        
        # 1. Niveaux Session
        for k, v in sess.items():
            if not isinstance(v, (int, float)) or abs(v) == 0: continue
            s_key = sess_key_map.get(k, k)
            
            if self._is_enabled(settings, s_key, "mag") and "Gap" not in k:
                valid_magnets.append((v, k, "session"))
            
            if self._is_enabled(settings, s_key, "map"):
                dist = last_px - v
                if "Gap" in k:
                    all_map_rows.append({
                        "desc": k.upper() + f" ({v:+.2f})", "lvl": "---", 
                        "dist": 9999, "raw_dist": 0, "tag": "bull" if v>0 else "bear"
                    })
                else:
                    all_map_rows.append({
                        "desc": k.upper(), "lvl": f"{v:.2f}", 
                        "dist": abs(dist), "tag": "session"
                    })

        if vwap and self._is_enabled(settings, "VWAP", "mag"):
            valid_magnets.append((vwap, "VWAP", "session"))
        if vwap and self._is_enabled(settings, "VWAP", "map"):
             all_map_rows.append({"desc": "VWAP", "lvl": f"{vwap:.2f}", "dist": abs(last_px-vwap), "tag": "session"})

        # 2. FVGs
        for tf, data in radar.items():
            if tf == "SESSION": continue
            fvg_key = f"FVG_{tf}"
            fvgs = data.get("fvgs", [])
            
            if fvgs and (self._is_enabled(settings, fvg_key, "mag") or self._is_enabled(settings, fvg_key, "map")):
                for fvg in fvgs:
                    if fvg.get("mitigated", False): continue
                    
                    if self._is_enabled(settings, fvg_key, "mag"):
                        valid_magnets.append((fvg['top'], f"FVG {tf} Top", "res" if fvg['type']=="BEAR" else "sup"))
                        valid_magnets.append((fvg['bot'], f"FVG {tf} Bot", "res" if fvg['type']=="BEAR" else "sup"))
                    
                    if self._is_enabled(settings, fvg_key, "map"):
                        is_inside = fvg['bot'] <= last_px <= fvg['top']
                        dist = 0 if is_inside else min(abs(last_px - fvg['top']), abs(last_px - fvg['bot']))
                        tag = "active" if is_inside else ("bull" if fvg['type'] == "BULL" else "bear")
                        d_txt = "INSIDE" if is_inside else f"{dist:.2f}"
                        all_map_rows.append({
                            "desc": f"FVG {tf} {fvg['type']}",
                            "lvl": f"{fvg['bot']:.2f}-{fvg['top']:.2f}",
                            "dist": dist, "tag": tag, "txt_dist": d_txt
                        })

        # 3. PATTERNS (Nouveau !)
        # Si un pattern a un niveau de prix (level_price), on l'utilise
        for tf, data in radar.items():
            if tf == "SESSION": continue
            pat_key = f"PAT_{tf}"
            pats = data.get("patterns", [])
            
            if not pats: continue
            
            use_mag = self._is_enabled(settings, pat_key, "mag")
            use_map = self._is_enabled(settings, pat_key, "map")
            
            if not use_mag and not use_map: continue

            for p in pats:
                lvl = p.get("level_price")
                if not lvl: continue # Pas de niveau (ex: Inside Bar)
                
                name_short = p['name'].replace("(Live)", "").strip()
                
                # Magnet (Support/Resistance)
                if use_mag:
                    # Si Bullish (ex: Rejection Low), le niveau est un Support
                    # Si Bearish (ex: Break Low), le niveau devient Résistance
                    # Simplification : On affiche juste le niveau et le nom
                    m_type = "sup" if p["side"] == "BULL" else "res"
                    valid_magnets.append((lvl, f"{tf} {name_short}", m_type))
                
                # Map
                if use_map:
                    dist = abs(last_px - lvl)
                    tag = "bull" if p["side"] == "BULL" else "bear"
                    all_map_rows.append({
                        "desc": f"{tf} {name_short}",
                        "lvl": f"{lvl:.2f}",
                        "dist": dist, "tag": tag, "txt_dist": f"{dist:.2f}"
                    })

        # --- UPDATE UI ---
        # Magnets
        valid_magnets.sort(key=lambda x: x[0])
        next_up, next_dn = None, None
        marge = 0.5 
        for px, name, _ in valid_magnets:
            if px > last_px + marge:
                next_up = (px, name); break
        for px, name, _ in reversed(valid_magnets):
            if px < last_px - marge:
                next_dn = (px, name); break

        self.lbl_mag_up_val.config(text=f"{next_up[0]:.2f}" if next_up else "---")
        self.lbl_mag_up_txt.config(text=f"Target: {next_up[1]}" if next_up else "")
        self.lbl_mag_dn_val.config(text=f"{next_dn[0]:.2f}" if next_dn else "---")
        self.lbl_mag_dn_txt.config(text=f"Target: {next_dn[1]}" if next_dn else "")

        # Map
        self.tree_struct.delete(*self.tree_struct.get_children())
        all_map_rows.sort(key=lambda x: x["dist"])
        for r in all_map_rows:
            d_display = r.get("txt_dist", f"{r['dist']:.2f}")
            self.tree_struct.insert("", "end", values=(r["desc"], r["lvl"], d_display), tags=(r["tag"],))


class ExecutionView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG_APP)
        self.controller = controller
        self.current_sym = None
        
        f_head = tk.Frame(self, bg="white", padx=10, pady=5)
        f_head.pack(fill="x", pady=(0, 2))
        tk.Label(f_head, text="ACTIVE ASSET :", bg="white", font=("Segoe UI", 9, "bold")).pack(side="left")
        
        self.sym_var = tk.StringVar()
        tickers = list(controller.contracts_map.keys())
        def_sym = "MES" if "MES" in tickers else (tickers[0] if tickers else "")
        self.sym_var.set(def_sym)
        
        cb = ttk.Combobox(f_head, textvariable=self.sym_var, values=tickers, width=10, state="readonly", font=("Segoe UI", 10, "bold"))
        cb.pack(side="left", padx=10)
        cb.bind("<<ComboboxSelected>>", self._on_change_sym)
        
        self.paned = tk.PanedWindow(self, orient="horizontal", bg=COLOR_BG_APP, sashwidth=4)
        self.paned.pack(fill="both", expand=True)

        self.panel_ctx = ContextPanel(self.paned, controller, on_navigate_callback=self._on_navigate_to_price)
        self.paned.add(self.panel_ctx, minsize=340) 

        self.f_doom_container = tk.Frame(self.paned, bg=COLOR_BG_APP)
        self.paned.add(self.f_doom_container, minsize=400)
        self.doom_widget = None

        self.f_charts = tk.Frame(self.paned, bg=COLOR_BG_APP)
        self.paned.add(self.f_charts, minsize=300)
        self.chart_top = None
        self.chart_bot = None

        self._on_change_sym()

    def _on_navigate_to_price(self, price):
        if self.doom_widget:
            self.doom_widget._anchor_price = price
            self.doom_widget._last_user_scroll = time.time()
            self.doom_widget.update_data()

    def _on_change_sym(self, event=None):
        sym = self.sym_var.get()
        if not sym: return
        self.current_sym = sym
        
        self.controller.active_symbol = sym 
        self.panel_ctx.set_symbol(sym)
        
        if self.doom_widget: self.doom_widget.destroy()
        self.doom_widget = MultiHorizonWidget(self.f_doom_container, self.controller, sym)
        self.doom_widget.pack(fill="both", expand=True)
        
        for w in self.f_charts.winfo_children(): w.destroy()
        
        self.chart_top = MiniChartWidget(self.f_charts, self.controller, sym, height=300)
        self.chart_top.pack(fill="both", expand=True, pady=(0,2))
        self.chart_top.mode_var.set("15m") 
        self.chart_top.update_chart()

        self.chart_bot = MiniChartWidget(self.f_charts, self.controller, sym, height=300)
        self.chart_bot.pack(fill="both", expand=True, pady=(2,0))
        self.chart_bot.mode_var.set("5m")
        self.chart_bot.update_chart()

    def refresh(self):
        if self.doom_widget: self.doom_widget.update_data()
        if self.chart_top: self.chart_top.update_chart()
        if self.chart_bot: self.chart_bot.update_chart()