#!/usr/bin/env python3
# core/logger.py – v1.1
# Logger central léger avec filtrage du bruit IB.

from __future__ import annotations
import logging
import sys

try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
    _HAS_COLOR = True
except Exception:
    _HAS_COLOR = False

    class _Dummy:
        RESET_ALL = ""
    Fore = Style = _Dummy()  # fallback neutre


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    Fore.BLUE,
        "INFO":     Fore.GREEN,
        "WARNING":  Fore.YELLOW,
        "ERROR":    Fore.RED,
        "CRITICAL": Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        time_str  = self.formatTime(record, "%H:%M:%S")
        level_str = f"{record.levelname:<8}"
        name_str  = f"{record.name:<18}"
        msg       = record.getMessage()

        if _HAS_COLOR:
            color = self.COLORS.get(record.levelname, "")
            reset = Style.RESET_ALL
            return f"{color}{time_str} │ {level_str} │ {name_str} │ {msg}{reset}"
        else:
            return f"{time_str} │ {level_str} │ {name_str} │ {msg}"


def setup_logging(level: int = logging.INFO) -> None:
    """
    Initialise le logger global et applique les filtres.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # On enlève les handlers existants pour éviter d'empiler les formats.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())
    root.addHandler(handler)

    # ─────────────────────────────────────────────────────────────
    # FILTRAGE DU BRUIT
    # ─────────────────────────────────────────────────────────────
    
    # On met ib_insync en mode "WARNING" seulement. 
    # Cela cache les messages INFO (execDetails, commissions, portfolio updates...)
    logging.getLogger("ib_insync").setLevel(logging.WARNING)

    # On s'assure que TES modules importants restent bien en INFO (visibles)
    logging.getLogger("Controller").setLevel(logging.INFO)
    logging.getLogger("IBRM").setLevel(logging.INFO)
    logging.getLogger("Aggregator").setLevel(logging.INFO)