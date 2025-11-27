# ui/datalab.py
import tkinter as tk
from tkinter import ttk
import json
import os

# --- COULEURS ---
BG_DARK     = "#f0f2f5"
BG_CARD     = "#ffffff"
TXT_MAIN    = "#263238"
TXT_DIM     = "#78909c"
COL_ACTIVE  = "#2e7d32" 
COL_INACTIVE= "#cfd8dc"

SETTINGS_FILE = "datalab_settings.json"

class DataLabView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG_DARK)
        self.controller = controller
        
        self.settings = self._load_settings()
        
        # --- EN-TÊTE ---
        f_head = tk.Frame(self, bg=BG_CARD, padx=15, pady=10)
        f_head.pack(fill="x", pady=(0, 2))
        
        self.lbl_title = tk.Label(f_head, text="🎛️ DATA LABORATORY", bg=BG_CARD, fg=TXT_MAIN, font=("Segoe UI", 12, "bold"))
        self.lbl_title.pack(side="left")
        
        tk.Label(f_head, text="(Select active inputs for Bias & Map)", bg=BG_CARD, fg=TXT_DIM, font=("Segoe UI", 9)).pack(side="left", padx=10)
        
        tk.Button(f_head, text="RESET DEFAULTS", command=self._reset_defaults, bg="#eceff1", font=("Segoe UI", 8)).pack(side="right")

        # --- TABLEAU MATRICE ---
        cols = ("name", "val", "weight", "act", "bias", "mag", "map")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=25)
        
        self.tree.heading("name",   text="CATEGORY / SIGNAL", anchor="w")
        self.tree.heading("val",    text="LIVE RESULT", anchor="c")
        self.tree.heading("weight", text="SCORE", anchor="c")
        self.tree.heading("act",    text="ON", anchor="c")
        self.tree.heading("bias",   text="-> BIAS", anchor="c")
        self.tree.heading("mag",    text="-> MAG", anchor="c")
        self.tree.heading("map",    text="-> MAP", anchor="c")
        
        self.tree.column("name",   width=180, anchor="w")
        self.tree.column("val",    width=200, anchor="c") 
        self.tree.column("weight", width=60, anchor="c")
        self.tree.column("act",    width=40, anchor="c")
        self.tree.column("bias",   width=60, anchor="c")
        self.tree.column("mag",    width=60, anchor="c")
        self.tree.column("map",    width=60, anchor="c")
        
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tree.tag_configure("checked", foreground=COL_ACTIVE, font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("unchecked", foreground=COL_INACTIVE)
        self.tree.tag_configure("cat_patterns", background="#e3f2fd", foreground="#0d47a1", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("cat_struct", background="#f3e5f5", foreground="#4a148c", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("cat_session", background="#fff3e0", foreground="#e65100", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("sep", background="#263238", foreground="white", font=("Segoe UI", 9, "bold"))

        self.tree.bind("<Button-1>", self._on_click)

        # --- LISTE ORGANISÉE PAR CATÉGORIE ---
        self.items_map = [
            # 1. CANDLE PATTERNS
            ("SEP_1", "--- CANDLE PATTERNS ---", None, 0),
            ("PAT_M1",        "M1 Pattern (Scalp)",  "M1", 0.5),
            ("PAT_M5",        "M5 Pattern",          "M5", 1.0),
            ("PAT_M15",       "M15 Pattern",         "M15", 2.0),
            ("PAT_M30",       "M30 Pattern",         "M30", 3.0),
            ("PAT_H1",        "H1 Pattern",          "H1", 4.0),
            ("PAT_H4",        "H4 Structure",        "H4", 6.0),
            ("PAT_D1",        "Daily Structure",     "D1", 8.0),

            # 2. STRUCTURE & FVG
            ("SEP_2", "--- FVG / ZONES ---", None, 0),
            ("FVG_M1",        "M1 FVG Zones",        "M1", 0.5),
            ("FVG_M5",        "M5 FVG Zones",        "M5", 1.0),
            ("FVG_M15",       "M15 FVG Zones",       "M15", 1.5),
            ("FVG_M30",       "M30 FVG Zones",       "M30", 2.0),
            ("FVG_H1",        "H1 FVG Zones",        "H1", 3.0),
            ("FVG_H4",        "H4 FVG Zones",        "H4", 5.0),
            ("FVG_D1",        "D1 FVG Zones",        "D1", 8.0),

            # 3. INDICATEURS
            ("SEP_3", "--- INDICATORS ---", None, 0),
            ("RSI_M1",        "M1 RSI",              "M1", 0.5),
            ("RSI_M5",        "M5 RSI",              "M5", 1.0),
            ("EMA_20_M5",     "M5 EMA 20",           "M5", 1.0),
            ("RSI_M15",       "M15 RSI",             "M15", 2.0),
            ("RSI_M30",       "M30 RSI",             "M30", 3.0),
            ("RSI_H1",        "H1 RSI",              "H1", 4.0),
            ("VWAP",          "Session VWAP",        "Aggr", 3.0),

            # 4. SESSION LEVELS
            ("SEP_4", "--- SESSION MAP ---", None, 0),
            ("RTH_OPEN",      "RTH Open (09:30)",    "Sess", 0),
            ("RTH_CLOSE",     "RTH Close (16:00)",   "Sess", 0),
            ("GAP_RTH",       "Gap RTH",             "Sess", 0),
            ("SETTLEMENT",    "Settlement (17:00)",  "Sess", 0),
            ("GAP_MAINT",     "Gap Maintenance",     "Sess", 0),
            ("GLOBEX_OPEN",   "Globex Open (18:00)", "Sess", 0),
            ("DAY_HIGH",      "Day High (Break)",    "Sess", 5.0),
            ("DAY_LOW",       "Day Low (Break)",     "Sess", 5.0),
        ]

        self._ensure_defaults()
        self._auto_refresh()

    def _ensure_defaults(self):
        changed = False
        for item in self.items_map:
            key = item[0]
            if "SEP_" in key: continue
            if key not in self.settings:
                bias = True if "PAT" in key or "RSI" in key or "EMA" in key or "VWAP" in key or "DAY_" in key else False
                mag = True if "FVG" in key or "RTH" in key or "GAP" in key or "SETT" in key else False
                map_ = True
                if "M1" in key: map_ = False 
                self.settings[key] = {"act": True, "bias": bias, "mag": mag, "map": map_}
                changed = True
        if changed: self._save_settings()

    def _reset_defaults(self):
        self.settings = {}
        self._ensure_defaults()
        self._update_table()

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f: return json.load(f)
            except: return {}
        return {}

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f: json.dump(self.settings, f, indent=4)
        except: pass

    def _get_live_data(self, key, source, sym):
        analyzer = self.controller.analyzer
        aggregator = self.controller.aggregator
        radar = analyzer.get_radar_snapshot(sym)
        
        val_str = "---"
        raw_val = None 
        
        if source == "Aggr":
            if key == "VWAP":
                v = aggregator.get_rolling_vwap(sym, 60)
                if v: val_str = f"{v:.2f}"; raw_val = v
        
        elif source == "Sess":
            sess = radar.get("SESSION", {})
            k_map = {
                "RTH_OPEN": "RTH Open", "RTH_CLOSE": "RTH Close",
                "GLOBEX_OPEN": "Globex Open", "SETTLEMENT": "Settlement",
                "DAY_HIGH": "Day High", "DAY_LOW": "Day Low",
                "GAP_RTH": "Gap RTH", "GAP_MAINT": "Gap Maint"
            }
            if key in k_map:
                raw = sess.get(k_map[key])
                if raw is not None:
                    raw_val = raw
                    if "GAP" in key: val_str = f"{raw:+.2f}"
                    else: val_str = f"{raw:.2f}"

        elif source in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
            tf_data = radar.get(source, {})
            if "RSI" in key:
                r = tf_data.get("rsi")
                if r: val_str = f"{r:.1f}"; raw_val = r
            elif "EMA" in key:
                e = tf_data.get("ema_20")
                if e: val_str = f"{e:.2f}"; raw_val = e
            elif "FVG" in key:
                fvgs = tf_data.get("fvgs", [])
                if fvgs:
                    # Compter Bull/Bear
                    nb_bull = sum(1 for f in fvgs if f['type']=="BULL" and not f.get('mitigated', False))
                    nb_bear = sum(1 for f in fvgs if f['type']=="BEAR" and not f.get('mitigated', False))
                    val_str = f"{nb_bull} Bull | {nb_bear} Bear"
                    # Pour le score, on passe un tuple (bull, bear)
                    raw_val = (nb_bull, nb_bear)
                else:
                    val_str = "0 Zones"
                    raw_val = (0, 0)
            elif "PAT" in key:
                pats = tf_data.get("patterns", [])
                if pats:
                    names = [p.get("name", "?").replace("(Live)", "") for p in pats]
                    val_str = " | ".join(names)
                    raw_val = pats[-1].get("side") 
                else:
                    val_str = "None"

        return val_str, raw_val

    def _calculate_display_weight(self, key, base_weight, raw_val, cfg):
        if not cfg.get("bias", False): return "(0.0)"
        if base_weight == 0: return ""
        
        score = 0.0
        
        if "PAT" in key and raw_val:
            if raw_val == "BULL": score = base_weight * 1.5
            elif raw_val == "BEAR": score = -base_weight * 1.5
            
        elif "FVG" in key and raw_val:
            # raw_val = (nb_bull, nb_bear)
            nb_bull, nb_bear = raw_val
            score = (nb_bull * base_weight) - (nb_bear * base_weight)

        elif "RSI" in key and raw_val:
            rsi = float(raw_val)
            if rsi > 60: score = base_weight
            elif rsi < 40: score = -base_weight
            
        elif "DAY_" in key:
            return f"±{base_weight:.1f}"
            
        if score == 0: return "(0.0)"
        return f"{score:+.1f}"

    def _update_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        current_sym = getattr(self.controller, "active_symbol", None)
        if not current_sym:
            syms = list(self.controller.contracts_map.keys())
            if syms: current_sym = syms[0]
            else: return
            
        self.lbl_title.config(text=f"🎛️ DATA LABORATORY [{current_sym}]")

        for item in self.items_map:
            key, label, src, base_w = item
            
            if "SEP_" in key:
                self.tree.insert("", "end", values=(label, "", "", "", "", "", ""), tags=("sep",))
                continue

            cfg = self.settings.get(key, {})
            val_str, raw_val = self._get_live_data(key, src, current_sym)
            w_display = self._calculate_display_weight(key, base_w, raw_val, cfg)
            
            act = "☑" if cfg.get("act", True) else "☐"
            bias = "☑" if cfg.get("bias", False) else "☐"
            mag = "☑" if cfg.get("mag", False) else "☐"
            map_ = "☑" if cfg.get("map", False) else "☐"
            
            row_tag = "normal"
            if "PAT" in key: row_tag = "cat_patterns"
            elif "FVG" in key: row_tag = "cat_struct"
            elif "RTH" in key or "GAP" in key: row_tag = "cat_session"
            
            self.tree.insert("", "end", values=(label, val_str, w_display, act, bias, mag, map_), tags=(key, row_tag))

    def _on_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        tags = self.tree.item(item_id, "tags")
        if not tags: return
        key = tags[0]
        if "SEP_" in key: return 
        
        col_idx = int(col.replace("#", "")) - 1
        setting_key = None
        if col_idx == 3: setting_key = "act"
        elif col_idx == 4: setting_key = "bias"
        elif col_idx == 5: setting_key = "mag"
        elif col_idx == 6: setting_key = "map"
        
        if setting_key:
            current = self.settings[key].get(setting_key, False)
            self.settings[key][setting_key] = not current
            self._save_settings()
            self._update_table()

    def _auto_refresh(self):
        self._update_table()
        self.after(1000, self._auto_refresh)