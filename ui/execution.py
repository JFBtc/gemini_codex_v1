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
        
        # Mémoire des niveaux cochés pour le DOM (Set d'IDs uniques)
        self.checked_for_dom = set() 

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

        # --- 3. CONTEXTE GLOBAL (Liste complète & SÉLECTION DOM) ---
        f_list_head = tk.Frame(self, bg=BG_PANEL)
        f_list_head.pack(fill="x", pady=(15,2), padx=10)
        tk.Label(f_list_head, text="SESSION & STRUCTURE MAP", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(f_list_head, text="(Check for DOM | Dbl-Click Snap)", bg=BG_PANEL, fg=COL_H_LIGHT, font=("Segoe UI", 7, "italic")).pack(side="right")
        
        self.tree_struct = ttk.Treeview(self, columns=("dom", "desc", "lvl", "dist"), show="headings", height=14)
        
        self.tree_struct.heading("dom", text="DOM", anchor="c")
        self.tree_struct.heading("desc", text="Level / Structure", anchor="w")
        self.tree_struct.heading("lvl", text="Price", anchor="c")
        self.tree_struct.heading("dist", text="Dist", anchor="e")
        
        self.tree_struct.column("dom", width=40, anchor="c") 
        self.tree_struct.column("desc", width=140, anchor="w")
        self.tree_struct.column("lvl", width=80, anchor="c")
        self.tree_struct.column("dist", width=60, anchor="e")
        
        self.tree_struct.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.tree_struct.tag_configure("bull", foreground=COL_ACCENT_BULL)
        self.tree_struct.tag_configure("bear", foreground=COL_ACCENT_BEAR)
        self.tree_struct.tag_configure("session", foreground="#0277bd", font=("Segoe UI", 9, "bold"))
        self.tree_struct.tag_configure("inactive", foreground=COL_NEUTRAL)
        self.tree_struct.tag_configure("active", background="#fff9c4", foreground="black") 
        self.tree_struct.tag_configure("checked", font=("Segoe UI", 9, "bold")) 

        self.tree_struct.bind("<Button-1>", self._on_tree_click)
        self.tree_struct.bind("<Double-1>", self._on_tree_dbl_click)

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
        region = self.tree_struct.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_struct.identify_column(event.x)
        item_id = self.tree_struct.identify_row(event.y)
        if not item_id: return
        
        if col == "#1": # Colonne DOM
            tags = self.tree_struct.item(item_id, "tags")
            if not tags: return
            unique_id = tags[0] 
            if unique_id in self.checked_for_dom:
                self.checked_for_dom.remove(unique_id)
            else:
                self.checked_for_dom.add(unique_id)
            self._update_content()

    def _on_tree_dbl_click(self, event):
        item_id = self.tree_struct.identify_row(event.y)
        if not item_id: return
        vals = self.tree_struct.item(item_id, "values")
        if not vals: return
        lvl_str = vals[2]
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

        # --- SCORE BIAS PONDÉRÉ ---
        score = 0
        reasons = []
        
        WEIGHTS = {
            "M1": 0.5, "M5": 1, "M15": 1.5, "M30": 2, 
            "H1": 3, "H4": 5, "D1": 8, "SESSION": 3
        }

        # 1. INDICATEURS (RSI / EMA)
        for key, cfg in settings.items():
            if not self._is_enabled(settings, key, "bias"): continue
            
            if "RSI" in key:
                tf = key.split("_")[1]
                data = radar.get(tf, {})
                rsi = data.get("rsi", 50)
                w = WEIGHTS.get(tf, 1)
                if rsi > 60: score += w; reasons.append(f"{tf} RSI+")
                elif rsi < 40: score -= w; reasons.append(f"{tf} RSI-")
            elif "EMA" in key:
                tf = key.split("_")[-1]
                data = radar.get(tf, {})
                ema = data.get("ema_20")
                w = WEIGHTS.get(tf, 1)
                if ema and last_px > ema: score += w; reasons.append(f"{tf} Trend+")
                elif ema and last_px < ema: score -= w; reasons.append(f"{tf} Trend-")

        # 2. PATTERNS (Bias)
        for tf in ["M1", "M5", "M15", "H1", "H4"]:
            if not self._is_enabled(settings, f"PAT_{tf}", "bias"): continue
            pats = radar.get(tf, {}).get("patterns", [])
            w = WEIGHTS.get(tf, 1)
            for p in pats:
                if p["side"] == "BULL": score += (w * 1.5); reasons.append(f"{tf} {p['name']}")
                elif p["side"] == "BEAR": score -= (w * 1.5); reasons.append(f"{tf} {p['name']}")

        # 3. FVGS (Bias - NOUVEAU)
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4"]:
            if not self._is_enabled(settings, f"FVG_{tf}", "bias"): continue
            fvgs = radar.get(tf, {}).get("fvgs", [])
            w = WEIGHTS.get(tf, 1)
            for fvg in fvgs:
                if fvg.get("mitigated", False): continue
                # Support = Hausse, Résistance = Baisse
                if fvg['type'] == "BULL": score += w
                elif fvg['type'] == "BEAR": score -= w

        # 4. SESSION BREAKS (Bias)
        sess = radar.get("SESSION", {})
        day_h = sess.get("Day High")
        day_l = sess.get("Day Low")
        if self._is_enabled(settings, "DAY_HIGH", "bias") and day_h and last_px > day_h: 
            score += 5; reasons.append("BREAK DAY H")
        if self._is_enabled(settings, "DAY_LOW", "bias") and day_l and last_px < day_l: 
            score -= 5; reasons.append("BREAK DAY L")

        score_norm = max(min(score / 3.0, 10), -10)
        self._draw_bias_gauge(score_norm)
        
        txt_state = "NEUTRAL"
        col_state = COL_VAL_BOLD
        if score_norm >= 5: txt_state = "STRONG BULL"; col_state = COL_ACCENT_BULL
        elif score_norm <= -5: txt_state = "STRONG BEAR"; col_state = COL_ACCENT_BEAR
        elif score_norm > 1: txt_state = "BULLISH"; col_state = "#66bb6a"
        elif score_norm < -1: txt_state = "BEARISH"; col_state = "#ef5350"
        
        self.lbl_bias_score.config(text=txt_state, fg=col_state)
        self.lbl_bias_reason.config(text=" | ".join(reasons[-3:]) if reasons else "Waiting...")

        # --- MAGNETS & MAP ---
        sess_key_map = {
            "RTH Open": "RTH_OPEN", "RTH Close": "RTH_CLOSE",
            "Globex Open": "GLOBEX_OPEN", "Settlement": "SETTLEMENT",
            "Day High": "DAY_HIGH", "Day Low": "DAY_LOW",
            "Gap RTH": "GAP_RTH", "Gap Maint": "GAP_MAINT", "VWAP": "VWAP"
        }

        valid_magnets = [] 
        all_map_rows = [] 
        dom_export_list = []

        # 1. NIVEAUX SESSION
        for k, v in sess.items():
            if not isinstance(v, (int, float)) or abs(v) == 0: continue
            s_key = sess_key_map.get(k, k)
            unique_id = f"SESS_{k}"
            is_checked = unique_id in self.checked_for_dom
            chk_char = "☑" if is_checked else "☐"
            
            if is_checked: dom_export_list.append({"price": v, "type": "sup" if last_px > v else "res", "label": k})
            if self._is_enabled(settings, s_key, "mag") and "Gap" not in k: valid_magnets.append((v, k, "session"))
            if self._is_enabled(settings, s_key, "map"):
                dist = last_px - v
                tag = "bull" if v > 0 else "bear" if "Gap" in k else "session"
                row_tags = [unique_id, tag]; 
                if is_checked: row_tags.append("checked")
                all_map_rows.append({"dom": chk_char, "desc": k.upper() + (f" ({v:+.2f})" if "Gap" in k else ""), 
                                     "lvl": "---" if "Gap" in k else f"{v:.2f}", 
                                     "dist": 9999 if "Gap" in k else abs(dist), 
                                     "sort_dist": 9999 if "Gap" in k else abs(dist), "tags": tuple(row_tags)})

        if vwap:
            if self._is_enabled(settings, "VWAP", "mag"): valid_magnets.append((vwap, "VWAP", "session"))
            if self._is_enabled(settings, "VWAP", "map"):
                uid = "SESS_VWAP"; chk = "☑" if uid in self.checked_for_dom else "☐"
                if uid in self.checked_for_dom: dom_export_list.append({"price": vwap, "type": "sup" if last_px>vwap else "res", "label": "VWAP"})
                rt = [uid, "session"]; 
                if uid in self.checked_for_dom: rt.append("checked")
                all_map_rows.append({"dom": chk, "desc": "VWAP", "lvl": f"{vwap:.2f}", "dist": abs(last_px-vwap), "sort_dist": abs(last_px-vwap), "tags": tuple(rt)})

        # 2. FVGs
        for tf, data in radar.items():
            if tf == "SESSION": continue
            fvg_key = f"FVG_{tf}"
            fvgs = data.get("fvgs", [])
            
            if fvgs and (self._is_enabled(settings, fvg_key, "mag") or self._is_enabled(settings, fvg_key, "map")):
                for fvg in fvgs:
                    if fvg.get("mitigated", False): continue
                    uid = f"FVG_{tf}_{fvg['bot']}"
                    
                    if self._is_enabled(settings, fvg_key, "mag"):
                        valid_magnets.append((fvg['top'], f"FVG {tf} Top", "res" if fvg['type']=="BEAR" else "sup"))
                        valid_magnets.append((fvg['bot'], f"FVG {tf} Bot", "res" if fvg['type']=="BEAR" else "sup"))
                    
                    if self._is_enabled(settings, fvg_key, "map"):
                        is_chk = uid in self.checked_for_dom; chk = "☑" if is_chk else "☐"
                        is_in = fvg['bot'] <= last_px <= fvg['top']
                        dist = 0 if is_in else min(abs(last_px - fvg['top']), abs(last_px - fvg['bot']))
                        tag = "active" if is_in else ("bull" if fvg['type'] == "BULL" else "bear")
                        rt = [uid, tag]; 
                        if is_chk: rt.append("checked")
                        
                        all_map_rows.append({"dom": chk, "desc": f"FVG {tf} {fvg['type']}", "lvl": f"{fvg['bot']:.2f}-{fvg['top']:.2f}", 
                                             "dist": dist, "sort_dist": dist, "tags": tuple(rt)})
                        
                        if is_chk:
                            t_l = "sup" if fvg['type'] == "BULL" else "res"
                            dom_export_list.append({"price": fvg['top'], "type": t_l, "label": f"{tf} FVG Top"})
                            dom_export_list.append({"price": fvg['bot'], "type": t_l, "label": f"{tf} FVG Bot"})

        # 3. PATTERNS
        for tf, data in radar.items():
            if tf == "SESSION": continue
            pat_key = f"PAT_{tf}"
            pats = data.get("patterns", [])
            
            if pats and (self._is_enabled(settings, pat_key, "mag") or self._is_enabled(settings, pat_key, "map")):
                for p in pats:
                    lvl = p.get("level_price")
                    if not lvl: continue
                    name_s = p['name'].replace("(Live)", "").strip()
                    uid = f"{tf}_{name_s}_{lvl}"
                    
                    if self._is_enabled(settings, pat_key, "mag"):
                        valid_magnets.append((lvl, f"{tf} {name_s}", "sup" if p["side"]=="BULL" else "res"))
                    
                    if self._is_enabled(settings, pat_key, "map"):
                        is_chk = uid in self.checked_for_dom; chk = "☑" if is_chk else "☐"
                        if is_chk: dom_export_list.append({"price": lvl, "type": "sup" if p["side"]=="BULL" else "res", "label": f"{tf} {name_s}"})
                        dist = abs(last_px - lvl)
                        rt = [uid, "bull" if p["side"]=="BULL" else "bear"]; 
                        if is_chk: rt.append("checked")
                        all_map_rows.append({"dom": chk, "desc": f"{tf} {name_s}", "lvl": f"{lvl:.2f}", "dist": dist, "sort_dist": dist, "tags": tuple(rt)})

        # RENDU
        valid_magnets.sort(key=lambda x: x[0])
        next_up, next_dn = None, None
        marge = 0.5 
        for px, name, _ in valid_magnets:
            if px > last_px + marge: next_up = (px, name); break
        for px, name, _ in reversed(valid_magnets):
            if px < last_px - marge: next_dn = (px, name); break

        self.lbl_mag_up_val.config(text=f"{next_up[0]:.2f}" if next_up else "---")
        self.lbl_mag_up_txt.config(text=f"Target: {next_up[1]}" if next_up else "")
        self.lbl_mag_dn_val.config(text=f"{next_dn[0]:.2f}" if next_dn else "---")
        self.lbl_mag_dn_txt.config(text=f"Target: {next_dn[1]}" if next_dn else "")

        self.tree_struct.delete(*self.tree_struct.get_children())
        all_map_rows.sort(key=lambda x: x["sort_dist"])
        for r in all_map_rows:
            self.tree_struct.insert("", "end", values=(r["dom"], r["desc"], r["lvl"], f"{r['dist']:.2f}"), tags=r["tags"])

        self.controller.set_dom_levels(self.sym, dom_export_list)


class ExecutionView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG_APP)
        self.controller = controller
        self.current_sym = None
        f_head = tk.Frame(self, bg="white", padx=10, pady=5); f_head.pack(fill="x", pady=(0, 2))
        tk.Label(f_head, text="ACTIVE ASSET :", bg="white", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.sym_var = tk.StringVar()
        tickers = list(controller.contracts_map.keys())
        def_sym = "MES" if "MES" in tickers else (tickers[0] if tickers else "")
        self.sym_var.set(def_sym)
        cb = ttk.Combobox(f_head, textvariable=self.sym_var, values=tickers, width=10, state="readonly", font=("Segoe UI", 10, "bold"))
        cb.pack(side="left", padx=10)
        cb.bind("<<ComboboxSelected>>", self._on_change_sym)
        self.paned = tk.PanedWindow(self, orient="horizontal", bg=COLOR_BG_APP, sashwidth=4); self.paned.pack(fill="both", expand=True)
        self.panel_ctx = ContextPanel(self.paned, controller, on_navigate_callback=self._on_navigate_to_price)
        self.paned.add(self.panel_ctx, minsize=340) 
        self.f_doom_container = tk.Frame(self.paned, bg=COLOR_BG_APP); self.paned.add(self.f_doom_container, minsize=400)
        self.doom_widget = None
        self.f_charts = tk.Frame(self.paned, bg=COLOR_BG_APP); self.paned.add(self.f_charts, minsize=300)
        self.chart_top = None; self.chart_bot = None
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
        self.chart_top = MiniChartWidget(self.f_charts, self.controller, sym, height=300); self.chart_top.pack(fill="both", expand=True, pady=(0,2))
        self.chart_top.mode_var.set("15m"); self.chart_top.update_chart()
        self.chart_bot = MiniChartWidget(self.f_charts, self.controller, sym, height=300); self.chart_bot.pack(fill="both", expand=True, pady=(2,0))
        self.chart_bot.mode_var.set("5m"); self.chart_bot.update_chart()

    def refresh(self):
        if self.doom_widget: self.doom_widget.update_data()
        if self.chart_top: self.chart_top.update_chart()
        if self.chart_bot: self.chart_bot.update_chart()