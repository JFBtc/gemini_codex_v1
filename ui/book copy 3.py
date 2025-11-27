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

# Couleurs Structurelles (Nouvelle Palette)
COL_MAGNET_UP      = "#d32f2f" # Rouge Vif
COL_MAGNET_DN      = "#388e3c" # Vert Vif
COL_SESSION_LVL    = "#1565c0" # Bleu Session
COL_FVG_BULL       = "#e8f5e9" # Fond Vert très pâle (Zone)
COL_FVG_BEAR       = "#ffebee" # Fond Rouge très pâle (Zone)

# Couleurs Background pour colonne Delta (Legacy)
COL_BG_MAGNET_UP = "#d32f2f" 
COL_BG_MAGNET_DN = "#388e3c"

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
        self._last_user_scroll = 0.0
        self._scroll_timeout = 15.0
        self.current_display_prices = []
        
        # --- FILTRES DE VISIBILITÉ ---
        self.show_struct = tk.BooleanVar(value=True)
        self.show_vol = tk.BooleanVar(value=True)
        
        self.trees = {} # Dictionnaire pour accès facile
        
        self._setup_ui()

    def _configure_styles(self):
        # Style épuré pour le Book
        self.style.configure("Book.Treeview", 
            background=COLOR_BG_WIDGET,
            foreground=COLOR_FG_TEXT,
            fieldbackground=COLOR_BG_WIDGET,
            borderwidth=0,
            rowheight=20, # Un poil plus grand pour la lisibilité
            font=("Segoe UI", 9)
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
        
        # Checkbox: STRUCT (Affiche/Masque la colonne Contexte)
        cb_struct = tk.Checkbutton(f_tools, text="STRUCT", variable=self.show_struct, 
                                   bg=COLOR_BG_APP, font=("Segoe UI", 8, "bold"), 
                                   command=self.update_data, selectcolor="white")
        cb_struct.pack(side="left", padx=5)
        
        # Checkbox: VOLUME (Affiche/Masque les colonnes S/M/L)
        cb_vol = tk.Checkbutton(f_tools, text="VOLUME", variable=self.show_vol, 
                                bg=COLOR_BG_APP, font=("Segoe UI", 8), 
                                command=self.update_data, selectcolor="white")
        cb_vol.pack(side="left", padx=5)

        # Info Label (Prix actuel)
        self.lbl_info = tk.Label(f_tools, text=f"{self.sym}", font=("Segoe UI", 9, "bold"), bg=COLOR_BG_APP, fg=self.ticker_bg_color)
        self.lbl_info.pack(side="right", padx=10)

        # 3. GRID DU DOM
        f_grid = tk.Frame(inner_frame, bg=COLOR_BG_APP)
        f_grid.pack(fill="both", expand=True)

        # Définition des colonnes : CTX | S | M | L | BID | PX | ASK | DELTA
        # On enlève XL pour faire de la place à CTX
        cols_cfg = [
            ("ctx", 35, "w"),   # Contexte (Structure)
            ("s", 35, "e"),     # Vol 1m
            ("m", 35, "e"),     # Vol 5m
            ("l", 35, "e"),     # Vol 15m
            ("bid", 50, "e"),   # Bid DOM
            ("px", 90, "center"), # Prix
            ("ask", 50, "w"),   # Ask DOM
            ("delta", 50, "w")  # Delta
        ]
        
        self.tree_list = [] # Pour le scroll synchrone

        for i, (key, width, anchor) in enumerate(cols_cfg):
            f_grid.grid_columnconfigure(i, weight=0)
            
            # Header
            txt_head = key.upper() if key != "px" else self.sym
            lbl = tk.Label(f_grid, text=txt_head, font=("Segoe UI", 7, "bold"), bg=COLOR_BG_APP, fg=COLOR_FG_MUTED)
            if key == "px": 
                lbl.config(fg=self.header_fg, font=("Segoe UI", 8, "bold"))
                self.lbl_price_header = lbl # Garder réf pour toggle active
                lbl.bind("<Button-1>", self._toggle_active)
                lbl.bind("<Double-1>", self._center_view)
            
            lbl.grid(row=0, column=i, sticky="ew")

            # Treeview
            t = ttk.Treeview(f_grid, columns=("v",), show="", selectmode="none", height=30, style="Book.Treeview")
            t.column("v", width=width, anchor=anchor)
            t.column("#0", width=0, stretch=False)
            t.grid(row=1, column=i, sticky="nsew")
            
            # Events communs
            t.bind("<MouseWheel>", self._on_wheel)
            t.bind("<B1-Motion>", self._on_user_scroll)
            t.bind("<Button-1>", self._on_user_scroll) # Pour détecter clic simple aussi
            
            self.trees[key] = t
            self.tree_list.append(t)

        # Scrollbar unique
        sb = ttk.Scrollbar(f_grid, orient="vertical", command=self._sync_scroll)
        sb.grid(row=1, column=len(cols_cfg), sticky="ns")
        for t in self.tree_list: t.config(yscrollcommand=sb.set)

        # Bindings Spécifiques (Trading)
        self.trees["px"].bind("<Double-1>", self._center_view)
        self.trees["px"].bind("<Button-3>", self._on_right_click)
        
        self.trees["bid"].bind("<Button-1>", lambda e: self._on_dom_click(e, "BUY"))
        self.trees["ask"].bind("<Button-1>", lambda e: self._on_dom_click(e, "SELL"))

        # Configuration des Tags (Couleurs)
        self._init_tags()

    def _init_tags(self):
        # --- TAGS STRUCTURE (Colonne CTX) ---
        self.trees["ctx"].tag_configure("mag_up", foreground=COL_MAGNET_UP, font=("Segoe UI", 10, "bold"))
        self.trees["ctx"].tag_configure("mag_dn", foreground=COL_MAGNET_DN, font=("Segoe UI", 10, "bold"))
        self.trees["ctx"].tag_configure("sess", foreground=COL_SESSION_LVL, font=("Segoe UI", 8, "bold"))

        # --- TAGS PRIX ---
        self.trees["px"].tag_configure("current", background=self.ticker_bg_color, foreground="white")
        # Zones FVG en arrière-plan du prix
        self.trees["px"].tag_configure("fvg_bull", background=COL_FVG_BULL)
        self.trees["px"].tag_configure("fvg_bear", background=COL_FVG_BEAR)
        
        # Trading active
        self.trees["px"].tag_configure("ENTRY", background="#a5d6a7", foreground="white", font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("SL", background="#ef9a9a", foreground="#b71c1c", font=("Segoe UI", 9, "bold"))
        self.trees["px"].tag_configure("TP", background="#90caf9", foreground="#0d47a1")
        self.trees["px"].tag_configure("GHOST_SL", background=SL_BG_COLOR, foreground="black", font=("Segoe UI", 9))
        self.trees["px"].tag_configure("marker", foreground="#212121", font=("Segoe UI", 9, "bold")) # High/Low

        # --- TAGS VOLUME (Heatmap) ---
        for i in range(10):
            # Dégradé vert simple
            inte = int(255 - (i * 15))
            if inte < 0: inte = 0
            hex_c = f"#{inte:02x}ff{inte:02x}" 
            # Pour les gros volumes, texte noir, sinon gris
            fg = "black" if i > 3 else "#546e7a"
            
            self.trees["s"].tag_configure(f"vol_{i}", background=hex_c, foreground=fg)
            self.trees["m"].tag_configure(f"vol_{i}", background=hex_c, foreground=fg)
            self.trees["l"].tag_configure(f"vol_{i}", background=hex_c, foreground=fg)

        # --- TAGS DOM & DELTA ---
        self.trees["bid"].tag_configure("dom_bid", foreground="#1565c0") 
        self.trees["ask"].tag_configure("dom_ask", foreground="#c62828") 
        self.trees["bid"].tag_configure("absorb_bid", foreground="#6a1b9a", font=("Segoe UI", 9, "bold")) 
        self.trees["ask"].tag_configure("absorb_ask", foreground="#e65100", font=("Segoe UI", 9, "bold")) 

        self.trees["delta"].tag_configure("delta_pos", foreground="#2e7d32")
        self.trees["delta"].tag_configure("delta_neg", foreground="#c62828")
        
        # Magnets sur Delta (Rétro-compatibilité visuelle)
        self.trees["delta"].tag_configure("bg_mag_up", background=COL_BG_MAGNET_UP, foreground="white")
        self.trees["delta"].tag_configure("bg_mag_dn", background=COL_BG_MAGNET_DN, foreground="white")

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
        self._last_user_scroll = 0
        self._anchor_price = None
        self.update_data()

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
        except Exception as e:
            print(f"Click Error: {e}")

    def _on_right_click(self, event):
        # Menu contextuel simple sur le prix
        item_id = self.trees["px"].identify_row(event.y)
        if not item_id: return
        vals = self.trees["px"].item(item_id, "values")
        if not vals: return
        try: 
            # On nettoie le string prix (enlève les symboles)
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
            
            # --- SETUP GENERAL ---
            grp = int(self.panel.group_var.get()) if hasattr(self.panel, 'group_var') else 1
            eff_tick = self.tick_size * grp
            last_px_snap = _safe_snap(last_px, eff_tick)
            
            spd = self.controller.get_market_speed(self.sym)
            icon = "●" if self.is_active else "○"
            self.lbl_info.config(text=f"{icon} {self.sym} | {last_px:.2f} | {_safe_int(spd)}/m")

            # --- ANCRAGE VUE ---
            # Si l'utilisateur n'a pas scrollé depuis 15s, on recentre
            if self._anchor_price is None or (time.time() - self._last_user_scroll > self._scroll_timeout):
                 # Si le prix sort trop de l'écran, on recentre
                 if self._anchor_price:
                     dist = abs(last_px_snap - self._anchor_price) / eff_tick
                     if dist > 15: self._anchor_price = last_px_snap
                 else:
                     self._anchor_price = last_px_snap

            # --- DATA CONTEXTE (Radar) ---
            radar = self.controller.analyzer.get_radar_snapshot(self.sym)
            context_map = {} # { price: (text, tag) }
            fvg_ranges = []  # List of (top, bot, type, mitigated)
            
            if self.show_struct.get():
                # 1. Session Levels
                sess = radar.get("SESSION", {})
                for k, v in sess.items():
                    if v and isinstance(v, (int, float)) and k != "Gap":
                        snap = _safe_snap(v, eff_tick)
                        # Label court : High -> H, Low -> L, Open -> O
                        lbl = "H" if "High" in k else ("L" if "Low" in k else "O")
                        # Tag Couleur
                        tag = "mag_up" if "High" in k else ("mag_dn" if "Low" in k else "sess")
                        context_map[snap] = (lbl, tag)
                
                # 2. FVGs & Magnets
                for tf in ["M15", "H1"]:
                    for fvg in radar.get(tf, {}).get("fvgs", []):
                        # MODIF: Récupération de l'état 'mitigated'
                        is_mit = fvg.get("mitigated", False)
                        fvg_ranges.append((fvg['top'], fvg['bot'], fvg['type'], is_mit))
                        
                        # Magnet Icons
                        snap_top = _safe_snap(fvg['top'], eff_tick)
                        snap_bot = _safe_snap(fvg['bot'], eff_tick)
                        
                        # Resistance (Bear FVG Top) = Magnet Up (Rouge)
                        context_map[snap_top] = ("🧲", "mag_up" if fvg['type']=="BEAR" else "mag_dn")
                        # Si le bot n'est pas déjà pris
                        if snap_bot not in context_map:
                             context_map[snap_bot] = ("🧲", "mag_dn" if fvg['type']=="BULL" else "mag_up")

            # --- DATA VOLUME (VBP) ---
            vol_data = {"s": {}, "m": {}, "l": {}}
            delta_data = {} # Pour delta global
            max_vol = 1
            
            if self.show_vol.get():
                # On utilise 3 horizons fixes pour simplifier S/M/L
                # S = 1m Time, M = 5m Time, L = 15m Time (ou Vol Profile)
                # On récupère les données brutes
                try:
                    r_s, d_s = self.aggr.get_rolling_data(self.sym, "Time", 5) # S = 5 min
                    r_m, _   = self.aggr.get_rolling_data(self.sym, "Time", 30) # M = 30 min
                    r_l, _   = self.aggr.get_rolling_data(self.sym, "Vol", 10000) # L = Volume
                    
                    # Grouping
                    g_s, gd_s = self._group_data(r_s, d_s, grp)
                    g_m, _    = self._group_data(r_m, {}, grp)
                    g_l, _    = self._group_data(r_l, {}, grp)
                    
                    vol_data["s"] = g_s
                    vol_data["m"] = g_m
                    vol_data["l"] = g_l
                    delta_data = gd_s # On affiche le delta du court terme (S)
                    
                    # Max pour heatmap
                    all_vals = list(g_s.values()) + list(g_m.values()) + list(g_l.values())
                    if all_vals: max_vol = max(all_vals)
                except: pass

            # --- DATA DOM ---
            dom = self.aggr.dom.get(self.sym, {})
            bids = dom.get('bids', {})
            asks = dom.get('asks', {})
            
            # --- GENERATION DES LIGNES ---
            rows = 40
            center_step = round(self._anchor_price / eff_tick)
            # On génère du haut vers le bas (Prix décroissant pour affichage classique)
            # Mais Treeview liste : index 0 en haut. Donc Prix Haut -> Prix Bas.
            # Prix Haut = center + rows/2
            
            # Nettoyage
            for t in self.tree_list: t.delete(*t.get_children())
            
            markers = self.controller.get_trading_markers(self.sym)
            
            # Boucle d'affichage
            for i in range(rows // 2, -rows // 2, -1):
                p = (center_step + i) * eff_tick
                p = _safe_snap(p, eff_tick) # Float propre
                
                # 1. CONTEXTE
                ctx_txt, ctx_tag = "", ""
                if p in context_map:
                    ctx_txt, ctx_tag = context_map[p]
                self.trees["ctx"].insert("", "end", values=(ctx_txt,), tags=(ctx_tag,))

                # 2. PRIX + Structure Background
                p_str = f"{p:.2f}"
                p_tags = []
                
                # FVG Background - MODIF: On filtre les zones mitigées
                for top, bot, type_, is_mit in fvg_ranges:
                    if bot <= p <= top:
                        # On affiche UNIQUEMENT si NON mitigé
                        if not is_mit:
                            p_tags.append("fvg_bull" if type_=="BULL" else "fvg_bear")
                        break
                
                # Highlight Current
                if abs(p - last_px_snap) < (eff_tick/10): 
                    p_tags.append("current")
                
                # Trading Markers
                if p in markers: p_tags.append(markers[p]) # ENTRY/SL/TP
                
                # Ghost Orders
                sl_val = int(self.panel.sl_var.get()) * self.tick_size
                if not any(v == "ENTRY" for v in markers.values()):
                    if abs(p - (last_px_snap - sl_val)) < (eff_tick/10): p_tags.append("GHOST_SL")
                    if abs(p - (last_px_snap + sl_val)) < (eff_tick/10): p_tags.append("GHOST_SL")

                self.trees["px"].insert("", "end", values=(p_str,), tags=tuple(p_tags))

                # 3. VOLUME COLUMNS
                for k in ["s", "m", "l"]:
                    v = vol_data[k].get(p, 0)
                    v_str = _safe_int(v) if v > 0 else ""
                    tags = []
                    if v > 0:
                        intensity = min(9, int((v / max_vol) * 9))
                        tags.append(f"vol_{intensity}")
                    self.trees[k].insert("", "end", values=(v_str,), tags=tuple(tags))

                # 4. DOM & DELTA
                # Bids/Asks grouping
                b_sz, a_sz = 0, 0
                # Approximation simple pour le DOM groupé
                if grp == 1:
                    b_sz = bids.get(p, 0)
                    a_sz = asks.get(p, 0)
                else:
                    # Somme des niveaux proches
                    for bp, bz in bids.items():
                        if abs(bp - p) < (eff_tick/2): b_sz += bz
                    for ap, az in asks.items():
                        if abs(ap - p) < (eff_tick/2): a_sz += az
                
                # Tags DOM
                b_tag = "dom_bid"
                a_tag = "dom_ask"
                # Absorption detection (Si Volume S est fort mais Delta faible ou inverse)
                if vol_data["s"].get(p,0) > (max_vol*0.3):
                    d_val = delta_data.get(p, 0)
                    if d_val < 0 and abs(d_val) > (vol_data["s"].get(p,0)*0.6): b_tag = "absorb_bid"
                    if d_val > 0 and abs(d_val) > (vol_data["s"].get(p,0)*0.6): a_tag = "absorb_ask"

                self.trees["bid"].insert("", "end", values=(_safe_int(b_sz) if b_sz else "",), tags=(b_tag,))
                self.trees["ask"].insert("", "end", values=(_safe_int(a_sz) if a_sz else "",), tags=(a_tag,))

                # Delta
                d_val = delta_data.get(p, 0)
                d_str = _safe_int(d_val) if d_val != 0 else ""
                d_tag = "delta_pos" if d_val > 0 else "delta_neg"
                
                # Magnet Background sur Delta aussi (Optionnel)
                magnet_bg_tags = []
                if p in context_map:
                     if "mag_up" in context_map[p][1]: magnet_bg_tags.append("bg_mag_up")
                     elif "mag_dn" in context_map[p][1]: magnet_bg_tags.append("bg_mag_dn")

                self.trees["delta"].insert("", "end", values=(d_str,), tags=tuple([d_tag] + magnet_bg_tags))

            # Restauration vue si user scroll récent (pour éviter saut)
            if self._last_user_scroll > 0 and (time.time() - self._last_user_scroll < self._scroll_timeout):
                 pass # On laisse l'utilisateur gérer son scroll
            else:
                 # Auto scroll au milieu (index rows//2 correspond au prix actuel environ)
                 mid_item = self.trees["px"].get_children()[rows//2]
                 for t in self.tree_list: t.see(mid_item)

        except Exception as e:
            # print(f"Update Error: {e}")
            pass