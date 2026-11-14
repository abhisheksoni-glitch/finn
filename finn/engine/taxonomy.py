"""Rules-first classifier into the reference taxonomy.

Exchange subjects are semi-structured, so ordered regex rules resolve ~90% of
filings at zero cost. Only filings that land in a catch-all bucket with low
confidence are batched to the fast model.
"""
import re

CATEGORIES = ["results", "M&A", "fund_raise", "management_change", "litigation",
              "insider_trading", "earnings_call", "investor_meetings", "credit_rating",
              "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
              "agm_egm", "pledging", "unclassified"]

ROUTINE = [
    r"trading window", r"reg(ulation)?\.?\s*74\s*\(5\)", r"certificate under sebi \(depositories",
    r"loss of share certificate", r"duplicate share", r"investor complaint",
    r"business responsibility", r"\bbrsr\b", r"\besg\b", r"compliance certificate",
    r"reg(ulation)?\.?\s*(7|40)\s*\(", r"closure of trading", r"esop|esos|esps|employee stock",
    r"statement of deviation", r"related party transactions? (disclosure|for the half)",
    r"newspaper publication", r"change in (the )?registrar", r"share transfer agent",
    r"secretarial compliance", r"annual secretarial", r"format of initial disclosure",
    r"large corporate", r"updates? on (the )?website",
]

# (category, subtype, subject-pattern, text-pattern) - first match wins
RULES = [
    ("results", "results", r"financial result|integrated filing.*financial|^results?$", None),
    ("results", "results", r"outcome of board meeting", r"(financial )?results?.{0,40}(quarter|half|year).{0,20}ended|approved.{0,40}results"),
    ("results", "board_meeting", r"board meeting intimation", r"result"),
    ("pledging", "pledge", r"pledge|encumbrance", None),
    ("pledging", "pledge", None, r"\bpledg|encumbrance"),
    ("insider_trading", "insider", r"insider trading|sast|takeover regulations|reg\.?\s*29|reg\.?\s*31", None),
    ("credit_rating", "rating", r"credit rating", None),
    ("credit_rating", "rating", None, r"\b(crisil|icra|care ratings|india ratings|brickwork|acuite)\b.{0,80}(rating|reaffirm|upgrad|downgrad)"),
    ("M&A", "deal", r"acquisition|amalgamation|merger|demerger|scheme of arrangement|joint venture|divest|sale of (stake|subsidiary)", None),
    ("M&A", "deal", None, r"\b(acquir|acquisition|amalgamat|merger|demerger|joint venture|divest)"),
    ("fund_raise", "buyback", r"buy\s?back", None),
    ("fund_raise", "raise", r"qualified institution|\bqip\b|preferential|rights issue|commercial paper|non.?convertible|debenture|fund rais", None),
    ("fund_raise", "raise", None, r"\b(qip|qualified institutions? placement|preferential (issue|allotment)|rights issue|raising of funds|fund raising)\b"),
    ("bonus_split", "bonus", r"bonus|sub-division|stock split|split of", None),
    ("dividend", "dividend", r"dividend|record date", None),
    ("management_change", "kmp", r"change in (directors|management)|key managerial|resignation|appointment|cessation|retirement", None),
    ("management_change", "kmp", None, r"\b(appoint|resign|cessation|superannuat|re-?designat).{0,80}(ceo|cfo|managing director|chairman|director|chief|president|kmp)"),
    ("litigation", "legal", r"litigation|dispute|penalt|show cause|insolvency|nclt|order (passed|received)|regulatory action|fine", None),
    ("litigation", "legal", None, r"\b(show cause|penalty|nclt|insolvency|tax demand|gst demand|order.{0,30}(authority|tribunal|court)|sebi order)"),
    ("earnings_call", "call", r"^(?!.*investor meet).*(con\.? call|conference call|earnings call|transcript|audio recording)", None),
    ("earnings_call", "call", r"analysts?/institutional investor meet", r"transcript|audio|recording|earnings call|conference call|con\.? call"),
    ("investor_meetings", "meet", r"analysts?.{0,5}/?.{0,10}institutional investor meet|investor meet|analyst meet", None),
    ("capex", "capex", r"capacity|expansion|commercial production|capital expenditure|capex|new plant", None),
    ("capex", "capex", None, r"\b(capex|capacity expansion|greenfield|brownfield|commissioning|commercial production)\b"),
    ("postal_ballot", "ballot", r"postal ballot|e-voting|scrutini[sz]er", None),
    ("agm_egm", "meeting", r"\bagm\b|\begm\b|annual general meeting|extra.?ordinary general|shareholders? meeting", None),
    ("press_release", "press", r"press release|media release|general updates?|updates?$|clarification|order|contract|award|launch", None),
]


def classify(a):
    """-> (category, subtype, confidence 0..1)"""
    subj = (a.get("subject") or "").lower()
    text = (a.get("text") or "").lower()
    both = f"{subj} | {text}"
    if re.search(r"change in directors|key managerial|kmp", subj):
        if re.search(r"\b(ceo|cfo|chief|managing director|\bmd\b|chairman|chairperson|"
                     r"whole.?time director|executive director|independent director|"
                     r"director|president)\b", text) and not re.search(
                     r"^(?!.*\b(ceo|cfo|managing director|chairman)\b).*(company secretary|"
                     r"compliance officer|statutory auditor|secretarial auditor|cost auditor)", text):
            return "management_change", "kmp", 0.95
        return "unclassified", "routine_appointment", 0.85
    for pat in ROUTINE:
        if re.search(pat, both):
            if re.search(r"newspaper", both) and re.search(r"result", both):
                return "results", "results_ad", 0.9
            return "unclassified", "routine", 0.9
    for cat, sub, sp, tp in RULES:
        if sp and not re.search(sp, subj):
            continue
        if tp and not re.search(tp, text if sp else both):
            continue
        if sp is None and tp is None:
            continue
        conf = 0.95 if sp else 0.75
        if cat == "press_release":
            conf = 0.6
        return cat, sub, conf
    return "unclassified", "unknown", 0.3


LLM_SYSTEM = ("You classify Indian stock-exchange corporate announcements. Use ONLY these "
              "categories: " + ", ".join(CATEGORIES) + ". Return JSON {\"items\":[{\"i\":int,"
              "\"category\":str}]}.")


def llm_reclassify(items, llm):
    """Batch the low-confidence ones through the fast model (20 per call)."""
    todo = [a for a in items if a["confidence"] < 0.65]
    if not llm.available or not todo:
        return 0
    n = 0
    for k in range(0, len(todo), 20):
        chunk = todo[k:k + 20]
        lines = "\n".join(f"{i}. [{a['symbol']}] {a['subject']} :: {a['text'][:300]}"
                          for i, a in enumerate(chunk))
        out = llm.ask(lines, tier="fast", system=LLM_SYSTEM) or {}
        for it in out.get("items", []):
            try:
                a = chunk[int(it["i"])]
            except Exception:
                continue
            if it.get("category") in CATEGORIES:
                a["category"], a["confidence"] = it["category"], 0.8
                a["classified_by"] = "llm"
                n += 1
    return n
