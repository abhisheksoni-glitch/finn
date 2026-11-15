"""Pull-side research, grounded only in primary documents.

Pipeline (per ticker, works for any NSE symbol Screener covers):
  numbers   deterministic, from the company's reported financials (no model)
  map       fast model, one call per transcript / AR excerpt, cached forever
            -> guidance statements, claims, analyst pushback, with page refs
  reduce    one smart-model call over the compact extracts + numbers
            -> promise-vs-delivered ledger, narrative vs numbers, bull/bear
Every claim carries a source id that resolves to a document + page.
If no model key is set, the numbers and an extractive guidance list are still
produced, so the view never breaks.
"""
import re
from datetime import datetime

from .. import cache, settings
from ..sources import screener as scr
from ..sources.docs import pdf_pages
from .results import fq_label, pct, MONTHS
from .retrieval import chunk_pages


def _last(vals, n=1):
    vals = [v for v in (vals or []) if v is not None]
    return vals[-n:] if n > 1 else (vals[-1] if vals else None)


def cagr(a, b, years):
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def _annual(tbl):
    if not tbl:
        return [], {}
    cols = tbl["cols"]
    keep = [i for i, c in enumerate(cols) if re.match(r"(Mar|Dec|Jun|Sep) \d{4}", c)]
    return [cols[i] for i in keep], {k: [v[i] if i < len(v) else None for i in keep]
                                     for k, v in tbl["rows"].items()}


def numbers(page):
    t = page["tables"]
    pl_cols, pl = _annual(t.get("profit-loss"))
    bs_cols, bs = _annual(t.get("balance-sheet"))
    cf_cols, cf = _annual(t.get("cash-flow"))
    rt_cols, rt = _annual(t.get("ratios"))
    g = lambda d, *names: scr.row({"rows": d}, *names)

    rev, pat = g(pl, "sales", "revenue"), g(pl, "net profit")
    op = g(pl, "operating profit", "financing profit")
    opm = g(pl, "opm", "financing margin")
    other = g(pl, "other income")
    n = len(pl_cols)

    def growth(series, yrs):
        if not series or len(series) <= yrs:
            return None
        return cagr(series[-1 - yrs], series[-1], yrs)

    traj = {"years": [c[-4:] for c in pl_cols], "revenue": rev, "pat": pat, "opm": opm,
            "rev_cagr_3y": growth(rev, 3), "rev_cagr_5y": growth(rev, 5),
            "pat_cagr_3y": growth(pat, 3), "pat_cagr_5y": growth(pat, 5)}
    if opm and len([x for x in opm if x is not None]) >= 4:
        o = [x for x in opm if x is not None]
        traj["opm_change_3y_bps"] = round((o[-1] - o[-4]) * 100)
    if other and pat and pat[-1]:
        traj["other_income_share_of_pat"] = round((other[-1] or 0) / pat[-1] * 100, 1)

    eq = [(a or 0) + (b or 0) for a, b in zip(g(bs, "equity capital") or [], g(bs, "reserves") or [])]
    debt = g(bs, "borrowings") or []
    de = [round(d / e, 2) if e and d is not None else None for d, e in zip(debt, eq)]
    bal = {"years": [c[-4:] for c in bs_cols], "borrowings": debt, "equity": eq, "de": de,
           "cwip": g(bs, "cwip"), "investments": g(bs, "investments"),
           "debtor_days": g(rt, "debtor days"), "inventory_days": g(rt, "inventory days"),
           "payable_days": g(rt, "days payable"), "ccc": g(rt, "cash conversion cycle"),
           "wc_days": g(rt, "working capital days"), "roce": g(rt, "roce"),
           "ratio_years": [c[-4:] for c in rt_cols]}

    cfo = g(cf, "cash from operating activity", "cash from operations")
    cfi = g(cf, "cash from investing activity")
    fcf = g(cf, "free cash flow")
    fcf_kind = "reported"
    if not fcf and cfo and cfi:
        fcf = [(a + b) if a is not None and b is not None else None for a, b in zip(cfo, cfi)]
        fcf_kind = "CFO + CFI (proxy)"
    pat_by_year = dict(zip([c[-4:] for c in pl_cols], pat or []))
    cy = [c[-4:] for c in cf_cols]
    conv = [round(c / pat_by_year[y], 2) if c is not None and pat_by_year.get(y) else None
            for c, y in zip(cfo or [], cy)]
    k5 = [(c, pat_by_year.get(y)) for c, y in zip(cfo or [], cy)][-5:]
    cum = None
    if k5 and all(c is not None and p for c, p in k5):
        cum = round(sum(c for c, _ in k5) / sum(p for _, p in k5), 2)
    cash = {"years": cy, "cfo": cfo, "fcf": fcf, "fcf_kind": fcf_kind, "conversion": conv,
            "conversion_5y": cum}

    q = t.get("quarters") or {"cols": [], "rows": {}}
    qrev = scr.row(q, "sales", "revenue") or []
    qop = scr.row(q, "operating profit", "financing profit") or []
    qpat = scr.row(q, "net profit") or []
    quarters = []
    for i, c in enumerate(q["cols"]):
        r = qrev[i] if i < len(qrev) else None
        if r is None:
            continue
        quarters.append({"q": fq_label(c), "rev": r,
                         "rev_yoy": pct(r, qrev[i - 4]) if i >= 4 else None,
                         "opm": round(qop[i] / r * 100, 1) if i < len(qop) and qop[i] is not None and r else None,
                         "pat": qpat[i] if i < len(qpat) else None,
                         "pat_yoy": pct(qpat[i], qpat[i - 4]) if i >= 4 and i < len(qpat) else None})

    ttm = None
    plt = t.get("profit-loss")
    if plt and plt["cols"] and plt["cols"][-1].upper() == "TTM":
        ttm = {k: (v[-1] if v else None) for k, v in plt["rows"].items()}
    tget = lambda *names: scr.row({"rows": {k: [v] for k, v in ttm.items()}}, *names)[0] if ttm and scr.row({"rows": {k: [v] for k, v in ttm.items()}}, *names) else None
    snap = {"market_cap": page["ratios"].get("Market Cap"), "price": page["ratios"].get("Current Price"),
            "pe": page["ratios"].get("Stock P/E"), "roce": page["ratios"].get("ROCE"),
            "roe": page["ratios"].get("ROE"), "div_yield": page["ratios"].get("Dividend Yield"),
            "rev_ttm": tget("sales", "revenue") or _last(rev), "pat_ttm": tget("net profit") or _last(pat),
            "opm_ttm": tget("opm", "financing margin") or _last(opm), "ttm": ttm is not None,
            "de": _last(de)}
    return {"snapshot": snap, "trajectory": traj, "balance": bal, "cash": cash,
            "quarters": quarters[-8:]}


def call_quarter(date_str):
    """Concall month -> the quarter it discusses ('Nov 2025' -> 'Q2 FY26')."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", date_str or "")
    if not m:
        return date_str
    mon, yr = MONTHS.get(m.group(1).lower(), 1), int(m.group(2))
    qe_m = {1: 12, 2: 12, 3: 12, 4: 3, 5: 3, 6: 3, 7: 6, 8: 6, 9: 6, 10: 9, 11: 9, 12: 9}[mon]
    qe_y = yr - 1 if mon <= 3 and qe_m == 12 else yr
    return fq_label(f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][qe_m-1]} {qe_y}")


MAP_SYSTEM = (
    "You read ONE earnings-call transcript of an Indian listed company. Extract only what "
    "management actually said. Return JSON {\"guidance\":[{\"metric\":\"revenue_growth|"
    "volume_growth|ebitda_margin|pat|capex|market_share|other\",\"statement\":str (<=25 words),"
    "\"target\":str|null (e.g. '20-25%', '13-14%', 'Rs 1,500 cr'),\"horizon\":str (e.g. 'FY26',"
    "'next 2 quarters','medium term'),\"quote\":str (verbatim, <=30 words),\"page\":int}],"
    "\"claims\":[{\"claim\":str (<=20 words, a causal/narrative claim, e.g. margin up due to "
    "mix),\"page\":int}],\"pushback\":[{\"topic\":str,\"page\":int}] (what analysts pressed on),"
    "\"tone\":\"confident|cautious|defensive|mixed\"}. Page numbers refer to the [p N] markers. "
    "No outside knowledge.")

REDUCE_SYSTEM = (
    "You are a buy-side analyst. You are given (a) a company's reported numbers and (b) "
    "structured extracts of its last four earnings calls and annual report. Use ONLY this "
    "material - no outside knowledge, no news, no broker views. Every item must cite source "
    "ids from the material (e.g. 'T2:p7', 'QR', 'PL', 'CF', 'BS', 'AR:p34'). Be terse, "
    "concrete, numerical. Return JSON {"
    "\"verdict\":str (<=25 words: the one thing an investor should know),"
    "\"ledger\":[{\"said_in\":str (call quarter),\"promise\":str,\"target\":str|null,"
    "\"horizon\":str,\"delivered\":str (the actual number(s) from QR/PL),\"verdict\":"
    "\"delivered|partly|missed|too_early|walked_back\",\"src\":[str]}] (4-8 rows, the headline "
    "guidance on growth/margins/capex; track how the SAME guidance evolved call to call),"
    "\"guidance_drift\":str (<=30 words: raised/cut/quietly dropped over the 4 calls?),"
    "\"narrative\":[{\"claim\":str,\"numbers\":str,\"agree\":true|false,\"src\":[str]}] (3-5),"
    "\"guidance_now\":[{\"metric\":str,\"target\":str,\"horizon\":str,\"src\":[str]}],"
    "\"business\":{\"what\":str (<=30 words),\"segments\":[{\"name\":str,\"share\":str|null}],"
    "\"src\":[str]},"
    "\"bull\":[{\"point\":str,\"src\":[str]}] (3),\"bear\":[{\"point\":str,\"src\":[str]}] (3),"
    "\"watch\":[str] (2-3 things to check next quarter)}")


GUIDE_RX = re.compile(r"[^.]*\b(guid|we expect|we aim|target|aspire|outlook|going forward|"
                      r"margin (band|range)|grow (at|by)|capex of|we will be)\b[^.]*\.", re.I)


def _extractive_guidance(pages, tag):
    out = []
    for i, p in enumerate(pages):
        for m in GUIDE_RX.finditer(p or ""):
            s = re.sub(r"\s+", " ", m.group(0)).strip()
            if 40 < len(s) < 260 and re.search(r"\d", s):
                out.append({"statement": s, "src": f"{tag}:p{i+1}"})
    return out[:6]


def _marked(pages, limit=60000):
    s = "\n".join(f"[p {i+1}]\n{p}" for i, p in enumerate(pages))
    return s[:limit]


def _ar_pages(url):
    pages = pdf_pages(url, max_pages=140)
    kw = re.compile(r"segment|business overview|management discussion|revenue from operations|"
                    r"product portfolio|our business", re.I)
    scored = sorted(((len(kw.findall(p or "")), i) for i, p in enumerate(pages)), reverse=True)
    pick = sorted(i for s, i in scored[:6] if s > 0)
    return pages, pick


def build(symbol, llm, n_calls=4, with_ar=True, log=print):
    symbol = symbol.upper().replace(".NS", "")
    page = scr.fetch_company(symbol)
    if not page:
        return {"symbol": symbol, "error": "Screener has no financials for this symbol."}
    nums = numbers(page)
    docs = page["docs"]
    calls = [c for c in docs["concalls"] if c["links"].get("transcript")][:n_calls]
    sources = {"PL": {"title": "Annual P&L (reported)", "url": page["url"] + "#profit-loss"},
               "QR": {"title": "Quarterly results (reported)", "url": page["url"] + "#quarters"},
               "BS": {"title": "Balance sheet (reported)", "url": page["url"] + "#balance-sheet"},
               "CF": {"title": "Cash flow (reported)", "url": page["url"] + "#cash-flows"}}
    extracts, chunks, extractive = [], [], []
    for k, c in enumerate(reversed(calls), 1):
        tag = f"T{k}"
        qlabel = call_quarter(c["date"])
        url = c["links"]["transcript"]
        sources[tag] = {"title": f"{qlabel} earnings call transcript", "url": url, "date": c["date"]}
        log(f"    transcript {tag} {qlabel}")
        pages = pdf_pages(url)
        if not pages:
            continue
        chunks += chunk_pages(pages, tag, sources[tag]["title"])
        extractive += _extractive_guidance(pages, tag)
        if llm.available:
            ex = llm.ask(_marked(pages), tier="fast", system=MAP_SYSTEM)
            if ex:
                extracts.append({"src": tag, "quarter": qlabel, **ex})
    ar = None
    if with_ar and docs["annual_reports"]:
        ar = docs["annual_reports"][0]
        sources["AR"] = {"title": ar["title"], "url": ar["url"]}
        log(f"    annual report {ar['title']}")
        try:
            pages, pick = _ar_pages(ar["url"])
            chunks += chunk_pages([pages[i] for i in pick], "AR", ar["title"], page_numbers=[i + 1 for i in pick])
            ar_text = "\n".join(f"[AR p {i+1}]\n{pages[i][:3500]}" for i in pick)
        except Exception as e:
            log(f"  ! AR failed: {e}")
            ar_text = ""
    else:
        ar_text = ""

    analysis = None
    if llm.available and (extracts or ar_text):
        import json
        material = {"company": page["name"], "about": page["about"], "basis": page.get("basis"),
                    "numbers": {"QR_quarters": nums["quarters"],
                                "PL_annual": {k: nums["trajectory"][k] for k in
                                              ("years", "revenue", "pat", "opm", "rev_cagr_3y", "pat_cagr_3y")},
                                "BS": {k: nums["balance"][k] for k in ("years", "borrowings", "de")},
                                "CF": {k: nums["cash"][k] for k in ("years", "cfo", "conversion", "conversion_5y")}},
                    "calls": extracts}
        prompt = json.dumps(material, ensure_ascii=False) + ("\n\nANNUAL REPORT EXCERPTS:\n" + ar_text[:18000] if ar_text else "")
        analysis = llm.ask(prompt, tier="smart", system=REDUCE_SYSTEM)

    if not analysis:
        analysis = heuristic_view(nums, extractive)

    return {"symbol": symbol, "name": page["name"], "about": page["about"],
            "basis": page.get("basis"), "as_of": settings.now_ist().strftime("%Y-%m-%d"),
            "numbers": nums, "analysis": analysis, "extracts": extracts,
            "sources": sources, "chunks": chunks[:220],
            "mode": "llm" if llm.available else "numbers_only"}


def heuristic_view(n, extractive):
    """No-model fallback: rule-based bull/bear from the numbers + raw guidance
    sentences. Honest about being mechanical."""
    tr, ca, ba = n["trajectory"], n["cash"], n["balance"]
    bull, bear = [], []
    if (tr.get("rev_cagr_3y") or 0) >= 15:
        bull.append({"point": f"Revenue compounding {tr['rev_cagr_3y']}% a year over 3 years", "src": ["PL"]})
    elif tr.get("rev_cagr_3y") is not None and tr["rev_cagr_3y"] < 8:
        bear.append({"point": f"Revenue growth only {tr['rev_cagr_3y']}% a year over 3 years", "src": ["PL"]})
    if (tr.get("opm_change_3y_bps") or 0) >= 150:
        bull.append({"point": f"Operating margin up {tr['opm_change_3y_bps']} bps in 3 years", "src": ["PL"]})
    elif (tr.get("opm_change_3y_bps") or 0) <= -150:
        bear.append({"point": f"Operating margin down {-tr['opm_change_3y_bps']} bps in 3 years", "src": ["PL"]})
    c5 = ca.get("conversion_5y")
    if c5 is not None:
        (bull if c5 >= 0.9 else bear).append(
            {"point": f"5-year operating cash / profit = {c5:.2f}×", "src": ["CF", "PL"]})
    de = _last(ba.get("de"))
    if de is not None:
        (bull if de < 0.3 else bear if de > 1 else bull).append(
            {"point": f"Debt/equity {de:.2f}", "src": ["BS"]})
    return {"verdict": "Numbers-only view (no model key configured): reported financials and raw guidance sentences.",
            "ledger": [], "narrative": [], "bull": bull[:3], "bear": bear[:3],
            "guidance_raw": extractive, "watch": []}


def _key(symbol, llm):
    return f"{symbol.upper()}|{llm.models['smart']}|{llm.available}"


def cached_only(symbol, llm, ttl=24 * 3600):
    return cache.get("research", _key(symbol, llm), ttl)


def build_cached(symbol, llm, ttl=24 * 3600, **kw):
    return cache.cached("research", _key(symbol, llm), lambda: build(symbol, llm, **kw), ttl=ttl)
