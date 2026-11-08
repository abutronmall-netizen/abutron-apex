"""Real market data -> the same `Panel` the simulator produces.

Sources (no API key needed):
    crypto     Kraken  public OHLC endpoint   (BTCUSD, ETHUSD)
    equities   Yahoo   chart endpoint         (SPY, QQQ, NVDA)
    fx/indices Yahoo   chart endpoint         (EURUSD=X, ^GSPC, ^GDAXI)
    synthetics Deriv   wss ticks_history      (R_75, R_100, BOOM500, CRASH500, stpRNG)

Everything is cached to CSV under `data_cache/` so a run is reproducible offline
and so you can eyeball the raw bars.

The panel is built on a strict UTC-hour grid:
  * a symbol is `active` on an hour only if it has a real bar *and* the hour is
    inside its session (equities 14-21, fx 07-21) -> the engine never trades a
    stale price,
  * closed hours are forward-filled so indicators see a continuous series.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..config import Cfg
from .base import Panel, in_session

from ..paths import data_path

CACHE = data_path("data_cache")

# symbol -> (source, source_symbol, asset_class, kind)
MAP: Dict[str, tuple] = {
    "BTCUSD": ("okx", "BTC-USDT", "crypto", "trend"),
    "ETHUSD": ("okx", "ETH-USDT", "crypto", "trend"),
    "SPY": ("yahoo", "SPY", "us_equity", "trend"),
    "QQQ": ("yahoo", "QQQ", "us_equity", "trend"),
    "NVDA": ("yahoo", "NVDA", "us_equity", "trend"),
    "EURUSD": ("yahoo", "EURUSD=X", "fx_index", "fx"),
    "US500": ("yahoo", "^GSPC", "fx_index", "index"),
    "GER40": ("yahoo", "^GDAXI", "fx_index", "index"),
    "R_75": ("deriv", "R_75", "deriv_synthetic", "volatility"),
    "R_100": ("deriv", "R_100", "deriv_synthetic", "volatility"),
    "BOOM500": ("deriv", "BOOM500", "deriv_synthetic", "boom"),
    "CRASH500": ("deriv", "CRASH500", "deriv_synthetic", "crash"),
    "stpRNG": ("deriv", "stpRNG", "deriv_synthetic", "step"),
}

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                     "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
      "Accept": "application/json,text/plain,*/*"}


# --------------------------------------------------------------------------- http
def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:                                            # noqa: BLE001
        import subprocess
        out = subprocess.run(["curl", "-sSL", "--http1.1", "--max-time", str(timeout),
                              url],
                             capture_output=True, check=True)
        if not out.stdout:
            raise RuntimeError(f"empty response for {url}")
        return out.stdout


def okx_ohlc(inst: str = "BTC-USDT", bar: str = "1H", bars: int = 4320) -> np.ndarray:
    """Hourly OHLCV from OKX, paginated backwards. float array [n,6] = ts..volume."""
    out: List[List[float]] = []
    after = ""
    while len(out) < bars:
        url = (f"https://www.okx.com/api/v5/market/history-candles?instId={inst}"
               f"&bar={bar}&limit=100" + (f"&after={after}" if after else ""))
        js = json.loads(_get(url))
        if js.get("code") != "0":
            raise RuntimeError(f"okx {inst}: {js.get('msg')}")
        rows = js["data"]
        if not rows:
            break
        out.extend([[float(r[0]) / 1000.0, float(r[1]), float(r[2]), float(r[3]),
                     float(r[4]), float(r[5])] for r in rows])
        after = rows[-1][0]
        time.sleep(0.08)
    arr = np.array(sorted(out, key=lambda r: r[0]))
    _, idx = np.unique(arr[:, 0], return_index=True)
    return arr[idx][-bars:]


def yahoo_chart(symbol: str, interval: str = "1h", range_: str = "180d",
                tries: int = 5) -> np.ndarray:
    """Hourly OHLCV from Yahoo Finance (retries on 429). Returns float array [n,6]."""
    q = urllib.parse.quote(symbol, safe="")
    last: Optional[Exception] = None
    for attempt in range(tries):
        host = "query1" if attempt % 2 == 0 else "query2"
        url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}"
               f"?interval={interval}&range={range_}&includePrePost=false")
        try:
            js = json.loads(_get(url))
            break
        except Exception as e:                                # noqa: BLE001
            last = e
            time.sleep(4.0 * (attempt + 1))
    else:
        raise RuntimeError(f"yahoo {symbol}: {last}")
    res = js["chart"]["result"]
    if not res:
        raise RuntimeError(f"yahoo {symbol}: no result ({js['chart'].get('error')})")
    r = res[0]
    ts = r["timestamp"]
    q0 = r["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q0["open"][i], q0["high"][i], q0["low"][i], q0["close"][i], q0["volume"][i])
        if None in (o, h, l, c):
            continue
        rows.append([float(t), o, h, l, c, v or 0.0])
    return np.array(rows, dtype=float)


def deriv_candles(symbol: str, granularity: int = 3600, count: int = 5000,
                  app_id: str = "1089", timeout: int = 25) -> np.ndarray:
    """Hourly candles for a Deriv synthetic via the public ticks_history call."""
    import websockets

    async def _fetch() -> List[List[float]]:
        url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
        async with websockets.connect(url, open_timeout=timeout,
                                      additional_headers={"Origin": "https://app.deriv.com"}) as ws:
            await ws.send(json.dumps({"ticks_history": symbol, "adjust_start_time": 1,
                                      "count": count, "end": "latest",
                                      "granularity": granularity, "style": "candles"}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout * 2))
        if "error" in msg:
            raise RuntimeError(f"deriv {symbol}: {msg['error']['message']}")
        return [[float(c["epoch"]), float(c["open"]), float(c["high"]),
                 float(c["low"]), float(c["close"])] for c in msg["candles"]]

    rows = asyncio.run(_fetch())
    arr = np.array(rows, dtype=float)
    return np.column_stack([arr, np.zeros(len(arr))])


# --------------------------------------------------------------------------- cache
def fetch(symbol: str, refresh: bool = False) -> Optional[np.ndarray]:
    """Fetch one symbol (cached). Returns None if the source is unreachable."""
    if symbol not in MAP:
        return None
    src, src_sym, _ac, _kind = MAP[symbol]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{symbol}.csv"
    if path.exists() and not refresh:
        return np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    try:
        if src == "okx":
            arr = okx_ohlc(src_sym)
        elif src == "yahoo":
            arr = yahoo_chart(src_sym)
        else:
            arr = deriv_candles(src_sym)
    except Exception as e:                                    # noqa: BLE001
        print(f"  ! {symbol:<8s} {src:<6s} unreachable: {type(e).__name__}: {str(e)[:70]}")
        return None
    np.savetxt(path, arr, delimiter=",", header="ts,open,high,low,close,volume",
               comments="", fmt="%.6f")
    print(f"  + {symbol:<8s} {src:<6s} {len(arr):>5d} bars  "
          f"{time.strftime('%Y-%m-%d', time.gmtime(arr[0, 0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(arr[-1, 0]))}")
    return arr


def fetch_all(symbols: List[str], refresh: bool = False) -> Dict[str, np.ndarray]:
    print(f"fetching {len(symbols)} symbols -> {CACHE}")
    out = {}
    for i, s in enumerate(symbols):
        a = fetch(s, refresh)
        if a is not None and len(a):
            out[s] = a
        if i and MAP[s][0] == "yahoo":
            time.sleep(4.0)          # stay under Yahoo's burst limit
    return out


# --------------------------------------------------------------------------- panel
def build_real_panel(cfg: Cfg, refresh: bool = False,
                     symbols: Optional[List[str]] = None) -> Panel:
    """Align real bars into the engine's Panel on a UTC-hour grid."""
    universe = {u["symbol"]: u for u in cfg["universe"]}
    symbols = symbols or list(universe)
    raw = fetch_all(symbols, refresh)
    missing = [s for s in symbols if s not in raw]
    if missing:
        print(f"  (no real data for {missing} -> excluded from this run)")

    # common window: from the latest first-bar to the earliest last-bar
    lo = max(float(a[0, 0]) for a in raw.values())
    hi = min(float(a[-1, 0]) for a in raw.values())
    grid = np.arange(np.ceil(lo / 3600) * 3600, hi + 1, 3600.0)
    n = len(grid)
    if n < 400:
        raise RuntimeError(f"only {n} overlapping hourly bars across {list(raw)}")

    o, h, l, c, v, active = {}, {}, {}, {}, {}, {}
    for s, arr in raw.items():
        ac = universe[s]["asset_class"]
        pos = np.searchsorted(arr[:, 0], grid)
        pos = np.clip(pos, 0, len(arr) - 1)
        has = np.abs(arr[pos, 0] - grid) < 1.0
        # forward-fill everything from the last real bar
        idx = np.maximum.accumulate(np.where(has, np.arange(n), 0))
        o[s], h[s], l[s], c[s], v[s] = arr[idx, 1], arr[idx, 2], arr[idx, 3], arr[idx, 4], arr[idx, 5]
        hours = ((grid // 3600) % 24).astype(int)
        sess = np.array([in_session(ac, int(x)) for x in hours])
        active[s] = has & sess

    panel = Panel(symbols=list(raw), ts=grid, o=o, h=h, l=l, c=c, v=v, active=active,
                  asset_class={s: universe[s]["asset_class"] for s in raw})
    panel.is_real = True
    return panel


# ------------------------------------------------------------------ daily sources
MAP_DAILY: Dict[str, tuple] = {
    "BTCUSD": ("okx", "BTC-USDT"),
    "ETHUSD": ("okx", "ETH-USDT"),
    "SPY": ("nasdaq", "SPY", "etf"),
    "QQQ": ("nasdaq", "QQQ", "etf"),
    "NVDA": ("nasdaq", "NVDA", "stocks"),
    "US500": ("fred", "SP500"),
    "EURUSD": ("fred", "DEXUSEU"),
}


def nasdaq_daily(symbol: str, assetclass: str = "stocks",
                 start: str = "2022-11-01", end: Optional[str] = None) -> np.ndarray:
    """Daily OHLCV from Nasdaq's public quote chart endpoint."""
    end = end or time.strftime("%Y-%m-%d")
    url = (f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(symbol)}/chart"
           f"?assetclass={assetclass}&fromdate={start}&todate={end}")
    js = json.loads(_get(url))
    rows = (js.get("data") or {}).get("chart") or []
    out = []
    for r in rows:
        z = r.get("z") or {}
        try:
            out.append([float(r["x"]) / 1000.0,
                        float(z["open"]), float(z["high"]), float(z["low"]),
                        float(z["close"]),
                        float(str(z.get("volume", "0")).replace(",", ""))])
        except (KeyError, TypeError, ValueError):
            continue
    return np.array(sorted(out, key=lambda r: r[0]), dtype=float)


def fred_series(series: str, start: str = "2022-11-01") -> np.ndarray:
    """Daily close-only series from FRED (FX, index levels). o=h=l=c."""
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
           f"&cosd={start}")
    text = _get(url).decode()
    out = []
    for line in text.splitlines()[1:]:
        a, _, b = line.partition(",")
        if not b or b.strip() in (".", ""):
            continue
        try:
            ts = time.mktime(time.strptime(a.strip(), "%Y-%m-%d")) - time.timezone
            px = float(b)
        except ValueError:
            continue
        out.append([ts, px, px, px, px, 0.0])
    return np.array(out, dtype=float)


def fetch_daily(symbol: str, refresh: bool = False) -> Optional[np.ndarray]:
    if symbol not in MAP_DAILY:
        return None
    spec = MAP_DAILY[symbol]
    src, src_sym = spec[0], spec[1]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{symbol}_1D.csv"
    if path.exists() and not refresh:
        return np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    try:
        if src == "okx":
            arr = okx_ohlc(src_sym, bar="1D", bars=1500)
        elif src == "nasdaq":
            arr = nasdaq_daily(src_sym, spec[2])
        else:
            arr = fred_series(src_sym)
    except Exception as e:                                    # noqa: BLE001
        print(f"  ! {symbol:<8s} {src:<7s} unreachable: {type(e).__name__}: {str(e)[:60]}")
        return None
    if not len(arr):
        print(f"  ! {symbol:<8s} {src:<7s} returned 0 rows")
        return None
    np.savetxt(path, arr, delimiter=",", header="ts,open,high,low,close,volume",
               comments="", fmt="%.6f")
    print(f"  + {symbol:<8s} {src:<7s} {len(arr):>5d} bars  "
          f"{time.strftime('%Y-%m-%d', time.gmtime(arr[0, 0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(arr[-1, 0]))}")
    time.sleep(1.2)
    return arr


def build_real_panel_daily(cfg: Cfg, refresh: bool = False,
                           symbols: Optional[List[str]] = None) -> Panel:
    """Daily-bar real panel: one row per UTC day, session masks off."""
    from .base import set_period

    set_period("1D")
    universe = {u["symbol"]: u for u in cfg["universe"]}
    symbols = [s for s in (symbols or list(universe)) if s in MAP_DAILY]
    raw = {}
    print(f"fetching {len(symbols)} symbols (daily) -> {CACHE}")
    for s in symbols:
        a = fetch_daily(s, refresh)
        if a is not None and len(a):
            raw[s] = a
    missing = [s for s in symbols if s not in raw]
    if missing:
        print(f"  (no real data for {missing} -> excluded)")

    lo = max(float(a[0, 0]) for a in raw.values())
    hi = min(float(a[-1, 0]) for a in raw.values())
    DAY = 86400.0
    grid = np.arange(np.ceil(lo / DAY) * DAY, hi + 1, DAY)
    n = len(grid)

    o, h, l, c, v, active = {}, {}, {}, {}, {}, {}
    for s, arr in raw.items():
        day = np.floor(arr[:, 0] / DAY) * DAY
        idx_of = {int(d): i for i, d in enumerate(day)}
        rows = np.array([idx_of.get(int(d), -1) for d in grid])
        has = rows >= 0
        ff = np.maximum.accumulate(np.where(has, rows, 0))     # forward-filled row index
        src = np.where(has, rows, ff)
        o[s], h[s], l[s], c[s], v[s] = arr[src, 1], arr[src, 2], arr[src, 3], arr[src, 4], arr[src, 5]
        active[s] = has

    panel = Panel(symbols=list(raw), ts=grid, o=o, h=h, l=l, c=c, v=v, active=active,
                  asset_class={s: universe[s]["asset_class"] for s in raw})
    panel.is_real = True
    return panel
