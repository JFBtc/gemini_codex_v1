#!/usr/bin/env python3
# core/ib_resilient_manager.py
# IB Resilient Manager — v1.9 (debounce reco + auto-heal + rebind hook)
from __future__ import annotations

import asyncio, logging, random, time, contextlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ib_insync import IB, Contract, Ticker, util

log = logging.getLogger("IBRM")
log.setLevel(logging.INFO)

# ───────── Tunables
HEARTBEAT_SEC           = 15     # Périodicité du ping temps IB
HB_TIMEOUT_SEC          = 5      # Timeout max pour le heartbeat
SUPERVISOR_SEC          = 5      # Bouée de sauvetage hors-heartbeat
RECONNECT_MAX_BACKOFF   = 30     # Backoff max
RECONNECT_FIRST_BACKOFF = 2      # Backoff initial
MIN_TICKERS_READY       = 1      # Min tickers “vivants” avant reprise
MIN_STABLE_WINDOW_SEC   = 3      # Fenêtre stable avant reprise

ExternalCB     = Callable[[], None]
RebindIBHookCB = Callable[[IB], None]  # ex: lambda ib: (hub.rebind_ib(ib, cm), hub.restart_live_safe())

@dataclass
class SubRecord:
    contract: Contract
    genericTickList: str = ""
    snapshot: bool = False
    regulatorySnapshot: bool = False
    options: Optional[list] = None
    ticker: Optional[Ticker] = None

@dataclass
class IBResilientManager:
    # Connexion IB
    host: str = "127.0.0.1"
    port: int = 7497
    base_client_id: int = 1
    client_span: int = 12
    auto_connect: bool = True

    # Hooks publics
    on_suspend: List[ExternalCB] = field(default_factory=list)
    on_resume: List[ExternalCB] = field(default_factory=list)
    on_connected: List[ExternalCB] = field(default_factory=list)
    on_disconnected: List[ExternalCB] = field(default_factory=list)
    on_resubscribed: List[ExternalCB] = field(default_factory=list)
    on_rebind_ib: Optional[RebindIBHookCB] = None   # ← nouveau : rebind DataHub/CM AVANT resub

    # État interne
    ib: IB = field(default_factory=IB, init=False)
    _subs: Dict[str, SubRecord] = field(default_factory=dict, init=False)
    _watchdog_task: Optional[asyncio.Task] = field(default=None, init=False)
    _supervisor_task: Optional[asyncio.Task] = field(default=None, init=False)
    _reconnecting: bool = field(default=False, init=False)
    _current_client_id: int = field(default=0, init=False)
    _last_rebind_ts: float = field(default=0.0, init=False)

    # ════════════════════════════════════════════════════════
    # Lifecycle
    # ════════════════════════════════════════════════════════
    async def start(self) -> None:
        self._attach_handlers()
        if self.auto_connect:
            await self._connect_with_retry()

        loop = util.getLoop()
        if self._watchdog_task is None:
            self._watchdog_task = loop.create_task(self._watchdog(), name="IBRM.watchdog")
        if self._supervisor_task is None:
            self._supervisor_task = loop.create_task(self._supervisor(), name="IBRM.supervisor")

    async def stop(self) -> None:
        for t in (self._watchdog_task, self._supervisor_task):
            if t:
                t.cancel()
        self._watchdog_task = self._supervisor_task = None
        if self.ib.isConnected():
            with contextlib.suppress(Exception):
                await self.ib.disconnectAsync()

    # ════════════════════════════════════════════════════════
    # Public API
    # ════════════════════════════════════════════════════════
    def is_connected(self) -> bool:
        return self.ib.isConnected()

    def force_reconnect(self) -> None:
        util.getLoop().create_task(self._on_disconnect_sequence(), name="IBRM.force_reconnect")

    def subscribe(self, key: str, contract: Contract, *,
                  genericTickList: str = "",
                  snapshot: bool = False,
                  regulatorySnapshot: bool = False,
                  options: Optional[list] = None) -> Optional[Ticker]:
        """
        Enregistre une souscription reqMktData, persistante à travers les reco.
        """
        rec = SubRecord(contract, genericTickList, snapshot, regulatorySnapshot, options)
        self._subs[key] = rec

        if not self.ib.isConnected():
            return None

        # Idempotent côté IB : refaire reqMarketDataType(1) ne casse rien.
        with contextlib.suppress(Exception):
            self.ib.reqMarketDataType(1)

        try:
            t = self.ib.reqMktData(
                contract,
                genericTickList=genericTickList,
                snapshot=snapshot,
                regulatorySnapshot=regulatorySnapshot,
                mktDataOptions=options
            )
            rec.ticker = t
            return t
        except Exception as e:
            log.error(f"[IBRM] subscribe({key}) failed: {e}")
            return None

    def unsubscribe(self, key: str) -> None:
        rec = self._subs.pop(key, None)
        if not rec:
            return
        # Annule “proprement” via le Contract (plus robuste)
        with contextlib.suppress(Exception):
            if rec.ticker is not None and getattr(rec.ticker, "contract", None):
                self.ib.cancelMktData(rec.ticker.contract)
        with contextlib.suppress(Exception):
            if rec.ticker is not None:
                self.ib.cancelMktData(rec.ticker)
        rec.ticker = None

    def tickers(self) -> Dict[str, Ticker]:
        return {k: v.ticker for k, v in self._subs.items() if v.ticker}

    # ════════════════════════════════════════════════════════
    # Internals
    # ════════════════════════════════════════════════════════
    def _attach_handlers(self) -> None:
        # Évite doublons quand on recrée IB (auto-heal)
        with contextlib.suppress(Exception):
            self.ib.connectedEvent.clear()
            self.ib.disconnectedEvent.clear()
        self.ib.connectedEvent += self._on_ib_connected
        self.ib.disconnectedEvent += self._on_ib_disconnected

    async def _connect_with_retry(self) -> None:
        backoff = RECONNECT_FIRST_BACKOFF
        while True:
            cid = self._next_client_id()
            try:
                await self.ib.connectAsync(self.host, self.port, clientId=cid, timeout=8)
                self._current_client_id = cid
                log.info("✅ [IBRM] Connected (clientId=%s)", cid)
                with contextlib.suppress(Exception):
                    self.ib.reqMarketDataType(1)
                for cb in self.on_connected:
                    self._safe(cb)
                # Hook de rebind immédiat (cas: start() initial)
                if self.on_rebind_ib:
                    self._safe_rebind(self.ib)
                return
            except Exception as e:
                msg = (str(e) or "").lower()
                if "clientid" in msg and "in use" in msg:
                    log.warning("[IBRM] clientId %s already in use → rotating…", cid)
                    # Ré-essaie immédiatement avec un autre clientId
                    continue
                if "refus" in msg or "refusé" in msg or "refused" in msg:
                    log.error("API connection failed: %s", e)
                    log.error("Make sure API port on TWS/IBG is open")
                else:
                    log.error("[IBRM] Connect failed (%s)", e)
                log.error("[IBRM] Retry in %ss", backoff)
                await asyncio.sleep(backoff)
                backoff = min(RECONNECT_MAX_BACKOFF, backoff * 2)

    def _next_client_id(self) -> int:
        span = max(1, int(self.client_span))
        return int(self.base_client_id + random.randint(0, span))

    def _on_ib_connected(self) -> None:
        for cb in self.on_connected:
            self._safe(cb)

    def _on_ib_disconnected(self) -> None:
        log.error("[IBRM] disconnectedEvent (peer closed connection?)")
        for cb in self.on_disconnected:
            self._safe(cb)
        util.getLoop().create_task(self._on_disconnect_sequence(), name="IBRM.reconnect")

    async def _on_disconnect_sequence(self) -> None:
        if self._reconnecting:
            return
        self._reconnecting = True
        log.warning("[IBRM] Disconnected → reconnecting…")
        for cb in self.on_suspend:
            self._safe(cb)

        # Disconnect “propre” (non bloquant)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.ib.disconnectAsync(), timeout=2)

        # Tentative de reco; si la socket reste sale → recrée IB et re-bind handlers
        healed = False
        for attempt in range(2):
            try:
                await self._connect_with_retry()
                healed = True
                break
            except Exception:
                pass
            log.warning("[IBRM] Recreating IB instance (auto-heal)…")
            try:
                self.ib = IB()
                self._attach_handlers()
            except Exception as e:
                log.error("[IBRM] IB recreate failed: %s", e)

        if not healed and not self.ib.isConnected():
            # Dernière cartouche
            self.ib = IB()
            self._attach_handlers()
            await self._connect_with_retry()

        # Rebind IB d’abord (DataHub/ContractManager), puis resub
        if self.on_rebind_ib:
            self._safe_rebind(self.ib)

        log.info("[IBRM] Reconnected, resubscribing…")
        await self._resubscribe_all()
        await self._wait_feed_stable()
        log.info("[IBRM] Feed stable → resumed")

        for cb in self.on_resume:
            self._safe(cb)
        for cb in self.on_resubscribed:
            self._safe(cb)

        self._reconnecting = False

    def _safe_rebind(self, ib: IB) -> None:
        # évite double rebind si callbacks se déclenchent deux fois rapidement
        now = time.time()
        if now - self._last_rebind_ts < 0.5:
            return
        self._last_rebind_ts = now
        try:
            self.on_rebind_ib and self.on_rebind_ib(ib)
        except Exception as e:
            log.error("[IBRM] on_rebind_ib error: %s", e)

    async def _resubscribe_all(self) -> None:
        # Re-issue reqMktData pour chaque sub connue (idempotent côté TWS)
        with contextlib.suppress(Exception):
            self.ib.reqMarketDataType(1)
        for key, rec in self._subs.items():
            try:
                rec.ticker = self.ib.reqMktData(
                    rec.contract,
                    genericTickList=rec.genericTickList,
                    snapshot=rec.snapshot,
                    regulatorySnapshot=rec.regulatorySnapshot,
                    mktDataOptions=rec.options
                )
                log.info("[IBRM] Resub %s ✓", key)
            except Exception as e:
                log.error("[IBRM] Resub %s failed: %s", key, e)

    async def _wait_feed_stable(self) -> None:
        start = time.time()
        while True:
            ready = 0
            for rec in self._subs.values():
                t = rec.ticker
                if not t:
                    continue
                try:
                    # “vivant” si on observe last/close/marketPrice
                    if (t.last is not None) or (t.close is not None) or (t.marketPrice() is not None):
                        ready += 1
                except Exception:
                    pass
            if ready >= MIN_TICKERS_READY and (time.time() - start) >= MIN_STABLE_WINDOW_SEC:
                break
            await asyncio.sleep(0.2)

    async def _watchdog(self) -> None:
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_SEC)
                if not self.ib.isConnected():
                    continue
                try:
                    await asyncio.wait_for(self.ib.reqCurrentTimeAsync(), timeout=HB_TIMEOUT_SEC)
                except Exception as e:
                    log.warning("[IBRM] Heartbeat KO: %s → reconnect", e)
                    await self._on_disconnect_sequence()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[IBRM] Watchdog error: %s", e)

    async def _supervisor(self) -> None:
        """Filet de sécurité: si on est déconnecté et inactif, force une reco."""
        while True:
            try:
                await asyncio.sleep(SUPERVISOR_SEC)
                if self._reconnecting:
                    continue
                if not self.ib.isConnected():
                    log.warning("[IBRM] Supervisor: not connected → reconnect")
                    await self._on_disconnect_sequence()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[IBRM] Supervisor error: %s", e)

    @staticmethod
    def _safe(cb: ExternalCB) -> None:
        try:
            cb()
        except Exception as e:
            log.error("[IBRM] Callback error: %s", e)
