# engine/aggregator.py
from __future__ import annotations
import os, pickle, atexit, threading, time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Optional, Any

DEBUG_VOLUME = False 
MAX_VALID_TICK_SIZE = 5000 

NY = ZoneInfo("America/New_York")
def _session_key() -> str:
    now = datetime.now(tz=NY)
    return str(now.date() if now.hour < 18 else (now + timedelta(days=1)).date())

_DATA_DIR = "./data"
os.makedirs(_DATA_DIR, exist_ok=True)

def _snap_to_grid(px: float, tick: float) -> float:
    if tick <= 0: return float(px)
    steps = round(px / tick)
    val = steps * tick
    return float(f"{val:.6f}")

class RollingProfile:
    def __init__(self, max_history_sec=7200):
        self.history = deque() # (ts, px, size, dir)
        self.max_history_sec = max_history_sec

    def add(self, px, size, direction):
        now = time.time()
        self.history.append((now, px, size, direction))
        if len(self.history) % 100 == 0:
            limit = now - self.max_history_sec
            while self.history and self.history[0][0] < limit:
                self.history.popleft()

    def get_profile(self, mode: str, value: int):
        data = defaultdict(float)
        delta = defaultdict(float)
        mode_clean = mode.lower().strip()
        
        # --- BLINDAGE LECTURE HISTORIQUE ---
        # On prépare les variables de boucle pour éviter les erreurs de crash
        
        if mode_clean == "time":
            now = time.time()
            limit = now - (value * 60)
            for i in range(len(self.history) - 1, -1, -1):
                item = self.history[i]
                # Protection contre vieux format (qui n'avait pas direction)
                if len(item) == 4: ts, px, size, direction = item
                else: ts, px, size = item[0], item[1], item[2]; direction = 1
                
                if ts < limit: break
                data[px] += size
                delta[px] += (size * direction)
                
        elif mode_clean == "vol":
            cum_vol = 0
            for i in range(len(self.history) - 1, -1, -1):
                item = self.history[i]
                if len(item) == 4: ts, px, size, direction = item
                else: ts, px, size = item[0], item[1], item[2]; direction = 1
                
                cum_vol += size
                data[px] += size
                delta[px] += (size * direction)
                if cum_vol >= value: break 

        return data, delta

    def get_candles(self, mode: str, value: int, limit_candles=100):
        if not self.history: return []
        candles = []
        hist = list(self.history)
        current_candle = { "open": None, "high": -float('inf'), "low": float('inf'), "close": None, "vol": 0, "delta": 0, "ts": 0 }
        bucket_end_time = 0
        mode_clean = mode.lower().strip()
        
        if mode_clean == "time":
            tf_sec = value 
            if hist:
                # Protection lecture premier item
                first_item = hist[0]
                ts_start = first_item[0]
                bucket_end_time = (int(ts_start) // tf_sec) * tf_sec + tf_sec
        
        for item in hist:
            # Protection lecture item
            if len(item) == 4: ts, px, size, direc = item
            else: ts, px, size = item[0], item[1], item[2]; direc = 1

            is_new = False
            if mode_clean == "time":
                if ts >= bucket_end_time:
                    is_new = True
                    bucket_end_time = (int(ts) // tf_sec) * tf_sec + tf_sec
            elif mode_clean == "vol":
                if current_candle["vol"] >= value: is_new = True
            
            if is_new and current_candle["open"] is not None:
                candles.append(current_candle)
                current_candle = { "open": None, "high": -float('inf'), "low": float('inf'), "close": None, "vol": 0, "delta": 0, "ts": ts }

            if current_candle["open"] is None: 
                current_candle["open"] = px; current_candle["ts"] = ts
            current_candle["high"] = max(current_candle["high"], px)
            current_candle["low"] = min(current_candle["low"], px)
            current_candle["close"] = px
            current_candle["vol"] += size
            current_candle["delta"] += (size * direc)

        if current_candle["open"] is not None:
            candles.append(current_candle)
            
        return candles[-limit_candles:]
    
    def get_vwap(self, minutes: int):
        total_pv = 0.0; total_vol = 0.0
        now = time.time(); limit = now - (minutes * 60)
        for i in range(len(self.history) - 1, -1, -1):
            item = self.history[i]
            if len(item) == 4: ts, px, size, _ = item
            else: ts, px, size = item[0], item[1], item[2]
            
            if ts < limit: break
            total_pv += (px * size); total_vol += size
        return (total_pv / total_vol) if total_vol > 0 else None

    def __getstate__(self):
        return {'history': list(self.history), 'max_history_sec': self.max_history_sec}
    def __setstate__(self, state):
        self.history = deque(state.get('history', []))
        self.max_history_sec = state.get('max_history_sec', 7200)

class Aggregator:
    _SESSION = _session_key()
    _SCHEMA  = 33 # On garde le schema

    def __init__(self, ctx, autosave_secs=30, persist=False, tick_size_map=None, prefer_mode="auto"):
        self.ctx = ctx
        self._persist = bool(persist)

        self.volume_by_price = defaultdict(lambda: defaultdict(float))
        self.delta_session = defaultdict(lambda: defaultdict(float))
        self.dom = defaultdict(lambda: {'bids': defaultdict(int), 'asks': defaultdict(int)})
        self.rolling_profiles = defaultdict(RollingProfile)
        self.active_windows = defaultdict(lambda: 30) 
        self._speed_buffer = defaultdict(deque)
        self.vwap_data = defaultdict(lambda: {"total_pv": 0.0, "total_vol": 0.0})

        self._prev_price = {}; self._prev_dir = defaultdict(lambda: 1)
        self.last_price = {}; self.start_time = {}; self._rt_total_seen = {}
        self._tick_size = defaultdict(lambda: 0.25)
        if tick_size_map:
            for k, v in tick_size_map.items():
                try: self._tick_size[k] = float(v) if v else 0.25
                except: self._tick_size[k] = 0.25

        self._alias = {}; self._last_seen = defaultdict(lambda: (None, None))
        self._booted = defaultdict(lambda: False); self._tbt_idx = defaultdict(int)
        self._prefer_tbt_sym = defaultdict(bool); self._prefer_mode = (prefer_mode or "auto").strip().lower()

        if self._persist: self._load_session()
        if self._persist and int(autosave_secs) > 0:
            t = threading.Thread(target=self._autosave_loop, args=(int(autosave_secs),), daemon=True)
            t.start()
            atexit.register(self._dump_session)

    def _key(self, sym: str) -> str: return self._alias.get(sym, sym)
    def get_last_price(self, sym): return self.last_price.get(self._key(sym))
    def get_speed(self, sym: str, window_sec: float=60.0):
        s = self._key(sym); buf = self._speed_buffer[s]; now = time.time(); limit = now - window_sec
        while buf and buf[0][0] < limit: buf.popleft()
        return float(sum(item[1] for item in buf))

    def set_rolling_window(self, sym: str, minutes: int): pass
    def get_rolling_data(self, sym: str, mode: str, value: int):
        s = self._key(sym)
        if s not in self.rolling_profiles: self.rolling_profiles[s] = RollingProfile()
        return self.rolling_profiles[s].get_profile(mode, value)
    def get_candles_data(self, sym: str, mode: str = "time", value: int = 60):
        s = self._key(sym)
        if s not in self.rolling_profiles: return []
        return self.rolling_profiles[s].get_candles(mode, value)
    def get_rolling_vwap(self, sym: str, minutes: int = 60) -> Optional[float]:
        s = self._key(sym)
        if s not in self.rolling_profiles: return None
        return self.rolling_profiles[s].get_vwap(minutes)
    def get_vwap(self, sym: str) -> Optional[float]:
        s = self._key(sym); d = self.vwap_data[s]
        return (d["total_pv"] / d["total_vol"]) if d["total_vol"] > 0 else None

    def reset_session(self, sym: str | None = None):
        keys = [self._key(sym)] if sym else list(self.volume_by_price.keys())
        for s in keys:
            self.volume_by_price.pop(s, None)
            self.delta_session.pop(s, None)
            if s in self.rolling_profiles: self.rolling_profiles[s] = RollingProfile()
            self.last_price.pop(s, None)
            self._speed_buffer.pop(s, None)
            if s in self._rt_total_seen: del self._rt_total_seen[s]
            self._tbt_idx.pop(s, None); self._prefer_tbt_sym.pop(s, None)
            if s in self.dom: self.dom[s] = {'bids': defaultdict(int), 'asks': defaultdict(int)}
            self.vwap_data.pop(s, None) 
        if self._persist: self._dump_session()

    def on_dom_update(self, sym: str, bids: List[Tuple[float, int]], asks: List[Tuple[float, int]]):
        s = self._key(sym); tick = self._tick_size[s]
        new_bids = defaultdict(int)
        for p, sz in bids:
            if sz > 0: new_bids[_snap_to_grid(p, tick)] += int(sz)
        self.dom[s]['bids'] = new_bids
        new_asks = defaultdict(int)
        for p, sz in asks:
            if sz > 0: new_asks[_snap_to_grid(p, tick)] += int(sz)
        self.dom[s]['asks'] = new_asks

    def _ingest(self, sym, px, size, *, source):
        if size > MAX_VALID_TICK_SIZE: return 
        if sym not in self.start_time: self.start_time[sym] = datetime.now(tz=NY)
        tick_sz = self._tick_size[sym]; px_snap = _snap_to_grid(px, tick_sz)
        prev = self._prev_price.get(sym, px); direc = self._prev_dir[sym]
        if px > prev: direc = 1 
        elif px < prev: direc = -1 
        self._prev_price[sym] = px; self._prev_dir[sym] = direc
        self.last_price[sym] = px_snap
        self.volume_by_price[sym][px_snap] += size
        self.delta_session[sym][px_snap] += (size * direc)
        self.vwap_data[sym]["total_pv"] += (px * size)
        self.vwap_data[sym]["total_vol"] += size
        self.rolling_profiles[sym].add(px_snap, size, direc)
        self._speed_buffer[sym].append((time.time(), size))

    def on_tick(self, sym: str, tick: Any) -> None:
        if tick is None: return
        sym_log = self._key(sym)
        ingested = False
        if self._prefer_mode in ("auto", "tbt"):
            try:
                tbt = getattr(tick, "tickByTicks", None)
                if tbt:
                    start = self._tbt_idx[sym]; n = len(tbt)
                    if start < n:
                        for rec in tbt[start:n]:
                            px = getattr(rec, "price", None); sz = getattr(rec, "size", None)
                            if px and sz and sz > 0:
                                if self._persist:
                                    key = (float(px), float(sz))
                                    if not self._booted[sym_log] and self._last_seen[sym_log] == key: 
                                        self._booted[sym_log] = True; continue
                                    self._booted[sym_log] = True; self._last_seen[sym_log] = key
                                self._ingest(sym_log, float(px), float(sz), source="TBT")
                                ingested = True; self._prefer_tbt_sym[sym_log] = True
                        self._tbt_idx[sym] = n
            except: pass
        if (not ingested) and (self._prefer_mode in ("auto", "rtv")) and (not self._prefer_tbt_sym[sym_log]):
            px, size, total = None, None, None
            rt = getattr(tick, "rtVolume", None)
            if rt:
                try:
                    p = str(rt).split(";")
                    if len(p) >= 4: px=float(p[0]) if p[0] else None; size=float(p[1]) if p[1] else None; total=float(p[3]) if p[3] else None
                except: pass
            if total is not None:
                if sym_log not in self._rt_total_seen: self._rt_total_seen[sym_log] = total; size = 0 
                else:
                    prev = self._rt_total_seen[sym_log]
                    if total > prev: size = total - prev
                    self._rt_total_seen[sym_log] = total
            if px and size and size > 0:
                if self._persist:
                    key = (px, size)
                    if not self._booted[sym_log] and self._last_seen[sym_log] == key: 
                        self._booted[sym_log] = True; return
                    self._booted[sym_log] = True; self._last_seen[sym_log] = key
                self._ingest(sym_log, px, size, source="RTV")
                ingested = True
        if not ingested:
            last = getattr(tick, "last", None); lsz = getattr(tick, "lastSize", None)
            if last and lsz and lsz > 0:
                px, size = float(last), float(lsz)
                key = (px, size)
                if self._last_seen[sym_log] != key:
                    self._last_seen[sym_log] = key
                    self._ingest(sym_log, px, size, source="LAST")
    def _snapshot(self):
        return { "session": self._SESSION, "schema": self._SCHEMA, "vbp": {s: dict(v) for s, v in self.volume_by_price.items()}, "last_px": dict(self.last_price), "tick_sz": dict(self._tick_size), "vwap": dict(self.vwap_data), "rolling": self.rolling_profiles }
    def _dump_session(self):
        if not self._persist: return
        fn = os.path.join(_DATA_DIR, f"aggregator_{self._SESSION}.pkl")
        try: pickle.dump(self._snapshot(), open(fn, "wb"), protocol=4)
        except: pass
    def _load_session(self):
        fn = os.path.join(_DATA_DIR, f"aggregator_{self._SESSION}.pkl")
        if not os.path.exists(fn): return
        try:
            snap = pickle.load(open(fn, "rb"))
            if snap.get("session") != self._SESSION: return
            if snap.get("schema") != self._SCHEMA: return 
            self.volume_by_price = defaultdict(lambda: defaultdict(float), {k: defaultdict(float, v) for k, v in snap.get("vbp", {}).items()})
            self.last_price = dict(snap.get("last_px", {}))
            for k, v in snap.get("tick_sz", {}).items(): self._tick_size[k] = float(v)
            if "vwap" in snap:
                for k, v in snap["vwap"].items(): self.vwap_data[k] = v
            if "rolling" in snap:
                loaded = snap["rolling"]
                self.rolling_profiles = defaultdict(RollingProfile)
                for k, v in loaded.items():
                    if isinstance(v, RollingProfile): self.rolling_profiles[k] = v
        except: pass
    def _autosave_loop(self, secs):
        while True: time.sleep(secs); self._dump_session()