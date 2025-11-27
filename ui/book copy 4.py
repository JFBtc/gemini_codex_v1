# ui/book.py
import tkinter as tk
from tkinter import ttk
import time
import math
from ui.panels import UnifiedControlPanel
import config

# --- PALETTE ---
COLOR_BG_APP       = "#f0f2f5"
COLOR_BG_WIDGET    = "#ffffff"
COLOR_FG_TEXT      = "#263238"
COLOR_FG_MUTED     = "#90a4ae"
COLOR_BORDER       = "#cfd8dc"

# Couleurs Structurelles (Pour le DOM)
COL_SUP_BG         = "#e8f5e9" # Vert Pâle (Fond)
COL_RES_BG         = "#ffebee" # Rouge Pâle (Fond)
COL_SUP_TXT        = "#2e7d32" # Vert Foncé (Texte)
COL_RES_TXT        = "#c62828" # Rouge Foncé (Texte)

BG_NQ_ACTIVE = "#006064" 
FG_NQ_HEADER = "#004d40"
BG_ES_ACTIVE = "#37474f"
FG_ES_HEADER = "#263238"
FG_INACTIVE  = "#b0bec5"

# --- DEFINITIONS RESTAURÉES ---
SL_BG_COLOR = "#ffcdd2"  # Couleur de fond pour le Ghost SL

PALETTE_SUP = ["#e8f5e9", "#c8e6c9", "#a5d6a7", "#81c784", "#66bb6a", "#4caf50", "#43a047", "#388e3c", "#2e7d32", "#1b5e20"]
PALETTE_RES = ["#ffebee", "#ffcdd2", "#ef9a9a", "#e57373", "#ef5350", "#f44336", "#e53935", "#d32f2f", "#c62828", "#b71c1c"]

def _safe_snap(val, step):
    if step <= 0: return val
    try: return round(val / step) * step
    except: return val

def _safe_int(val):
    if val is None: return 0
    try: return int(float(val))
    except: return 0

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
        self._last_user_scroll = 0.0
        self._scroll_timeout = 15.0
        self.current_display_prices = []
        
        # On garde les variables de filtre pour l'UI, même si le DOM est piloté par le Controller
        self.show_struct = tk.BooleanVar(value=True)
        self.show_vol = tk.BooleanVar(value=True)
        
        self.trees = {} 
        self.tree_list = []
        
        self._setup_ui()

    def _configure_styles(self):
        self.style.configure("Book.Treeview", 
            background=COLOR_BG_WIDGET, foreground=COLOR_FG_TEXT,
            fieldbackground=COLOR_BG_WIDGET, borderwidth=0, rowheight=20, font=("Segoe UI", 9)
        )
        self.style.map("Book.Treeview", background=[("selected", "#eceff1")])

    def _setup_ui(self):
        main_frame = tk.Frame(self, bg=COLOR_BORDER, padx=1, pady=1)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        inner_frame = tk.Frame(main_frame, bg=COLOR_BG_APP)
        inner_frame.pack(fill="both", expand=True)

        # 1. PANNEAU DE CONTRÔLE (Ordres)
        self.panel = UnifiedControlPanel(inner_frame, self.controller, self.sym)
        self.panel.pack(fill="x", pady=0)
        
        # 2. BARRE D'OUTILS "FOCUS" (Filtres)
        f_tools = tk.Frame(inner_frame, bg=COLOR_BG_APP, pady=2)
        f_tools.pack(fill="x")
        
        cb_struct = tk.Checkbutton(f_tools, text="STRUCT", variable=self.show_struct, 
                                   bg=COLOR_BG_APP, font=("Segoe UI", 8, "bold"), 
                                   command=self.update_data, selectcolor="white")
        cb_struct.pack(side="left", padx=5)
        
        cb_vol = tk.Checkbutton(f_tools, text="VOLUME", variable=self.show_vol, 
                                bg=COLOR_BG_APP, font=("Segoe UI", 8), 
                                command=self.update_data, selectcolor="white")
        cb_vol.pack(side="left", padx=5)

        self.lbl_info = tk.Label(f_tools, text=f"{self.sym}", font=("Segoe UI", 9, "bold"), bg=COLOR_BG_APP, fg=self.ticker_bg_color)
        self.lbl_info.pack(side="right", padx=10)

        # 3. GRID DU DOM
        f_grid = tk.Frame(inner_frame, bg=COLOR_BG_APP)
        f_grid.pack(fill="both", expand=True)

        cols_cfg = [
            ("ctx", 35, "w"), ("s", 35, "e"), ("m", 35, "e"), ("l", 35, "e"),
            ("bid", 50, "e"), ("px", 90, "center"), ("ask", 50, "w"), ("delta", 50, "w")
        ]
        
        for i, (key, width, anchor) in enumerate(cols_cfg):
            f_grid.grid_columnconfigure(i, weight=0)
            
            # Header
            txt_head = key.upper() if key != "px" else self.sym
            lbl = tk.Label(f_grid, text=txt_head, font=("Segoe UI", 7, "bold"), bg=COLOR_BG_APP, fg=COLOR_FG_MUTED)
            if key == "px": 
                lbl.config(fg=self.header_fg, font=("Segoe UI", 8, "bold"))
                self.lbl_price_header = lbl
                lbl.bind("<Button-1>", self._toggle_active)
                lbl.bind("<Double-1>", self._center_view)
            lbl.grid(row=0, column=i, sticky="ew")

            t = ttk.Treeview(f_grid, columns=("v",), show="", selectmode="none", height=30, style="Book.Treeview")
            t.column("v", width=width, anchor=anchor)
            t.grid(row=1, column=i, sticky="nsew")
            
            t.bind("<MouseWheel>", self._on_wheel)
            t.bind("<B1-Motion>", self._on_user_scroll)
            t.bind("<Button-1>", self._on_user_scroll)
            
            self.trees[key] = t
            self.tree_list.append(t)
            
        sb = ttk.Scrollbar(f_grid, orient="vertical", command=self._sync_scroll)
        sb.grid(row=1, column=len(cols_cfg), sticky="ns")
        for t in self.tree_list: t.config(yscrollcommand=sb.set)

        # Bindings Spécifiques
        self.trees["px"].bind("<Double-1>", self._center_view)
        self.trees["px"].bind("<Button-3>", self._on_right_click)
        self.trees["bid"].bind("<Button-1>", lambda e: self._on_dom_click(e, "BUY"))
        self.trees["ask"].bind("<Button-1>", lambda e: self._on_dom_click(e, "SELL"))

        self._init_tags()

    def _init_tags(self):
        # Tags existants ...
        self.trees["px"].tag_configure("current", background=self.ticker_bg_color, foreground="white")
        # Trading active
        self.trees["px"].tag_configure("ENTRY", background="#a5d6a7", foreground="white", font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("SL", background="#ef9a9a", foreground="#b71c1c", font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("TP", background="#90caf9", foreground="#0d47a1")
        self.trees["px"].tag_configure("GHOST_SL", background=SL_BG_COLOR, foreground="black", font=("Segoe UI", 9))

        # Heatmap Volume
        for i, c in enumerate(PALETTE_SUP): 
            fg = "white" if i > 4 else COLOR_FG_TEXT
            self.trees["s"].tag_configure(f"sup{i}", background=c, foreground=fg)
        for i, c in enumerate(PALETTE_RES): 
            fg = "white" if i > 4 else COLOR_FG_TEXT
            self.trees["s"].tag_configure(f"res{i}", background=c, foreground=fg)
            
        # NOUVEAUX TAGS POUR LES NIVEAUX SÉLECTIONNÉS
        # Support = Fond Vert, Texte Vert Foncé
        self.trees["delta"].tag_configure("lvl_sup", background=COL_SUP_BG, foreground=COL_SUP_TXT, font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("lvl_sup_px", background=COL_SUP_BG)
        
        # Resistance = Fond Rouge, Texte Rouge Foncé
        self.trees["delta"].tag_configure("lvl_res", background=COL_RES_BG, foreground=COL_RES_TXT, font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("lvl_res_px", background=COL_RES_BG)

        # Tags DOM standard
        self.trees["bid"].tag_configure("dom_bid", foreground="#1565c0") 
        self.trees["ask"].tag_configure("dom_ask", foreground="#c62828") 
        self.trees["bid"].tag_configure("absorb_bid", foreground="#6a1b9a", font=("Segoe UI", 9, "bold")) 
        self.trees["ask"].tag_configure("absorb_ask", foreground="#e65100", font=("Segoe UI", 9, "bold")) 
        self.trees["delta"].tag_configure("delta_pos", foreground="#2e7d32")
        self.trees["delta"].tag_configure("delta_neg", foreground="#c62828")

    def _sync_scroll(self, *args):
        for t in self.tree_list: t.yview(*args)
    def _on_wheel(self, event):
        self._last_user_scroll = time.time()
        d = int(-1*(event.delta/120))
        for t in self.tree_list: t.yview_scroll(d, "units")
        return "break"
    def _on_user_scroll(self, event):
        self._last_user_scroll = time.time()
    def _toggle_active(self, event):
        self.is_active = not self.is_active
        col = self.header_fg if self.is_active else FG_INACTIVE
        self.lbl_price_header.config(fg=col)
        self.update_data()
    def _center_view(self, event=None):
        self._last_user_scroll = 0; self._anchor_price = None; self.update_data()
        
    def _on_dom_click(self, event, action):
        self._last_user_scroll = time.time() 
        tree = event.widget
        row_id = tree.identify_row(event.y)
        if not row_id: return
        try:
            index = tree.index(row_id)
            if 0 <= index < len(self.current_display_prices):
                price = self.current_display_prices[index]
                qty = float(self.panel.qty_var.get())
                sl = int(self.panel.sl_var.get())
                tp = int(self.panel.tp_var.get())
                self.controller.place_limit_order(self.sym, action, price, qty, sl, tp)
        except Exception as e: print(f"Click Error: {e}")

    def _on_right_click(self, event):
        item_id = self.trees["px"].identify_row(event.y)
        if not item_id: return
        vals = self.trees["px"].item(item_id, "values")
        if not vals: return
        try: 
            p_txt = vals[0].split()[0]
            clicked_price = float(p_txt)
        except: return
        menu = tk.Menu(self, tearoff=0, bg="white", fg="#333")
        menu.add_command(label=f"Action @ {clicked_price:.2f}", state="disabled")
        menu.add_separator()
        menu.add_command(label="Move SL Here", command=lambda: self.controller.modify_order_price(self.sym, "SL", clicked_price), foreground="red")
        menu.add_command(label="Move TP Here", command=lambda: self.controller.modify_order_price(self.sym, "TP", clicked_price), foreground="blue")
        menu.tk_popup(event.x_root, event.y_root)

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
            last_px = self.aggr.get_last_price(self.sym)
            if not last_px: return
            
            grp = int(self.panel.group_var.get()) if hasattr(self.panel, 'group_var') else 1
            eff_tick = self.tick_size * grp
            last_px_snap = _safe_snap(last_px, eff_tick)
            
            spd = self.controller.get_market_speed(self.sym)
            icon = "●" if self.is_active else "○"
            self.lbl_info.config(text=f"{icon} {self.sym} | {last_px:.2f} | {_safe_int(spd)}/m")

            if self._anchor_price is None or (time.time() - self._last_user_scroll > self._scroll_timeout):
                 if self._anchor_price:
                     dist = abs(last_px_snap - self._anchor_price) / eff_tick
                     if dist > 15: self._anchor_price = last_px_snap
                 else: self._anchor_price = last_px_snap

            # --- RECUPERATION DES NIVEAUX COCHÉS PAR L'UTILISATEUR ---
            # C'est la seule source de vérité pour l'affichage des niveaux custom
            # Cela remplace toute la logique "intelligente" précédente
            user_levels = []
            if self.show_struct.get():
                user_levels = self.controller.get_dom_levels(self.sym)
            
            # On les indexe par prix pour un accès rapide
            levels_map = {} 
            for lvl in user_levels:
                # On snap le niveau sur la grille actuelle
                p_snap = _safe_snap(lvl['price'], eff_tick)
                levels_map[p_snap] = lvl # {type: 'sup', label: '...'}

            # --- DATA VOL & DOM ---
            vol_data = {"s": {}, "m": {}, "l": {}}
            delta_data = {}
            max_vol = 1
            if self.show_vol.get():
                try:
                    r_s, d_s = self.aggr.get_rolling_data(self.sym, "Time", 5)
                    r_m, _   = self.aggr.get_rolling_data(self.sym, "Time", 30)
                    r_l, _   = self.aggr.get_rolling_data(self.sym, "Vol", 10000)
                    g_s, gd_s = self._group_data(r_s, d_s, grp)
                    g_m, _    = self._group_data(r_m, {}, grp)
                    g_l, _    = self._group_data(r_l, {}, grp)
                    vol_data = {"s": g_s, "m": g_m, "l": g_l}
                    delta_data = gd_s
                    all_vals = list(g_s.values()) + list(g_m.values()) + list(g_l.values())
                    if all_vals: max_vol = max(all_vals)
                except: pass

            dom = self.aggr.dom.get(self.sym, {})
            bids = dom.get('bids', {}); asks = dom.get('asks', {})
            
            # --- RENDU ---
            rows = 40
            center_step = round(self._anchor_price / eff_tick)
            for t in self.tree_list: t.delete(*t.get_children())
            
            markers = self.controller.get_trading_markers(self.sym)
            
            for i in range(rows // 2, -rows // 2, -1):
                p = _safe_snap((center_step + i) * eff_tick, eff_tick)
                
                # 1. CTX (Vide ou Icône)
                self.trees["ctx"].insert("", "end", values=("",))

                # 2. PRICE
                p_str = f"{p:.2f}"
                p_tags = []
                if abs(p - last_px_snap) < (eff_tick/10): p_tags.append("current")
                
                # Trading Markers
                if p in markers: p_tags.append(markers[p]) 
                
                # Highlight si niveau sélectionné (Background)
                if p in levels_map:
                    lvl_info = levels_map[p]
                    if lvl_info['type'] == 'sup': p_tags.append("lvl_sup_px")
                    else: p_tags.append("lvl_res_px")

                self.trees["px"].insert("", "end", values=(p_str,), tags=tuple(p_tags))

                # 3. VOLUMES
                for k in ["s", "m", "l"]:
                    v = vol_data[k].get(p, 0)
                    v_str = _safe_int(v) if v > 0 else ""
                    tags = []
                    if v > 0:
                        intensity = min(9, int((v / max_vol) * 9))
                        tags.append(f"vol_{intensity}")
                    self.trees[k].insert("", "end", values=(v_str,), tags=tuple(tags))

                # 4. DOM (Bid/Ask)
                b_sz = 0; a_sz = 0
                if grp == 1: b_sz = bids.get(p, 0); a_sz = asks.get(p, 0)
                else: 
                    for bp, bz in bids.items(): 
                        if abs(bp - p) < (eff_tick/2): b_sz += bz
                    for ap, az in asks.items(): 
                        if abs(ap - p) < (eff_tick/2): a_sz += az
                
                # Absorption / Dom logic
                b_tag = "dom_bid"; a_tag = "dom_ask"
                d_val = delta_data.get(p, 0)
                if vol_data["s"].get(p,0) > (max_vol*0.3):
                    if d_val < 0 and abs(d_val) > (vol_data["s"].get(p,0)*0.6): b_tag = "absorb_bid"
                    if d_val > 0 and abs(d_val) > (vol_data["s"].get(p,0)*0.6): a_tag = "absorb_ask"

                self.trees["bid"].insert("", "end", values=(_safe_int(b_sz) if b_sz else "",), tags=(b_tag,))
                self.trees["ask"].insert("", "end", values=(_safe_int(a_sz) if a_sz else "",), tags=(a_tag,))

                # 5. DELTA / LEVELS
                # C'est ici qu'on affiche les labels des niveaux choisis
                d_str = ""
                d_tags = []
                
                if p in levels_map:
                    lvl_info = levels_map[p]
                    d_str = lvl_info['label'] # Affiche le nom (ex: "M5 Sweep")
                    if lvl_info['type'] == 'sup': d_tags.append("lvl_sup")
                    else: d_tags.append("lvl_res")
                else:
                    # Affichage Delta normal si pas de niveau
                    if d_val != 0: 
                        d_str = f"{_safe_int(d_val)}"
                        d_tags.append("delta_pos" if d_val > 0 else "delta_neg")

                self.trees["delta"].insert("", "end", values=(d_str,), tags=tuple(d_tags))

            if self._last_user_scroll > 0 and (time.time() - self._last_user_scroll < self._scroll_timeout): pass
            else:
                 mid_item = self.trees["px"].get_children()[rows//2]
                 for t in self.tree_list: t.see(mid_item)

        except Exception as e: pass