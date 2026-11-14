"""Corporate announcements. NSE API (needs a cookie warm-up) with BSE as a
fallback per symbol. Both are normalised to one shape:

{id, symbol, exchange, subject, text, ts (ISO, IST), url}
"""
import hashlib
from datetime import datetime

from ..http import FetchError, get, session

NSE_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_API = ("https://www.nseindia.com/api/corporate-announcements?index=equities"
           "&from_date={f}&to_date={t}&symbol={sym}")
BSE_API = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno={p}"
           "&strCat=-1&strPrevDate={f}&strScrip={code}&strSearch=P&strToDate={t}"
           "&strType=C&subcategory=-1")
BSE_PDF = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{}"


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _parse_nse_dt(s):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            pass
    return None


def normalize_nse(item, symbol=None):
    dt = _parse_nse_dt(item.get("an_dt") or item.get("sort_date") or "")
    if dt is None and item.get("sort_date"):
        try:
            dt = datetime.strptime(item["sort_date"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            dt = None
    if dt is None:
        return None
    sym = item.get("symbol") or symbol
    sid = item.get("seq_id") or hashlib.md5(
        f"{sym}{item.get('an_dt')}{item.get('desc')}".encode()).hexdigest()[:12]
    return {
        "id": f"nse:{sid}",
        "symbol": sym,
        "exchange": "NSE",
        "subject": (item.get("desc") or "").strip(),
        "text": (item.get("attchmntText") or "").strip(),
        "ts": _iso(dt),
        "url": item.get("attchmntFile") or "",
    }


def normalize_bse(item, symbol):
    raw = item.get("NEWS_DT") or item.get("DT_TM") or ""
    dt = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(raw[:26], fmt)
            break
        except Exception:
            continue
    if dt is None:
        return None
    subj = item.get("SUBCATNAME") or item.get("CATEGORYNAME") or ""
    head = (item.get("NEWSSUB") or item.get("HEADLINE") or "").strip()
    att = item.get("ATTACHMENTNAME") or ""
    return {
        "id": f"bse:{item.get('NEWSID')}",
        "symbol": symbol,
        "exchange": "BSE",
        "subject": subj.strip() or head,
        "text": " ".join(x for x in [head, (item.get("HEADLINE") or "").strip()] if x)[:1200],
        "ts": _iso(dt),
        "url": BSE_PDF.format(att) if att else "",
    }


class NSE:
    def __init__(self):
        self.s = session(Accept="application/json, text/plain, */*", Referer=NSE_HOME)
        get(self.s, "https://www.nseindia.com", tries=2)
        get(self.s, NSE_HOME, tries=1)

    def fetch(self, symbol, start, end):
        url = NSE_API.format(f=start.strftime("%d-%m-%Y"), t=end.strftime("%d-%m-%Y"), sym=symbol)
        j = get(self.s, url).json()
        items = j.get("data", []) if isinstance(j, dict) else j
        return [x for x in (normalize_nse(i, symbol) for i in items) if x]


class BSE:
    def __init__(self):
        self.s = session(Accept="application/json", Referer="https://www.bseindia.com/",
                         Origin="https://www.bseindia.com")

    def fetch(self, symbol, code, start, end):
        out = []
        for p in range(1, 6):
            url = BSE_API.format(p=p, f=start.strftime("%Y%m%d"), t=end.strftime("%Y%m%d"), code=code)
            rows = get(self.s, url).json().get("Table", [])
            out += [x for x in (normalize_bse(i, symbol) for i in rows) if x]
            if len(rows) < 50:
                break
        return out


def fetch_announcements(holdings, start, end, log=print):
    """-> (list of announcements, health dict)"""
    out, health = [], {"nse": 0, "bse": 0, "failed": []}
    nse = None
    try:
        nse = NSE()
    except FetchError as e:
        log(f"  ! NSE warm-up failed ({e}); using BSE")
    bse = BSE()
    for h in holdings:
        sym, got = h["symbol"], None
        if nse:
            try:
                got = nse.fetch(sym, start, end)
                health["nse"] += 1
            except Exception as e:
                log(f"  ! NSE {sym}: {e}")
        if got is None and h.get("bse"):
            try:
                got = bse.fetch(sym, h["bse"], start, end)
                health["bse"] += 1
            except Exception as e:
                log(f"  ! BSE {sym}: {e}")
        if got is None:
            health["failed"].append(sym)
            continue
        out += got
    out.sort(key=lambda a: a["ts"], reverse=True)
    return out, health
