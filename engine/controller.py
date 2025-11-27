"""Controlleur principal orchestrant les services du robot."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

import config
from core.ib_resilient_manager import IBResilientManager
from engine.aggregator import Aggregator
from engine.guardian import TradeGuardian
from engine.market_analyzer import MarketAnalyzer
from ib_insync import Contract

log = logging.getLogger("BotController")


class BotController:
    """Point d'entrée partagé entre la couche UI et le moteur."""

    def __init__(self) -> None:
        self.tick_sizes_map = self._extract_tick_sizes(config.PAIRS)
        self.contracts_map = self._build_contracts(config.PAIRS)

        self.ibm = IBResilientManager(
            host=getattr(config, "IB_HOST", "127.0.0.1"),
            port=getattr(config, "IB_PORT", 7497),
            base_client_id=getattr(config, "CLIENT_ID", 1),
        )
        self.aggregator = Aggregator(self, tick_size_map=self.tick_sizes_map)
        self.guardian = TradeGuardian(self.ibm, self.aggregator)
        self.analyzer = MarketAnalyzer(self.ibm, self.tick_sizes_map)

        self._dom_levels: Dict[str, List[dict]] = defaultdict(list)
        self._markers: Dict[str, Dict[float, str]] = defaultdict(dict)
        self.active_symbol: Optional[str] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._tasks: List[asyncio.Task] = []

    # ─────────────────────────── Helpers ───────────────────────────
    def _extract_tick_sizes(self, pairs: Iterable[dict]) -> Dict[str, float]:
        tick_map: Dict[str, float] = {}
        for pair in pairs:
            for side in ("left", "right"):
                leg = pair.get(side, {})
                sym = leg.get("symbol")
                tick = leg.get("tick_size", 0.25)
                if sym:
                    tick_map[sym] = float(tick or 0.25)
        return tick_map

    def _build_contracts(self, pairs: Iterable[dict]) -> Dict[str, Contract]:
        contracts: Dict[str, Contract] = {}
        for pair in pairs:
            for side in ("left", "right"):
                leg = pair.get(side, {})
                sym = leg.get("symbol")
                if not sym:
                    continue
                contracts[sym] = Contract(
                    symbol=sym,
                    secType="FUT",
                    lastTradeDateOrContractMonth=leg.get("expiry"),
                    exchange=leg.get("exchange", "GLOBEX"),
                    currency=leg.get("currency", "USD"),
                )
        return contracts

    # ─────────────────────────── Public API ───────────────────────────
    def get_aggregator(self) -> Aggregator:
        return self.aggregator

    def get_tick_size(self, symbol: str) -> float:
        return self.tick_sizes_map.get(symbol, 0.25)

    def get_market_speed(self, symbol: str) -> float:
        return self.aggregator.get_speed(symbol)

    def get_dom_levels(self, symbol: str) -> List[dict]:
        return list(self._dom_levels.get(symbol, []))

    def set_dom_levels(self, symbol: str, levels: List[dict]) -> None:
        self._dom_levels[symbol] = list(levels)

    def get_trading_markers(self, symbol: str) -> Dict[float, str]:
        return dict(self._markers.get(symbol, {}))

    def reset_data(self, symbol: Optional[str] = None) -> None:
        self.aggregator.reset_session(symbol)

    def update_guardian_config(self, symbol: str, active: bool, trigger_ticks: int) -> None:
        self.guardian.update_config(symbol, active, trigger_ticks)

    # ────────────────────────── Trading Stubs ─────────────────────────
    def place_order(self, symbol: str, action: str, qty: float, sl: int, tp: int) -> None:
        log.info("[Order] %s %s (SL=%s, TP=%s)", action, symbol, sl, tp)

    def place_limit_order(self, symbol: str, action: str, price: float, qty: float, sl: int, tp: int) -> None:
        log.info("[Lmt] %s %s @ %.2f (SL=%s, TP=%s)", action, symbol, price, sl, tp)

    def modify_order_price(self, symbol: str, order_type: str, price: float) -> None:
        log.info("[Modify] %s %s -> %.2f", order_type, symbol, price)

    def flatten(self, symbol: str) -> None:
        log.info("[Flat] Closing %s", symbol)

    # ───────────────────────── Lifecycle ────────────────────────────
    async def start(self, stop_event: Optional[asyncio.Event] = None) -> asyncio.Event:
        """Initialise les connexions et démarre les boucles asynchrones."""
        self._stop_event = stop_event or asyncio.Event()

        await self.ibm.start()

        loop = asyncio.get_running_loop()
        self._tasks.append(loop.create_task(self.guardian.start(), name="guardian"))
        self._tasks.append(
            loop.create_task(self.analyzer.start_radar_loop(self.contracts_map), name="market_radar")
        )
        return self._stop_event

    async def close(self) -> None:
        """Nettoyage à la fermeture de l'application."""
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()

        self.guardian.running = False
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

        await self.ibm.stop()
