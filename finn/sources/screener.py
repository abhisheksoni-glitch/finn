"""screener.in company page -> structured financial tables + document links.

Screener consolidates the company's own filings (results, AR, transcripts) so
it is used here as a primary-data index, not as commentary: we only read the
reported numbers and the links to the company's own documents.
"""
import re

from bs4 import BeautifulSoup

from .. import cache
from ..http import get, session

BASE = "https://www.screener.in"
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"]


def num(s):
    s = (s or "").strip().replace(",", "").replace("%", "").replace("₹", "")
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _label(td):
    t = td.get_text(" ", strip=True)
    t = re.sub(r"\s*\+\s*$", "", t).strip()
    return re.sub(r"\s+", " ", t)


def parse_table(sec):
    tbl = sec.select_one("table.data-table") or sec.find("table")
    if tbl is None:
        return None
    head = [th.get_text(" ", strip=True) for th in tbl.select("thead th")][1:]
    rows = {}
    for tr in tbl.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        lab = _label(tds[0])
        if not lab or lab.lower().startswith("raw pdf"):
            continue
        rows[lab] = [num(td.get_text(strip=True)) for td in tds[1:]][:len(head) or None]
    return {"cols": head, "rows": rows}


def parse_docs(soup):
    docs = {"annual_reports": [], "concalls": []}
    sec = soup.find(id="documents")
    if not sec:
        return docs
    ar = sec.select_one(".annual-reports")
    if ar:
        for a in ar.select("a[href]"):
            t = a.get_text(" ", strip=True)
            m = re.search(r"(20\d\d)", t)
            docs["annual_reports"].append({"title": t, "year": int(m.group(1)) if m else None,
                                           "url": a["href"]})
    cc = sec.select_one(".concalls")
    if cc:
        for li in cc.select("li"):
            date = li.find("div")
            entry = {"date": date.get_text(" ", strip=True) if date else "", "links": {}}
            for a in li.select("a[href]"):
                k = a.get_text(" ", strip=True).lower()
                key = "transcript" if "transcript" in k else "ppt" if "ppt" in k else \
                      "recording" if k.startswith("rec") else None
                if key:
                    entry["links"][key] = a["href"]
            if entry["links"]:
                docs["concalls"].append(entry)
    return docs


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    about = soup.select_one(".company-profile .about p") or soup.select_one(".about p")
    ratios = {}
    for li in soup.select("#top-ratios li"):
        n, v = li.select_one(".name"), li.select_one(".number")
        if n and v:
            ratios[n.get_text(" ", strip=True)] = num(v.get_text(strip=True))
    tables = {}
    for s in SECTIONS:
        sec = soup.find(id=s)
        if sec:
            t = parse_table(sec)
            if t:
                tables[s] = t
    return {"name": h1.get_text(" ", strip=True) if h1 else "",
            "about": about.get_text(" ", strip=True) if about else "",
            "ratios": ratios, "tables": tables, "docs": parse_docs(soup)}


def _enough(page):
    q = page["tables"].get("quarters")
    if not q:
        return False
    rev = row(q, "sales", "revenue") or []
    return sum(1 for x in rev if x is not None) >= 4


def row(tbl, *names):
    if not tbl:
        return None
    rows = tbl["rows"]
    for n in names:
        for k, v in rows.items():
            if k.lower() == n:
                return v
    for n in names:
        for k, v in rows.items():
            if k.lower().startswith(n):
                return v
    return None


def fetch_company(symbol, ttl=6 * 3600):
    def load():
        s = session()
        for path in (f"/company/{symbol}/consolidated/", f"/company/{symbol}/"):
            try:
                html = get(s, BASE + path, tries=2).text
            except Exception:
                continue
            page = parse_page(html)
            if _enough(page):
                page["basis"] = "consolidated" if "consolidated" in path else "standalone"
                page["url"] = BASE + path
                return page
        return None
    return cache.cached("screener", symbol.upper(), load, ttl=ttl)
