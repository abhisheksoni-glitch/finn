"""Materiality scoring -> tiers, plus zero-cost one-liners.

score = category base + content modifiers (+ position-size and price-reaction
nudges). Tiers: top >= 70 (card), glance 35-69 (one line), routine < 35
(collapsed). The UI lets the investor mute (stock x category) which demotes to
routine; that is the learning loop.
"""
import re

from .taxonomy import classify

BASE = {"results": 88, "M&A": 84, "management_change": 78, "fund_raise": 72,
        "litigation": 66, "credit_rating": 58, "pledging": 66, "insider_trading": 52,
        "capex": 60, "bonus_split": 50, "dividend": 40, "press_release": 42,
        "earnings_call": 24, "investor_meetings": 14, "agm_egm": 18, "postal_ballot": 16,
        "unclassified": 6}

LABEL = {"results": "Results", "M&A": "M&A", "management_change": "Management",
         "fund_raise": "Fund raise", "litigation": "Legal & regulatory",
         "credit_rating": "Credit rating", "pledging": "Promoter pledge",
         "insider_trading": "Insider deal", "capex": "Capex", "bonus_split": "Bonus / split",
         "dividend": "Dividend", "press_release": "Press release", "earnings_call": "Earnings call",
         "investor_meetings": "Investor meetings", "agm_egm": "AGM / EGM",
         "postal_ballot": "Postal ballot", "unclassified": "Compliance paperwork"}

BOILER = [
    r"^.*?\bhas (informed|submitted to) the exchange,?\s*(about|regarding|that)?\s*",
    r"^.*?\bhas (informed|intimated) (the )?exchanges?\s*(about|regarding|that)?\s*",
    r"^pursuant to regulation \d+[^,]*,\s*",
    r"^(please find|we (wish to )?inform)[^,.]*?(that|enclosed|attached)\s*",
]

MONEY = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\b|lakh|million|mn|billion|bn)", re.I)


def money_cr(text):
    best = None
    for m in MONEY.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        u = m.group(2).lower()
        cr = v if u.startswith("cr") else v / 100 if u == "lakh" else \
            v / 10 if u in ("million", "mn") else v * 100
        best = max(best or 0, cr)
    return best


def clean_line(text, subject):
    t = re.sub(r"\s+", " ", text or "").strip()
    for p in BOILER:
        t = re.sub(p, "", t, flags=re.I)
    t = t.strip(" .:-")
    if len(t) < 12:
        t = subject
    t = t[0].upper() + t[1:] if t else subject
    return (t[:180].rsplit(" ", 1)[0] + "…") if len(t) > 180 else t


def score(a, holding=None, day_move=None):
    cat, sub = a["category"], a.get("subtype")
    s = BASE.get(cat, 10)
    t = f"{a['subject']} {a['text']}".lower()
    why = []
    if cat == "results":
        if sub == "board_meeting":
            s, why = 30, ["date set for results"]
        elif sub == "results_ad":
            s = 8
    elif cat == "management_change":
        if re.search(r"\b(ceo|managing director|\bmd\b|chief executive|chairman)\b", t):
            s += 12; why.append("top job")
        elif re.search(r"\b(cfo|chief financial)\b", t):
            s += 10; why.append("CFO seat")
        elif re.search(r"independent director|non-executive", t):
            s -= 45
        if re.search(r"resign|cessation|step(s|ped)? down", t):
            s += 6; why.append("exit")
    elif cat == "credit_rating":
        if re.search(r"downgrad|negative|watch with negative", t):
            s += 28; why.append("downgrade")
        elif re.search(r"upgrad|positive", t):
            s += 10; why.append("upgrade")
        elif re.search(r"reaffirm|retain", t):
            s -= 30
    elif cat == "pledging":
        if re.search(r"invoc", t):
            s += 22; why.append("pledge invoked")
        elif re.search(r"release|revoc", t):
            s -= 40
    elif cat == "litigation":
        if re.search(r"insolvency|nclt|cirp", t):
            s += 16
        amt = money_cr(t)
        if amt and amt >= 100:
            s += 10; why.append(f"₹{amt:,.0f} cr at stake")
    elif cat == "press_release":
        amt = money_cr(t)
        if re.search(r"\border|contract|award|letter of (intent|award)", t):
            s += 10; why.append("order win")
        if amt and amt >= 500:
            s += 16
        if re.search(r"clarif", t):
            s += 8; why.append("clarification")
    elif cat == "dividend" and re.search(r"special|interim", t):
        s += 6
    elif cat == "fund_raise" and re.search(r"commercial paper|ncd|debenture", t):
        s -= 30
    elif cat == "insider_trading" and re.search(r"promoter", t):
        s += 8; why.append("promoter")
    if holding and holding.get("weight", 0) >= 7:
        s += 3
    if day_move is not None and abs(day_move) >= 4 and cat != "unclassified":
        s += 10; why.append(f"stock {day_move:+.1f}% on the news")
    s = max(0, min(100, s))
    return s, why


def tier(s):
    return "top" if s >= 70 else "glance" if s >= 35 else "routine"


def reaction(moves, sym, ts):
    """Price move of the first session that could react to the filing:
    same day if filed before the 15:30 close, else the next session."""
    from datetime import datetime, timedelta
    d = datetime.fromisoformat(ts[:19])
    if d.hour * 60 + d.minute >= 15 * 60 + 30:
        d += timedelta(days=1)
    for k in range(4):
        m = moves.get((sym, (d + timedelta(days=k)).strftime("%Y-%m-%d")))
        if m is not None:
            return m
    return None


def triage(anns, holdings_by_sym, moves=None):
    moves = moves or {}
    for a in anns:
        if "category" not in a:
            a["category"], a["subtype"], a["confidence"] = classify(a)
    for a in anns:
        h = holdings_by_sym.get(a["symbol"])
        dm = reaction(moves, a["symbol"], a["ts"])
        a["reaction"] = dm
        a["score"], a["why"] = score(a, h, dm)
        a["tier"] = tier(a["score"])
        a["label"] = LABEL.get(a["category"], a["category"])
        a["line"] = clean_line(a["text"], a["subject"])
    anns.sort(key=lambda a: (-{"top": 2, "glance": 1, "routine": 0}[a["tier"]], -a["score"], a["ts"]))
    return anns


SUMMARY_SYSTEM = ("You write one-line summaries of Indian corporate filings for a busy fund "
                  "manager. <= 22 words, lead with the fact that matters (numbers, names, "
                  "counterparties), no fluff, no advice. Return JSON {\"items\":[{\"i\":int,"
                  "\"line\":str}]}.")


def llm_lines(anns, llm, pdf_text=None):
    """Upgrade one-liners for glance/top items that are not handled by a
    bespoke card (results, management change). Uses the filing PDF when the
    exchange text is too thin."""
    todo = [a for a in anns if a["tier"] != "routine"
            and a["category"] not in ("results", "management_change")]
    if not llm.available or not todo:
        return 0
    n = 0
    for k in range(0, len(todo), 12):
        chunk = todo[k:k + 12]
        blocks = []
        for i, a in enumerate(chunk):
            body = a["text"]
            if pdf_text and len(body) < 160:
                body = (pdf_text(a["url"]) or body)[:1800]
            blocks.append(f"### {i} [{a['symbol']}] {a['subject']}\n{body[:1800]}")
        out = llm.ask("\n\n".join(blocks), tier="fast", system=SUMMARY_SYSTEM) or {}
        for it in out.get("items", []):
            try:
                chunk[int(it["i"])]["line"] = it["line"].strip()
                n += 1
            except Exception:
                pass
    return n
