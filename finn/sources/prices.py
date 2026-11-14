"""End-of-day price & volume. yfinance first, Yahoo chart API as a fallback,
NSE suffix first then BSE."""
from datetime import datetime, timezone

from ..http import get, session


def _rows_from_df(sub):
    rows = []
    sub = sub.dropna(subset=["Close"])
    for idx, r in sub.iterrows():
        vol = r.get("Volume")
        rows.append({"d": idx.strftime("%Y-%m-%d"), "c": round(float(r["Close"]), 2),
                     "v": int(vol) if vol == vol and vol is not None else 0})
    return rows


def _yf(tickers, period):
    import yfinance as yf
    df = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                     auto_adjust=False, progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            sub = df[t] if len(tickers) > 1 else df
            if hasattr(sub.columns, "levels") and t in sub.columns.get_level_values(0):
                sub = sub[t]
            rows = _rows_from_df(sub)
            if rows:
                out[t] = rows
        except Exception:
            continue
    return out


def _chart_api(ticker, rng="6mo"):
    s = session()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={rng}&interval=1d"
    j = get(s, url, tries=2).json()
    res = j["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for ts, c, v in zip(res["timestamp"], q["close"], q["volume"]):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append({"d": d, "c": round(c, 2), "v": int(v or 0)})
    return rows


def fetch_eod(symbols, period="6mo"):
    """-> {SYMBOL: [{d, c, v}, ...] oldest first}"""
    out = {}
    try:
        got = _yf([s + ".NS" for s in symbols], period)
        out = {t[:-3]: rows for t, rows in got.items()}
    except Exception as e:
        print(f"  ! yfinance failed: {e}")
    for s in symbols:
        if s in out and len(out[s]) > 25:
            continue
        for suffix in (".NS", ".BO"):
            try:
                rows = _chart_api(s + suffix)
                if rows:
                    out[s] = rows
                    break
            except Exception:
                continue
    return out
