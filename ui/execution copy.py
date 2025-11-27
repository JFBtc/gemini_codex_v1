# ui/execution.py
import tkinter as tk
from tkinter import ttk
from ui.book import MultiHorizonWidget, COLOR_BG_APP
from ui.charts import MiniChartWidget

# --- COULEURS & STYLES ---
BG_PANEL = "#f7f9fc"
COL_H_LIGHT = "#546e7a"
COL_VAL_BOLD = "#263238"
COL_ACCENT_BULL = "#00c853" # Vert électrique
COL_ACCENT_BEAR = "#ff1744" # Rouge électrique
COL_NEUTRAL = "#b0bec5"

class ContextPanel(tk.Frame):
    """
    ZONE GAUCHE : HUD STRATÉGIQUE (Head-Up Display)
    """
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG_PANEL, width=340)
        self.controller = controller
        self.sym = None
        self.pack_propagate(False)

        # --- 1. BIAS GAUGE ---
        f_gauge = tk.Frame(self, bg=BG_PANEL, pady=5)
        f_gauge.pack(fill="x", padx=10, pady=(5,0))
        
        tk.Label(f_gauge, text="MARKET BIAS", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 7, "bold")).pack(anchor="w")
        
        self.canvas_bias = tk.Canvas(f_gauge, width=300, height=20, bg=BG_PANEL, highlightthickness=0)
        self.canvas_bias.pack(pady=2)
        
        self.lbl_bias_score = tk.Label(f_gauge, text="NEUTRAL", bg=BG_PANEL, fg=COL_VAL_BOLD, font=("Segoe UI", 11, "bold"))
        self.lbl_bias_score.pack()
        
        # Label pour les raisons (multiligne si besoin)
        self.lbl_bias_reason = tk.Label(f_gauge, text="Waiting...", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8), wraplength=300, justify="center")
        self.lbl_bias_reason.pack(pady=(2,5))

        # --- 2. NEXT MAGNETS ---
        tk.Label(self, text="NEXT LIQUIDITY MAGNETS", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8, "bold")).pack(pady=(10,2), anchor="w", padx=10)
        
        self.f_magnets = tk.Frame(self, bg="white", bd=0, relief="flat")
        self.f_magnets.pack(fill="x", padx=10, ipady=5)
        
        # Resistance
        self.lbl_mag_up_val = tk.Label(self.f_magnets, text="---", bg="white", fg=COL_ACCENT_BEAR, font=("Segoe UI", 10, "bold"))
        self.lbl_mag_up_val.pack(anchor="e", padx=10, pady=(5,0))
        self.lbl_mag_up_txt = tk.Label(self.f_magnets, text="Resistance", bg="white", fg=COL_H_LIGHT, font=("Segoe UI", 7))
        self.lbl_mag_up_txt.pack(anchor="e", padx=10)
        
        ttk.Separator(self.f_magnets, orient="horizontal").pack(fill="x", pady=5, padx=20)
        
        # Support
        self.lbl_mag_dn_val = tk.Label(self.f_magnets, text="---", bg="white", fg=COL_ACCENT_BULL, font=("Segoe UI", 10, "bold"))
        self.lbl_mag_dn_val.pack(anchor="w", padx=10)
        self.lbl_mag_dn_txt = tk.Label(self.f_magnets, text="Support", bg="white", fg=COL_H_LIGHT, font=("Segoe UI", 7))
        self.lbl_mag_dn_txt.pack(anchor="w", padx=10, pady=(0,5))

        # --- 3. CONTEXTE GLOBAL (Liste complète) ---
        tk.Label(self, text="SESSION & STRUCTURE MAP", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8, "bold")).pack(pady=(15,2), anchor="w", padx=10)
        
        # Treeview élargi pour tout voir
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
        self.tree_struct.tag_configure("active", background="#fff9c4", foreground="black") # Surlignage si on est dessus

        self._auto_refresh()

    def set_symbol(self, symbol):
        self.sym = symbol
        self._update_content()

    def _auto_refresh(self):
        if self.sym: self._update_content()
        self.after(1000, self._auto_refresh)

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

        # --- SCORE BIAS (Détaillé) ---
        score = 0
        reasons = []
        
        # RSI
        rsi_m15 = radar.get("M15", {}).get("rsi", 50)
        rsi_h1 = radar.get("H1", {}).get("rsi", 50)
        if rsi_m15 > 55: score += 2; reasons.append("M15 Momentum (Bull)")
        elif rsi_m15 < 45: score -= 2; reasons.append("M15 Momentum (Bear)")
        
        # VWAP
        if vwap:
            if last_px > vwap + 2.0: score += 2; reasons.append("Above VWAP")
            elif last_px < vwap - 2.0: score -= 2; reasons.append("Below VWAP")
        
        # Structure (EMA)
        ema_20_m5 = radar.get("M5", {}).get("ema_20", 0)
        if ema_20_m5 and last_px > ema_20_m5: score += 1; reasons.append("M5 Trend Up")
        elif ema_20_m5 and last_px < ema_20_m5: score -= 1; reasons.append("M5 Trend Down")

        score = max(min(score, 10), -10)
        self._draw_bias_gauge(score)
        
        txt_state = "NEUTRAL"
        col_state = COL_VAL_BOLD
        if score >= 4: txt_state = "BULLISH FLOW"; col_state = COL_ACCENT_BULL
        elif score <= -4: txt_state = "BEARISH FLOW"; col_state = COL_ACCENT_BEAR
        elif score > 1: txt_state = "MILDLY BULLISH"; col_state = "#66bb6a"
        elif score < -1: txt_state = "MILDLY BEARISH"; col_state = "#ef5350"
        
        self.lbl_bias_score.config(text=txt_state, fg=col_state)
        # Afficher TOUTES les raisons
        self.lbl_bias_reason.config(text=" | ".join(reasons) if reasons else "No clear signal")

        # --- MAGNETS (Immédiats) ---
        levels_map = [] # (price, name, type)
        session = radar.get("SESSION", {})
        
        # On compile tout pour les magnets
        for k, v in session.items():
            if v and isinstance(v, (int, float)) and k != "Gap": levels_map.append((v, k, "session"))
        if vwap: levels_map.append((vwap, "VWAP", "session"))
        
        # Bornes FVG pour les magnets
        for tf in ["M15", "H1"]:
            for fvg in radar.get(tf, {}).get("fvgs", []):
                levels_map.append((fvg['top'], f"FVG {tf} Top", "res" if fvg['type']=="BEAR" else "sup"))
                levels_map.append((fvg['bot'], f"FVG {tf} Bot", "res" if fvg['type']=="BEAR" else "sup"))

        levels_map.sort(key=lambda x: x[0])
        next_up, next_dn = None, None
        marge = 0.5 
        
        for px, name, _ in levels_map:
            if px > last_px + marge:
                next_up = (px, name); break
        for px, name, _ in reversed(levels_map):
            if px < last_px - marge:
                next_dn = (px, name); break

        self.lbl_mag_up_val.config(text=f"{next_up[0]:.2f}" if next_up else "Blue Sky")
        self.lbl_mag_up_txt.config(text=f"Target: {next_up[1]}" if next_up else "")

        self.lbl_mag_dn_val.config(text=f"{next_dn[0]:.2f}" if next_dn else "Free Fall")
        self.lbl_mag_dn_txt.config(text=f"Target: {next_dn[1]}" if next_dn else "")

        # --- CONTEXTE GLOBAL (Liste complète) ---
        self.tree_struct.delete(*self.tree_struct.get_children())
        rows = []

        # 1. Niveaux Session (Day H/L, Open, etc.)
        for k, v in session.items():
            if k == "Gap": continue
            if v and isinstance(v, (int, float)):
                dist = last_px - v
                rows.append({
                    "desc": k.upper(),
                    "lvl": f"{v:.2f}",
                    "dist": abs(dist),
                    "raw_dist": dist,
                    "tag": "session"
                })
        
        # Ajout du Gap séparément
        gap = session.get("Gap", 0)
        if abs(gap) > 0:
            rows.append({
                "desc": f"GAP ({gap:+.2f})",
                "lvl": "---",
                "dist": 9999, # Toujours à la fin ou début
                "raw_dist": 0,
                "tag": "bull" if gap > 0 else "bear"
            })

        # 2. FVGs (Tous les valides)
        for tf in ["M15", "H1"]:
            d = radar.get(tf, {})
            for fvg in d.get("fvgs", []):
                # Distance au FVG (0 si dedans)
                is_inside = fvg['bot'] <= last_px <= fvg['top']
                if is_inside:
                    dist = 0
                    d_txt = "INSIDE"
                    tag = "active"
                else:
                    d_top = abs(last_px - fvg['top'])
                    d_bot = abs(last_px - fvg['bot'])
                    dist = min(d_top, d_bot)
                    d_txt = f"{dist:.2f}"
                    tag = "bull" if fvg['type'] == "BULL" else "bear"
                
                rows.append({
                    "desc": f"FVG {tf} {fvg['type']}",
                    "lvl": f"{fvg['bot']:.2f}-{fvg['top']:.2f}",
                    "dist": dist,
                    "raw_dist": 0,
                    "tag": tag,
                    "txt_dist": d_txt
                })

        # Tri : Les plus proches d'abord
        rows.sort(key=lambda x: x["dist"])

        for r in rows:
            d_display = r.get("txt_dist", f"{r['dist']:.2f}")
            self.tree_struct.insert("", "end", values=(r["desc"], r["lvl"], d_display), tags=(r["tag"],))


class ExecutionView(tk.Frame):
    """VUE PRINCIPALE : Le Cockpit"""
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

        self.panel_ctx = ContextPanel(self.paned, controller)
        self.paned.add(self.panel_ctx, minsize=340) 

        self.f_doom_container = tk.Frame(self.paned, bg=COLOR_BG_APP)
        self.paned.add(self.f_doom_container, minsize=400)
        self.doom_widget = None

        self.f_charts = tk.Frame(self.paned, bg=COLOR_BG_APP)
        self.paned.add(self.f_charts, minsize=300)
        self.chart_top = None
        self.chart_bot = None

        self._on_change_sym()

    def _on_change_sym(self, event=None):
        sym = self.sym_var.get()
        if not sym: return
        self.current_sym = sym
        
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
        self.chart_bot.mode_var.set("5m")  # Passage en 5m pour voir mieux la structure
        self.chart_bot.update_chart()

    def refresh(self):
        if self.doom_widget: self.doom_widget.update_data()
        if self.chart_top: self.chart_top.update_chart()
        if self.chart_bot: self.chart_bot.update_chart()