# ui/panels.py
import tkinter as tk
from tkinter import ttk
from core.ui_state import get_widget_settings, update_widget_settings
import config

# --- PALETTE "DAY PRO" ---
COLOR_BG_APP    = "#f0f2f5"
COLOR_FG_TEXT   = "#263238"
COLOR_BG_INPUT  = "#ffffff"

class UnifiedControlPanel(tk.Frame):
    def __init__(self, parent, controller, symbol, context="Session", read_only=False):
        super().__init__(parent, bg=COLOR_BG_APP)
        self.controller = controller
        self.sym = symbol
        self.context = context
        self.read_only = read_only
        self.storage_key = f"{symbol}_{context}"
        
        saved = get_widget_settings(self.storage_key)
        
        # Vars (Chargement des defaults personnalisés)
        self.qty_var = tk.StringVar(value=saved.get("qty", "1"))
        self.sl_var  = tk.StringVar(value=saved.get("sl", "10"))
        self.tp_var  = tk.StringVar(value=saved.get("tp", "20"))
        
        self.zone_mode_var = tk.StringVar(value=saved.get("zone_mode", "Ticks"))
        self.zone_val_var = tk.StringVar(value=saved.get("zone_val", "10"))
        self.zone_src_var = tk.StringVar(value=saved.get("zone_src", "M")) # Default M
        
        self.rolling_mode_var = tk.StringVar(value=saved.get("rolling", "Vol")) # Default Vol
        
        self.group_var = tk.StringVar(value=saved.get("group", "1"))
        
        self.be_active_var = tk.BooleanVar(value=False)
        self.be_trigger_var = tk.StringVar(value=saved.get("be_trig", "8")) # Default 8
        
        # --- ALERTES SÉLECTIVES ---
        self.alert_active_var = tk.BooleanVar(value=False) # Master Switch
        self.alert_zone_var = tk.BooleanVar(value=True)    # Zone VBP
        self.alert_vwap_var = tk.BooleanVar(value=False)   # VWAP
        self.alert_pivot_var = tk.BooleanVar(value=False)  # Pivot
        
        self.show_last_var = tk.BooleanVar(value=True)
        self.show_vwap_var = tk.BooleanVar(value=True)
        self.strat_var = tk.StringVar(value="Perso")

        # Traceurs pour sauvegarde automatique
        for var in (self.qty_var, self.sl_var, self.tp_var, self.zone_mode_var, 
                    self.zone_val_var, self.group_var, self.be_trigger_var, 
                    self.zone_src_var, self.rolling_mode_var):
            var.trace_add("write", self._on_change)
            
        self.be_active_var.trace_add("write", self._update_guardian)
        self.be_trigger_var.trace_add("write", self._update_guardian)
        self.strat_var.trace_add("write", self._apply_strategy)

        self._build_ui()
        self.after(2000, self._update_guardian)

    def _apply_strategy(self, *args):
        strat_name = self.strat_var.get()
        if strat_name in config.STRATEGIES:
            s = config.STRATEGIES[strat_name]
            self.qty_var.set(str(s["qty"]))
            self.sl_var.set(str(s["sl"]))
            self.tp_var.set(str(s["tp"]))
            self.be_active_var.set(s["be_active"])
            self.be_trigger_var.set(str(s["be_trig"]))

    def _on_change(self, *args):
        update_widget_settings(
            self.storage_key,
            self.qty_var.get(), self.sl_var.get(), self.tp_var.get(),
            self.zone_mode_var.get(), self.zone_val_var.get(), self.group_var.get(),
            self.zone_src_var.get(), self.rolling_mode_var.get(), self.be_trigger_var.get()
        )

    def _update_guardian(self, *args):
        try:
            active = self.be_active_var.get()
            trig = int(self.be_trigger_var.get() or 15)
            self.controller.update_guardian_config(self.sym, active, trig)
        except: pass

    def _build_ui(self):
        # Ligne 1
        f_top = tk.Frame(self, bg=COLOR_BG_APP)
        f_top.pack(fill="x", pady=2)
        if not self.read_only:
            strats = list(config.STRATEGIES.keys()) + ["Perso"]
            cb = ttk.Combobox(f_top, textvariable=self.strat_var, values=strats, width=8, state="readonly")
            cb.pack(side="left", padx=2)
            self._entry(f_top, "Qty", self.qty_var, 3)
            self._entry(f_top, "SL", self.sl_var, 3)
            self._entry(f_top, "TP", self.tp_var, 3)
        
        # Ligne 2 : Barre d'outils VBP
        f_vbp = tk.Frame(self, bg=COLOR_BG_APP)
        f_vbp.pack(fill="x", pady=2)
        
        # Alertes (Icone Cloche + Z/V/P)
        cb_alert = ttk.Checkbutton(f_vbp, text="🔔", variable=self.alert_active_var)
        cb_alert.pack(side="left", padx=(2,5))
        
        # Petites cases pour choisir QUOI sonner
        ttk.Checkbutton(f_vbp, text="Z", variable=self.alert_zone_var).pack(side="left", padx=0)
        ttk.Checkbutton(f_vbp, text="V", variable=self.alert_vwap_var).pack(side="left", padx=0)
        ttk.Checkbutton(f_vbp, text="P", variable=self.alert_pivot_var).pack(side="left", padx=0)
        
        tk.Label(f_vbp, text="|", bg=COLOR_BG_APP, fg="#bdbdbd").pack(side="left", padx=3)
        
        # Mode Vol/Time
        ttk.Combobox(f_vbp, textvariable=self.rolling_mode_var, values=["Time", "Vol"], width=4, state="readonly").pack(side="left", padx=1)

        # Zone Source
        tk.Label(f_vbp, text="Src", bg=COLOR_BG_APP, fg=COLOR_FG_TEXT, font=("Segoe UI", 7)).pack(side="left")
        ttk.Combobox(f_vbp, textvariable=self.zone_src_var, values=["Sess", "XL", "L", "M"], width=4, state="readonly").pack(side="left", padx=0)
        
        # Zone Taille
        ttk.Combobox(f_vbp, textvariable=self.zone_mode_var, values=["Ticks", "Pct"], width=4, state="readonly").pack(side="left", padx=1)
        ttk.Entry(f_vbp, textvariable=self.zone_val_var, width=3).pack(side="left", padx=0)
        
        tk.Label(f_vbp, text="Grp", bg=COLOR_BG_APP, fg=COLOR_FG_TEXT, font=("Segoe UI", 7)).pack(side="left", padx=(5,0))
        ttk.Combobox(f_vbp, textvariable=self.group_var, values=["1", "2", "4", "10", "20"], width=3, state="readonly").pack(side="left")

        # Ligne 3 : Trading
        if not self.read_only:
            f_btns = tk.Frame(self, bg=COLOR_BG_APP)
            f_btns.pack(fill="x", pady=4)
            
            f_be = tk.Frame(f_btns, bg=COLOR_BG_APP)
            f_be.pack(side="left", padx=2)
            ttk.Checkbutton(f_be, text="BE", variable=self.be_active_var).pack(side="left")
            ttk.Entry(f_be, textvariable=self.be_trigger_var, width=3).pack(side="left")

            self._btn(f_btns, "ACHAT", "#388e3c", lambda: self._trade("BUY"))
            self._btn(f_btns, "FLAT", "#546e7a", self._flatten, w=6)
            self._btn(f_btns, "VENTE", "#d32f2f", lambda: self._trade("SELL"))
            
            btn_reset = tk.Button(f_vbp, text="×", width=2, bg=COLOR_BG_APP, fg="#90a4ae", 
                                  font=("Arial", 8), bd=0, command=self._reset_session, cursor="hand2")
            btn_reset.pack(side="right", padx=2)

    def _entry(self, parent, lbl, var, w):
        f = tk.Frame(parent, bg=COLOR_BG_APP)
        f.pack(side="left", padx=3)
        tk.Label(f, text=lbl, bg=COLOR_BG_APP, fg="#78909c", font=("Segoe UI", 7, "bold")).pack(side="top", anchor="w")
        e = tk.Entry(f, textvariable=var, width=w, font=("Segoe UI", 9), bg=COLOR_BG_INPUT, relief="flat", highlightthickness=1, highlightcolor="#cfd8dc")
        e.pack(side="bottom")

    def _btn(self, parent, txt, bg_col, cmd, w=None):
        b = tk.Button(parent, text=txt, bg=bg_col, fg="white", 
                      font=("Segoe UI", 8, "bold"), command=cmd, 
                      relief="flat", width=w, cursor="hand2", pady=2)
        b.pack(side="left", fill="x", expand=(w is None), padx=2)

    def _trade(self, action):
        if self.read_only: return
        try:
            q = float(self.qty_var.get())
            sl = int(self.sl_var.get())
            tp = int(self.tp_var.get())
            self.controller.place_order(self.sym, action, q, sl, tp)
        except: print(f"Erreur param {self.sym}")

    def _flatten(self):
        if self.read_only: return
        self.controller.flatten(self.sym)

    def _reset_session(self):
        if self.read_only: return
        self.controller.reset_data(self.sym)

SingleControlPanel = UnifiedControlPanel