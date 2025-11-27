# ui/book.py
import tkinter as tk
from tkinter import ttk
import time
import math
from ui.panels import UnifiedControlPanel
from core.vbp_core import compute_zone_ticks_exact, compute_zone_pct_contiguous
import config

# --- PALETTE "SNIPER PRO" ---
COLOR_BG_APP       = "#f0f2f5"
COLOR_BG_WIDGET    = "#ffffff"
COLOR_FG_TEXT      = "#263238"
COLOR_FG_MUTED     = "#90a4ae"
COLOR_BORDER       = "#cfd8dc"

# Couleurs Contextuelles (Radar) - FONCÉES POUR VISIBILITÉ
COL_FVG_BULL_BG = "#81c784" # Vert Moyen
COL_FVG_BEAR_BG = "#e57373" # Rouge Moyen
COL_SESSION_LVL = "#0288d1" # Bleu
COL_MAGNET_UP   = "#d32f2f" # Rouge Vif (Target Haute)
COL_MAGNET_DN   = "#388e3c" # Vert Vif (Target Basse)

# Couleurs Background pour colonne Delta (Magnets) - TRES VISIBLES
COL_BG_MAGNET_UP = "#d32f2f" # Fond Rouge Foncé
COL_BG_MAGNET_DN = "#388e3c" # Fond Vert Foncé

BG_NQ_ACTIVE = "#006064" 
FG_NQ_HEADER = "#004d40"
BG_ES_ACTIVE = "#37474f"
FG_ES_HEADER = "#263238"
FG_INACTIVE  = "#b0bec5"

PALETTE_SUP = ["#e8f5e9", "#c8e6c9", "#a5d6a7", "#81c784", "#66bb6a", "#4caf50", "#43a047", "#388e3c", "#2e7d32", "#1b5e20"]
PALETTE_RES = ["#ffebee", "#ffcdd2", "#ef9a9a", "#e57373", "#ef5350", "#f44336", "#e53935", "#d32f2f", "#c62828", "#b71c1c"]

ZONE_BG_COLOR   = "#e3f2fd"
SL_BG_COLOR     = "#ffcdd2" 

def _safe_snap(val, step):
    if step <= 0: return val
    try:
        r = round(val / step) * step
        return float(f"{r:.6f}")
    except: return val

def _safe_int(val):
    if val is None: return 0
    try:
        f = float(val)
        if math.isnan(f): return 0
        return int(f)
    except:
        return 0

class MultiHorizonWidget(ttk.Frame):
    def __init__(self, parent, controller, symbol):
        super().__init__(parent)
        self.controller = controller
        self.aggr = controller.get_aggregator()
        self.sym = symbol
        self.tick_size = controller.get_tick_size(symbol)
        
        self.style = ttk.Style()
        self._configure_styles()

        if "NQ" in symbol:
            self.ticker_bg_color = BG_NQ_ACTIVE
            self.header_fg = FG_NQ_HEADER
        else:
            self.ticker_bg_color = BG_ES_ACTIVE
            self.header_fg = FG_ES_HEADER

        self.is_active = True
        self._anchor_price = None
        self.was_in_zone = False
        self._last_user_scroll = 0.0
        self._scroll_timeout = 15.0
        self.headers_labels = {}
        
        self.current_display_prices = []
        
        self._setup_ui()

    def _configure_styles(self):
        self.style.configure("Day.Treeview", 
            background=COLOR_BG_WIDGET,
            foreground=COLOR_FG_TEXT,
            fieldbackground=COLOR_BG_WIDGET,
            borderwidth=0,
            rowheight=18, 
            font=("Segoe UI", 9)
        )
        self.style.configure("Day.Treeview.Heading", font=("Segoe UI", 1)) 
        self.style.map("Day.Treeview", background=[("selected", "#eceff1")])

    def _setup_ui(self):
        main_frame = tk.Frame(self, bg=COLOR_BORDER, padx=1, pady=1)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        inner_frame = tk.Frame(main_frame, bg=COLOR_BG_APP)
        inner_frame.pack(fill="both", expand=True)

        self.panel = UnifiedControlPanel(inner_frame, self.controller, self.sym)
        self.panel.pack(fill="x", pady=0)
        
        info_frame = tk.Frame(inner_frame, bg=COLOR_BG_APP)
        info_frame.pack(fill="x", pady=2)
        self.lbl_info = tk.Label(info_frame, text="Init...", font=("Segoe UI", 9), bg=COLOR_BG_APP, fg=COLOR_FG_TEXT)
        self.lbl_info.pack(side="left", padx=5)

        legend = tk.Frame(info_frame, bg=COLOR_BG_APP)
        legend.pack(side="right", padx=5)
        
        tk.Label(legend, text="CONTEXT:", bg=COLOR_BG_APP, fg=COLOR_FG_MUTED, font=("Segoe UI", 7)).pack(side="left")
        tk.Label(legend, text="FVG+", bg=COL_FVG_BULL_BG, fg="black", font=("Segoe UI", 7)).pack(side="left", padx=1)
        tk.Label(legend, text="FVG-", bg=COL_FVG_BEAR_BG, fg="black", font=("Segoe UI", 7)).pack(side="left", padx=1)
        tk.Label(legend, text="🧲 TARGET", fg=COL_MAGNET_UP, bg=COLOR_BG_APP, font=("Segoe UI", 7, "bold")).pack(side="left", padx=1)

        f_data = tk.Frame(inner_frame, bg=COLOR_BG_APP)
        f_data.pack(fill="both", expand=True)

        for i in range(8): f_data.grid_columnconfigure(i, weight=1)
        f_data.grid_columnconfigure(4, weight=0) 
        f_data.grid_columnconfigure(5, weight=0) 
        f_data.grid_columnconfigure(6, weight=0) 
        f_data.grid_rowconfigure(1, weight=1) 

        def _add_header(col_idx, key, default_text, align, color=COLOR_FG_MUTED):
            lbl = tk.Label(f_data, text=default_text, bg=COLOR_BG_APP, fg=color, font=("Segoe UI", 8, "bold"), anchor=align)
            lbl.grid(row=0, column=col_idx, sticky="ew", padx=1)
            if key: self.headers_labels[key] = lbl
            return lbl

        _add_header(0, "S", "1m", "e")
        _add_header(1, "M", "5m", "e")
        _add_header(2, "L", "15m", "e")
        _add_header(3, "XL", "60m", "e")
        
        _add_header(4, None, "BID", "e")
        self.lbl_price_header = _add_header(5, None, f"{self.sym}", "center", self.header_fg)
        self.lbl_price_header.config(font=("Segoe UI", 9, "bold"))
        self.lbl_price_header.bind("<Button-1>", self._toggle_active)
        self.lbl_price_header.bind("<Double-1>", self._center_view)

        _add_header(6, None, "ASK", "w")
        _add_header(7, None, "DELTA/MAG", "w")

        def _make_tree_grid(col_idx, width, anchor, stretch=True):
            t = ttk.Treeview(f_data, columns=("val",), show="", selectmode="none", height=30, style="Day.Treeview")
            t.column("val", width=width, anchor=anchor)
            t.column("#0", width=0, stretch=False)
            t.grid(row=1, column=col_idx, sticky="nsew")
            return t

        def _make_price_tree_grid(col_idx, width):
            t = ttk.Treeview(f_data, columns=("px",), show="", selectmode="none", height=30, style="Day.Treeview")
            t.column("px", width=width, anchor="center")
            t.column("#0", width=0, stretch=False)
            t.bind("<Button-3>", self._on_right_click)
            t.bind("<Double-1>", self._center_view) 
            t.grid(row=1, column=col_idx, sticky="nsew")
            return t

        self.tree_S  = _make_tree_grid(0, 40, "e")
        self.tree_M  = _make_tree_grid(1, 40, "e")
        self.tree_L  = _make_tree_grid(2, 40, "e")
        self.tree_XL = _make_tree_grid(3, 45, "e")
        
        self.tree_Bid  = _make_tree_grid(4, 50, "e", stretch=False) 
        self.tree_Bid.bind("<Button-1>", lambda e: self._on_dom_click(e, "BUY"))

        self.tree_P    = _make_price_tree_grid(5, 100)
        
        self.tree_Ask  = _make_tree_grid(6, 50, "w", stretch=False) 
        self.tree_Ask.bind("<Button-1>", lambda e: self._on_dom_click(e, "SELL"))

        self.tree_Delta= _make_tree_grid(7, 60, "w")

        sb = ttk.Scrollbar(f_data, orient="vertical", command=self._sync_scroll)
        sb.grid(row=1, column=8, sticky="ns")
        
        self.trees = [self.tree_S, self.tree_M, self.tree_L, self.tree_XL, self.tree_Bid, self.tree_P, self.tree_Ask, self.tree_Delta]
        
        for t in self.trees:
            t.config(yscrollcommand=sb.set)
            t.bind("<MouseWheel>", self._on_wheel)
            if t != self.tree_Bid and t != self.tree_Ask:
                t.bind("<Button-1>", self._on_user_interact)
            t.bind("<B1-Motion>", self._on_user_interact)
            self._init_tags(t)

    def _toggle_active(self, event):
        self.is_active = not self.is_active
        col = self.header_fg if self.is_active else FG_INACTIVE
        self.lbl_price_header.config(fg=col)
        self.update_data()

    def _on_user_interact(self, event):
        self._last_user_scroll = time.time()
        
    def _center_view(self, event=None):
        self._last_user_scroll = 0
        self._anchor_price = None
        self.update_data()

    def _on_dom_click(self, event, action):
        self._last_user_scroll = time.time() 
        tree = event.widget
        region = tree.identify("region", event.x, event.y)
        if region != "cell": return
        row_id = tree.identify_row(event.y)
        if not row_id: return
        try:
            index = tree.index(row_id)
            if 0 <= index < len(self.current_display_prices):
                price = self.current_display_prices[index]
                try: qty = float(self.panel.qty_var.get())
                except: qty = 1
                try: sl = int(self.panel.sl_var.get())
                except: sl = 10
                try: tp = int(self.panel.tp_var.get())
                except: tp = 20
                self.controller.place_limit_order(self.sym, action, price, qty, sl, tp)
        except Exception as e:
            print(f"Click Error: {e}")

    def _on_right_click(self, event):
        region = self.tree_P.identify("region", event.x, event.y)
        if region != "cell": return
        item_id = self.tree_P.identify_row(event.y)
        if not item_id: return
        vals = self.tree_P.item(item_id, "values")
        if not vals: return
        try: 
            price_str = vals[0].split()[0]
            clicked_price = float(price_str)
        except: return
        menu = tk.Menu(self.tree_P, tearoff=0, bg="white", fg="#333")
        menu.add_command(label=f"Action @ {clicked_price:.2f}", state="disabled")
        menu.add_separator()
        menu.add_command(label="Déplacer STOP", command=lambda: self.controller.modify_order_price(self.sym, "SL", clicked_price), foreground="red")
        menu.add_command(label="Déplacer TP", command=lambda: self.controller.modify_order_price(self.sym, "TP", clicked_price), foreground="blue")
        menu.tk_popup(event.x_root, event.y_root)

    def _init_tags(self, tree):
        tree.tag_configure("normal", foreground=COLOR_FG_TEXT)
        # Heatmap Volume
        for i, c in enumerate(PALETTE_SUP): 
            fg = "white" if i > 4 else COLOR_FG_TEXT
            tree.tag_configure(f"sup{i}", background=c, foreground=fg)
        for i, c in enumerate(PALETTE_RES): 
            fg = "white" if i > 4 else COLOR_FG_TEXT
            tree.tag_configure(f"res{i}", background=c, foreground=fg)
        
        # Trading Tags
        tree.tag_configure("delta_pos", foreground="#2e7d32") 
        tree.tag_configure("delta_neg", foreground="#c62828") 
        tree.tag_configure("absorb_bid", foreground="#6a1b9a", font=("Segoe UI", 9, "bold")) 
        tree.tag_configure("absorb_ask", foreground="#e65100", font=("Segoe UI", 9, "bold")) 
        tree.tag_configure("imbalance", foreground="#0277bd", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("ENTRY", background="#a5d6a7", foreground="white", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("SL", background="#ef9a9a", foreground="#b71c1c", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("TP", background="#90caf9", foreground="#0d47a1")
        tree.tag_configure("GHOST_SL", background=SL_BG_COLOR, foreground="black", font=("Segoe UI", 9))
        
        tree.tag_configure("last_active", background=self.ticker_bg_color, foreground="white", font=("Segoe UI", 9))
        tree.tag_configure("last_inactive", background="#cfd8dc", foreground="#546e7a", font=("Segoe UI", 9))
        tree.tag_configure("zone", background=ZONE_BG_COLOR)
        
        tree.tag_configure("p_active", foreground="#212121", font=("Segoe UI", 9))
        tree.tag_configure("p_inactive", foreground="#b0bec5", font=("Segoe UI", 9))
        tree.tag_configure("dom_bid", foreground="#1565c0", font=("Segoe UI", 9)) 
        tree.tag_configure("dom_ask", foreground="#c62828", font=("Segoe UI", 9)) 

        # --- TAGS RADAR & MAGNETS ---
        tree.tag_configure("fvg_bull", background=COL_FVG_BULL_BG) 
        tree.tag_configure("fvg_bear", background=COL_FVG_BEAR_BG) 
        tree.tag_configure("lvl_session", foreground=COL_SESSION_LVL, font=("Segoe UI", 9, "bold"))
        
        # Magnets Text (Colonne Prix)
        tree.tag_configure("magnet_up", foreground=COL_MAGNET_UP, font=("Segoe UI", 9, "bold"))
        tree.tag_configure("magnet_dn", foreground=COL_MAGNET_DN, font=("Segoe UI", 9, "bold"))

        # Magnets BG (Colonne Delta) - COULEURS FORTES + TEXTE BLANC
        tree.tag_configure("bg_magnet_up", background=COL_BG_MAGNET_UP, foreground="white", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("bg_magnet_dn", background=COL_BG_MAGNET_DN, foreground="white", font=("Segoe UI", 9, "bold"))


    def _sync_scroll(self, *args):
        for t in self.trees: t.yview(*args)
    
    def _on_wheel(self, event):
        self._last_user_scroll = time.time()
        d = int(-1*(event.delta/120))
        for t in self.trees: t.yview_scroll(d, "units")
        return "break"

    def _group_data(self, vbp, delta_map, factor):
        if factor <= 1: return vbp, delta_map
        g_vol, g_delta = {}, {}
        block = self.tick_size * factor
        for p, vol in vbp.items():
            p_grp = _safe_snap(p, block)
            g_vol[p_grp] = g_vol.get(p_grp, 0) + vol
            g_delta[p_grp] = g_delta.get(p_grp, 0) + delta_map.get(p, 0)
        return g_vol, g_delta

    def update_data(self):
        try:
            saved_yview = self.tree_P.yview()
            last_p = self.aggr.get_last_price(self.sym)
            if not last_p: return
            
            spd = self.controller.get_market_speed(self.sym)
            icon = "●" if self.is_active else "○"
            col_icon = self.ticker_bg_color if self.is_active else "#cfd8dc"
            self.lbl_info.config(text=f"{icon} {self.sym} | {last_p:.2f} | {_safe_int(spd)}/m", fg=col_icon)
            
            try: grp = int(self.panel.group_var.get())
            except: grp = 1
            effective_tick = self.tick_size * grp
            last_p_grp = _safe_snap(last_p, effective_tick)

            # --- RECUPERATION DONNEES RADAR ---
            radar_ctx = self.controller.get_context(self.sym) or {}
            
            # 1. FVG Zones (Pour colorer le background)
            fvg_zones = []   
            
            # 2. Magnets (Pour les icônes)
            magnet_levels = {} # { price_snap: ("Symbol", "Tag") }
            
            # Parsing FVG
            for tf in ["M15", "H1"]:
                d = radar_ctx.get(tf, {})
                for fvg in d.get("fvgs", []):
                    fvg_zones.append((fvg['top'], fvg['bot'], fvg['type']))
                    
                    snap_top = _safe_snap(fvg['top'], effective_tick)
                    snap_bot = _safe_snap(fvg['bot'], effective_tick)
                    
                    # Magnet Rouge pour Resistance (Top), Vert pour Support (Bot)
                    magnet_levels[snap_top] = ("🧲", "magnet_up" if fvg['type']=="BEAR" else "magnet_dn")
                    magnet_levels[snap_bot] = ("🧲", "magnet_dn" if fvg['type']=="BULL" else "magnet_up")

            # Parsing Session Levels
            sess = radar_ctx.get("SESSION", {})
            for k, v in sess.items():
                if v and isinstance(v, (int, float)) and k != "Gap":
                    snap_v = _safe_snap(v, effective_tick)
                    # Ex: Day High = Magnet Rouge, Day Low = Magnet Vert
                    tag = "magnet_up" if "High" in k else ("magnet_dn" if "Low" in k else "lvl_session")
                    magnet_levels[snap_v] = (k, tag)

            # Parsing VWAP
            vwap = self.controller.aggregator.get_rolling_vwap(self.sym, 60)
            if vwap:
                snap_v = _safe_snap(vwap, effective_tick)
                magnet_levels[snap_v] = ("VWAP", "lvl_session")

            # --- PREPA VBP ---
            r_mode = self.panel.rolling_mode_var.get() 
            if r_mode == "Vol":
                params = [45000, 15000, 5000, 1000] 
                labels = ["45K", "15K", "5K", "1K"]
                mode_tag = "Vol"
            else:
                params = [60, 15, 5, 1]
                labels = ["60m", "15m", "5m", "1m"]
                mode_tag = "Time"
            
            self.headers_labels["XL"].config(text=labels[0])
            self.headers_labels["L"].config(text=labels[1])
            self.headers_labels["M"].config(text=labels[2])
            self.headers_labels["S"].config(text=labels[3])

            try:
                raw_xl, delta_xl = self.aggr.get_rolling_data(self.sym, mode_tag, params[0])
                g_xl, g_delta_xl = self._group_data(raw_xl, delta_xl, grp) 
                
                raw_l, delta_l = self.aggr.get_rolling_data(self.sym, mode_tag, params[1])
                g_l, _ = self._group_data(raw_l, delta_l, grp)
                
                raw_m, delta_m = self.aggr.get_rolling_data(self.sym, mode_tag, params[2])
                g_m, _ = self._group_data(raw_m, delta_m, grp)
                
                raw_s, delta_s = self.aggr.get_rolling_data(self.sym, mode_tag, params[3])
                g_s, _ = self._group_data(raw_s, delta_s, grp)
            except:
                g_xl, g_delta_xl, g_l, g_m, g_s = {}, {}, {}, {}, {}

            dom_data = self.aggr.dom.get(self.sym, {})
            bids_map = dom_data.get('bids', {})
            asks_map = dom_data.get('asks', {})
            
            tickers = self.controller.ib_manager.tickers()
            current_ticker = tickers.get(f"Feed_{self.sym}")
            best_bid_l1, best_ask_l1, bid_sz_l1, ask_sz_l1 = None, None, 0, 0
            has_deep_data = (len(bids_map) > 0 or len(asks_map) > 0)
            if current_ticker:
                if current_ticker.bid: 
                    best_bid_l1 = _safe_snap(current_ticker.bid, effective_tick)
                    bid_sz_l1 = _safe_int(current_ticker.bidSize) if current_ticker.bidSize else 0
                if current_ticker.ask: 
                    best_ask_l1 = _safe_snap(current_ticker.ask, effective_tick)
                    ask_sz_l1 = _safe_int(current_ticker.askSize) if current_ticker.askSize else 0

            # VBP Zone Manual
            zone_src = self.panel.zone_src_var.get()
            target_data = g_xl 
            if zone_src == "L": target_data = g_l
            elif zone_src == "M": target_data = g_m
            elif zone_src == "S": target_data = g_s
            elif zone_src == "Sess": 
                 r, _ = self._group_data(self.aggr.volume_by_price.get(self.sym, {}), {}, grp)
                 target_data = r

            zone = None
            if target_data and sum(target_data.values()) > 0:
                zone_mode = self.panel.zone_mode_var.get()
                try: zone_val = float(self.panel.zone_val_var.get())
                except: zone_val = 5
                if zone_mode == "Ticks": 
                    zone, _, _ = compute_zone_ticks_exact(target_data, effective_tick, int(zone_val))
                else: 
                    zone, _, _ = compute_zone_pct_contiguous(target_data, effective_tick, zone_val)

            # Visu Grid
            vis_rows = config.MAX_ROWS
            if self._anchor_price is None: self._anchor_price = last_p_grp
            
            if not self._last_user_scroll or (time.time() - self._last_user_scroll > self._scroll_timeout):
                dist_ticks = (last_p_grp - self._anchor_price) / effective_tick
                if abs(dist_ticks) > (vis_rows * 0.35):
                    self._anchor_price = last_p_grp
                    saved_yview = None
            
            half_rows = vis_rows // 2
            display_prices = []
            center_step = round(self._anchor_price / effective_tick)
            for i in range(half_rows, -half_rows, -1):
                p = (center_step + i) * effective_tick
                p = _safe_snap(p, effective_tick)
                display_prices.append(p)
            
            self.current_display_prices = display_prices

            # NETTOYAGE
            for t in self.trees: t.delete(*t.get_children())
            
            markers = self.controller.get_trading_markers(self.sym)
            grouped_markers = { _safe_snap(mp, effective_tick): type for mp, type in markers.items() }
            
            ghost_sl_buy, ghost_sl_sell = None, None
            has_active_pos = any(v == "ENTRY" for v in markers.values())
            if not has_active_pos:
                try:
                    sl_ticks_param = int(self.panel.sl_var.get())
                    sl_dist = sl_ticks_param * self.tick_size
                    ghost_sl_buy = _safe_snap(last_p_grp - sl_dist, effective_tick)
                    ghost_sl_sell = _safe_snap(last_p_grp + sl_dist, effective_tick)
                except: pass

            ext = self.controller.get_auction_levels(self.sym)
            high, low = ext.get("high"), ext.get("low")
            
            max_xl = max((g_xl.get(p, 0) for p in display_prices), default=1)
            max_l  = max((g_l.get(p, 0)  for p in display_prices), default=1)
            max_m  = max((g_m.get(p, 0)  for p in display_prices), default=1)
            max_s  = max((g_s.get(p, 0)  for p in display_prices), default=1)
            
            def get_heat_tags(v, mx):
                t = ["normal"]
                if v > 0:
                    inten = int((v / mx) * 9)
                    if p < last_p_grp: t.append(f"sup{inten}")
                    elif p > last_p_grp: t.append(f"res{inten}")
                    else: t.append(f"sup{inten}")
                return t

            visible_deltas = [abs(g_delta_xl.get(p, 0)) for p in display_prices]
            max_delta_vis = max(visible_deltas) if visible_deltas else 1
            if max_delta_vis == 0: max_delta_vis = 1

            for p in display_prices:
                # 1. Determine FVG / Level Context for this row
                row_tags = []
                magnet_tags = []
                
                # FVG Background
                for f_top, f_bot, f_type in fvg_zones:
                    if f_bot <= p <= f_top:
                        row_tags.append("fvg_bull" if f_type=="BULL" else "fvg_bear")
                        break 
                
                # Level Marker ?
                lvl_str = ""
                if p in magnet_levels:
                    txt, tag = magnet_levels[p]
                    lvl_str = f" {txt}"
                    row_tags.append(tag)
                    
                    # Logique pour colorer le Delta
                    if "magnet_up" in tag: magnet_tags.append("bg_magnet_up")
                    elif "magnet_dn" in tag: magnet_tags.append("bg_magnet_dn")

                # 2. VBP Columns
                vol_xl = g_xl.get(p, 0)
                vol_l = g_l.get(p, 0)
                vol_m = g_m.get(p, 0)
                vol_s = g_s.get(p, 0)
                d = g_delta_xl.get(p, 0)
                
                def _ins(tree, val, heat_tags):
                    final_tags = list(heat_tags) + row_tags
                    if zone and zone[0] <= p <= zone[1]: final_tags.append("zone")
                    tree.insert("", "end", values=(val,), tags=final_tags)

                _ins(self.tree_S, _safe_int(vol_s) if vol_s else "", get_heat_tags(vol_s, max_s))
                _ins(self.tree_M, _safe_int(vol_m) if vol_m else "", get_heat_tags(vol_m, max_m))
                _ins(self.tree_L, _safe_int(vol_l) if vol_l else "", get_heat_tags(vol_l, max_l))
                _ins(self.tree_XL, _safe_int(vol_xl) if vol_xl else "", get_heat_tags(vol_xl, max_xl))

                # 3. BID
                b_sz = 0
                if has_deep_data:
                    if grp == 1: b_sz = bids_map.get(p, 0)
                    else:
                        for sub_p in bids_map:
                            if _safe_snap(sub_p, effective_tick) == p: b_sz += bids_map[sub_p]
                if b_sz == 0 and best_bid_l1 and abs(p - best_bid_l1) < (effective_tick / 100.0): b_sz = bid_sz_l1
                
                b_tags = list(row_tags)
                if zone and zone[0] <= p <= zone[1]: b_tags.append("zone")
                
                is_absorb_bid = (vol_s > 0 and vol_s > (max_s * 0.25) and abs(d) > (vol_s * 0.5) and d < 0)
                if is_absorb_bid: b_tags.append("absorb_bid")
                else: b_tags.append("dom_bid")
                
                self.tree_Bid.insert("", "end", values=(_safe_int(b_sz) if b_sz > 0 else "",), tags=b_tags)

                # 4. PRICE
                p_tags = list(row_tags)
                is_last_row = False
                p_str = f"{p:.2f}" + lvl_str 
                tol = effective_tick / 2
                
                is_ghost = False
                if ghost_sl_buy and abs(p - ghost_sl_buy) <= tol: is_ghost = True
                elif ghost_sl_sell and abs(p - ghost_sl_sell) <= tol: is_ghost = True
                
                if is_ghost: p_tags.append("GHOST_SL")
                else:
                    if abs(p - last_p_grp) <= tol:
                        is_last_row = True
                        p_tags.append("last_active" if (self.panel.show_last_var.get() and self.is_active) else "last_inactive")
                    else:
                        p_tags.append("p_active" if self.is_active else "p_inactive")

                if p in grouped_markers: p_tags.append(grouped_markers[p])
                elif high and abs(p-high)<=tol: p_str += " H"
                elif low and abs(p-low)<=tol: p_str += " L"
                
                iid = self.tree_P.insert("", "end", values=(p_str,), tags=p_tags)
                if is_last_row: last_id = iid
                
                # 5. ASK
                a_sz = 0
                if has_deep_data:
                    if grp == 1: a_sz = asks_map.get(p, 0)
                    else:
                        for sub_p in asks_map:
                            if _safe_snap(sub_p, effective_tick) == p: a_sz += asks_map[sub_p]
                if a_sz == 0 and best_ask_l1 and abs(p - best_ask_l1) < (effective_tick / 100.0): a_sz = ask_sz_l1
                
                a_tags = list(row_tags)
                if zone and zone[0] <= p <= zone[1]: a_tags.append("zone")

                is_absorb_ask = (vol_s > 0 and vol_s > (max_s * 0.25) and abs(d) > (vol_s * 0.5) and d > 0)
                if is_absorb_ask: a_tags.append("absorb_ask")
                else: a_tags.append("dom_ask")

                if b_sz > 0 and a_sz > 0:
                    if a_sz > (b_sz * 3): a_tags.append("imbalance")
                    elif b_sz > (a_sz * 3): b_tags.append("imbalance")
                
                self.tree_Ask.insert("", "end", values=(_safe_int(a_sz) if a_sz > 0 else "",), tags=a_tags)

                # 6. DELTA + LIQUIDITY MAGNETS
                d_tags = list(row_tags)
                # On ajoute les tags de background Magnet ICI
                d_tags.extend(magnet_tags)
                
                d_tags.append("normal")
                d_str = ""
                if vol_xl > 0:
                    bar_len = int((abs(d) / max_delta_vis) * 5)
                    bar_len = min(bar_len, 5)
                    bar_char = "|" * bar_len
                    if d > 0: 
                        d_str = f"{bar_char} {_safe_int(d)}"
                        d_tags.append("delta_pos")
                    elif d < 0: 
                        d_str = f"{_safe_int(d)} {bar_char}"
                        d_tags.append("delta_neg")
                    else: d_str = "0"
                self.tree_Delta.insert("", "end", values=(d_str,), tags=d_tags)

            if saved_yview and not last_id and (time.time() - self._last_user_scroll > self._scroll_timeout):
                for t in self.trees: t.yview_moveto(saved_yview[0])
            elif last_id and (time.time() - self._last_user_scroll > self._scroll_timeout):
                for t in self.trees: t.see(last_id)

        except Exception as e:
            # print(f"UI ERROR: {e}") 
            pass