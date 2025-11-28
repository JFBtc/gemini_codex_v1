# ui/dashboard.py
import logging
import tkinter as tk
from tkinter import ttk
from ui.book import MultiHorizonWidget, COLOR_BG_APP
from ui.charts import MiniChartWidget
from ui.datalab import DataLabView
from ui.execution import ExecutionView  # <--- AJOUT IMPORT
import config

class WallView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG_APP)
        self.widgets = []
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        for i, pair in enumerate(config.PAIRS):
            sym_L = pair["left"]["symbol"]
            sym_R = pair["right"]["symbol"]
            wid_L = MultiHorizonWidget(self, controller, sym_L)
            wid_L.grid(row=i, column=0, sticky="nsew", padx=1, pady=1)
            self.widgets.append(wid_L)
            wid_R = MultiHorizonWidget(self, controller, sym_R)
            wid_R.grid(row=i, column=1, sticky="nsew", padx=1, pady=1)
            self.widgets.append(wid_R)

    def refresh(self):
        for w in self.widgets: w.update_data()

class ChartsWindow(tk.Toplevel):
    def __init__(self, controller):
        super().__init__()
        self.title("Météo du Marché - Graphiques")
        self.geometry("1000x800")
        self.configure(bg=COLOR_BG_APP)
        self.charts = []
        self.maximized_chart = None 
        
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        for i, pair in enumerate(config.PAIRS):
            sym_L = pair["left"]["symbol"]
            sym_R = pair["right"]["symbol"]
            
            c1 = MiniChartWidget(self, controller, sym_L)
            c1.grid(row=i, column=0, sticky="nsew", padx=2, pady=2)
            c1.grid_info_saved = {"row": i, "column": 0} 
            self.charts.append(c1)
            
            c2 = MiniChartWidget(self, controller, sym_R)
            c2.grid(row=i, column=1, sticky="nsew", padx=2, pady=2)
            c2.grid_info_saved = {"row": i, "column": 1}
            self.charts.append(c2)

    def toggle_maximize(self, chart_widget):
        if self.maximized_chart:
            for c in self.charts:
                info = c.grid_info_saved
                c.grid(row=info["row"], column=info["column"], sticky="nsew", padx=2, pady=2)
            self.maximized_chart = None
        else:
            for c in self.charts:
                c.grid_remove() 
            chart_widget.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")
            self.maximized_chart = chart_widget

    def refresh(self):
        for c in self.charts: c.update_chart()


class RefreshGuard:
    """Utility to track refresh failures and expose a status suffix."""

    def __init__(self):
        self.failure_count = 0

    def record_success(self):
        if self.failure_count:
            self.failure_count = 0
        return self.status_suffix

    def record_failure(self, widget_name):
        self.failure_count += 1
        logging.exception("Echec du rafraîchissement du widget %s", widget_name)
        return self.status_suffix

    @property
    def status_suffix(self):
        return "" if self.failure_count == 0 else f" ⚠️ ({self.failure_count})"

class FocusView(tk.Frame):
    def __init__(self, parent, controller, pair_index):
        super().__init__(parent, bg=COLOR_BG_APP)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        pair = config.PAIRS[pair_index]
        sym = pair["left"]["symbol"]
        self.wid = MultiHorizonWidget(self, controller, sym)
        self.wid.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    def refresh(self):
        self.wid.update_data()

class ModernDashboard(ttk.Notebook):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.charts_window = None
        self.refresh_guard = RefreshGuard()
        self.logger = logging.getLogger(__name__)
        self._exec_tab_base = " 🚀 EXÉCUTION "

        # --- 1. NOUVEAU COCKPIT (PAR DÉFAUT) ---
        self.tab_exec = ExecutionView(self, controller)
        self.add(self.tab_exec, text=self._exec_tab_base)

        # --- 2. ANCIENS ONGLETS ---
        self.tab_wall = WallView(self, controller)
        self.add(self.tab_wall, text=" 🧱 MUR DOM ")
        
        self.tab_nq = FocusView(self, controller, pair_index=0)
        self.add(self.tab_nq, text=" 🎯 MNQ ")
        
        self.tab_es = FocusView(self, controller, pair_index=1)
        self.add(self.tab_es, text=" 🎯 MES ")
        
        self.tab_lab = DataLabView(self, controller)
        self.add(self.tab_lab, text=" 🔬 LABO ")

        f_tools = tk.Frame(self, bg=COLOR_BG_APP)
        self.add(f_tools, text=" ⚙️ OUTILS ")
        
        btn_detach = tk.Button(f_tools, text="🗗 DÉTACHER GRAPHIQUES", bg="#37474f", fg="white", font=("Segoe UI", 10, "bold"), command=self.open_charts)
        btn_detach.pack(pady=20, padx=20)

    def open_charts(self):
        if self.charts_window is None or not tk.Toplevel.winfo_exists(self.charts_window):
            self.charts_window = ChartsWindow(self.controller)

    @staticmethod
    def _safe_refresh(widget_name, refresh_callable, logger, log_exception=True):
        """
        Run a widget refresh and return True/False depending on success.

        This protects the UI loop from crashing when a widget raises during
        refresh, while optionally logging the failure for diagnostics.
        """

        try:
            refresh_callable()
            return True
        except Exception:
            if log_exception:
                logger.exception("Echec du rafraîchissement du widget %s", widget_name)
            return False

    def _update_exec_tab_status(self):
        self.tab(self.tab_exec, text=f"{self._exec_tab_base}{self.refresh_guard.status_suffix}")

    def refresh(self):
        # Refresh priority (Onglet actif seulement serait une optimisation,
        # mais on refresh tout pour garantir la fluidité des données en arrière-plan)

        # On refresh d'abord l'onglet Exécution s'il est visible (ou tout le temps pour les alertes)
        is_exec_ok = self._safe_refresh(
            "ExecutionView",
            self.tab_exec.refresh,
            self.logger,
            log_exception=False,
        )

        if is_exec_ok:
            self.tab(self.tab_exec, state="normal")
            self.refresh_guard.record_success()
        else:
            self.tab(self.tab_exec, state="disabled")
            self.refresh_guard.record_failure("ExecutionView")

        self._update_exec_tab_status()

        self._safe_refresh("WallView", self.tab_wall.refresh, self.logger)
        self._safe_refresh("FocusView-NQ", self.tab_nq.refresh, self.logger)
        self._safe_refresh("FocusView-ES", self.tab_es.refresh, self.logger)
        # Le Labo a son propre auto-refresh interne, pas besoin de l'appeler ici

        if self.charts_window and tk.Toplevel.winfo_exists(self.charts_window):
            self._safe_refresh("ChartsWindow", self.charts_window.refresh, self.logger)
