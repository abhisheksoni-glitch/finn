"""Quarterly results first cut: Revenue, EBITDA, PBT, PAT - QoQ and YoY.

Primary path is deterministic: Screener's quarterly table (parsed from the
company's own results filing) - no model call. If that table has not caught up
with the filing yet, the results PDF itself goes to the fast model with a
strict schema, and the output is sanity-checked before it is shown.
"""
import re
from datetime import datetime

from ..sources import screener as scr

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def fq_label(col):
    """'Sep 2025' -> 'Q2 FY26' (Indian fiscal year ends March)."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", col or "")
    if not m:
        return col
    mon, yr = MONTHS.get(m.group(1).lower()), int(m.group(2))
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(mon)
    if not q:
        return col
    fy = yr + 1 if mon >= 4 else yr
    return f"Q{q} FY{str(fy)[2:]}"


def quarter_end(col):
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", col or "")
    if not m:
        return None
    mon, yr = MONTHS.get(m.group(1).lower()), int(m.group(2))
    day = {3: 31, 6: 30, 9: 30, 12: 31}.get(mon, 28)
    return datetime(yr, mon, day)


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


def metric_rows(q):
    is_fin = scr.row(q, "financing profit") is not None
    rev = scr.row(q, "sales", "revenue")
    ebitda = None if is_fin else scr.row(q, "operating profit")
    pbt = scr.row(q, "profit before tax")
    pat = scr.row(q, "net profit")
    return is_fin, {"Revenue": rev, "EBITDA": ebitda, "PBT": pbt, "PAT": pat}, \
        scr.row(q, "financing profit") if is_fin else None


def headline(page, filing_ts=None):
    q = page["tables"].get("quarters") if page else None
    if not q or len(q["cols"]) < 5:
        return None
    cols = q["cols"]
    is_fin, rows, fin_profit = metric_rows(q)
    i = len(cols) - 1
    while i >= 0 and (rows["Revenue"] is None or rows["Revenue"][i] is None):
        i -= 1
    if i < 4:
        return None
    if filing_ts:
        fdt = datetime.fromisoformat(filing_ts[:19])
        qe = quarter_end(cols[i])
        if qe and (fdt - qe).days > 80:
            return {"stale": True, "latest": cols[i]}
    out = {"quarter": fq_label(cols[i]), "vs_qoq": fq_label(cols[i - 1]),
           "vs_yoy": fq_label(cols[i - 4]), "basis": page.get("basis", "consolidated"),
           "unit": "₹ cr", "metrics": [], "source": "screener", "is_financial": is_fin}
    for k, r in rows.items():
        if r is None:
            if k == "EBITDA" and is_fin and fin_profit:
                r, k = fin_profit, "Pre-provision profit"
            else:
                out["metrics"].append({"k": k, "v": None, "note": "n/a for lenders" if is_fin else "n/a"})
                continue
        v, qq, yy = r[i], r[i - 1], r[i - 4]
        out["metrics"].append({"k": k, "v": v, "qoq": pct(v, qq), "yoy": pct(v, yy),
                               "prev": qq, "yago": yy})
    rev = rows["Revenue"]
    eb = rows["EBITDA"]
    if rev and eb and rev[i] and eb[i] is not None and rev[i - 4]:
        m_now, m_ya = eb[i] / rev[i] * 100, eb[i - 4] / rev[i - 4] * 100
        out["margin"] = {"now": round(m_now, 1), "yago": round(m_ya, 1),
                         "bps": round((m_now - m_ya) * 100)}
    out["series"] = {"cols": [fq_label(c) for c in cols[max(0, i - 7):i + 1]],
                     "Revenue": rev[max(0, i - 7):i + 1] if rev else [],
                     "PAT": rows["PAT"][max(0, i - 7):i + 1] if rows["PAT"] else []}
    return out


RESULTS_SYSTEM = (
    "Extract headline numbers from an Indian listed company's quarterly results filing. "
    "Prefer CONSOLIDATED figures if both are present. Return JSON: {\"basis\":"
    "\"consolidated|standalone\",\"unit\":\"crore|lakh|million\",\"quarter_label\":str,"
    "\"columns\":[\"this quarter\",\"previous quarter\",\"same quarter last year\"],"
    "\"revenue\":[3 numbers],\"ebitda\":[3 numbers or null],\"pbt\":[3],\"pat\":[3]}. "
    "Revenue = revenue from operations. EBITDA = PBT + finance costs + depreciation - other "
    "income if not stated. Use only numbers printed in the document; null if absent.")


def headline_from_pdf(pages, llm):
    if not llm.available or not pages:
        return None
    text = "\n".join(pages[:8])[:24000]
    j = llm.ask(text, tier="fast", system=RESULTS_SYSTEM)
    if not j or not j.get("revenue"):
        return None
    mult = {"crore": 1, "lakh": 0.01, "million": 0.1}.get(str(j.get("unit", "crore")).lower(), 1)
    out = {"quarter": j.get("quarter_label", "Latest quarter"), "vs_qoq": "prev qtr",
           "vs_yoy": "year ago", "basis": j.get("basis", "?"), "unit": "₹ cr",
           "metrics": [], "source": "filing_pdf"}
    for k, key in (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("PBT", "pbt"), ("PAT", "pat")):
        r = j.get(key) or [None, None, None]
        r = [x * mult if isinstance(x, (int, float)) else None for x in (r + [None] * 3)[:3]]
        out["metrics"].append({"k": k, "v": r[0], "qoq": pct(r[0], r[1]), "yoy": pct(r[0], r[2]),
                               "prev": r[1], "yago": r[2]})
    m = {x["k"]: x["v"] for x in out["metrics"]}
    if m.get("PAT") and m.get("Revenue") and abs(m["PAT"]) > abs(m["Revenue"]):
        return None
    return out


def summary_line(card):
    if not card or not card.get("metrics"):
        return None
    m = {x["k"]: x for x in card["metrics"]}
    bits = []
    for k in ("Revenue", "PAT"):
        x = m.get(k)
        if x and x.get("yoy") is not None:
            bits.append(f"{k.lower() if k == 'Revenue' else k} {x['yoy']:+.0f}% YoY")
    mg = card.get("margin")
    if mg:
        bits.append(f"EBITDA margin {mg['now']}% ({mg['bps']:+d} bps)")
    return f"{card.get('quarter', 'Results')}: " + ", ".join(bits) if bits else None
