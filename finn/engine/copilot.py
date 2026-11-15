"""Ask FINN: a conversational layer over the investor's own book.

The phone sends a compact, already-filtered view of what it is showing (holdings,
the ranked filings in the window, price moves, alerts, and any research it has open),
so the model sees exactly what the investor sees and nothing else. One fast-model
call per question; answers must cite the items they rest on, and the app turns those
citations back into the cards they came from.
"""
import json
import re

SYSTEM = (
    "You are FINN, a terse analyst for a portfolio manager. Answer ONLY from the DATA "
    "provided (their holdings, exchange filings, end-of-day prices, alerts, and research "
    "built from the company's own transcripts and annual report). Never use outside "
    "knowledge about any company, never give buy/sell advice or price targets. "
    "Lead with the answer in the first sentence. Use at most 110 words, plain prose, no "
    "headings or bullet symbols. Name stocks by symbol. Quote numbers exactly as given. "
    "If the DATA does not contain the answer, say what is missing in one sentence. "
    "Cite every item you rely on, using its id exactly: filings as F:<id>, price data as "
    "P:<SYMBOL>, research as R:<SYMBOL>. Return JSON {\"answer\": str, \"cites\": [str], "
    "\"follow_ups\": [up to 3 short questions the investor might ask next, answerable "
    "from the same DATA]}."
)

MAX_CONTEXT = 40000


def chat(context, q, history, llm):
    q = (q or "").strip()[:500]
    if not q:
        return {"answer": "Ask me about your book.", "cites": [], "follow_ups": []}
    if not llm.available:
        return None
    ctx = json.dumps(context or {}, ensure_ascii=False, separators=(",", ":"))[:MAX_CONTEXT]
    turns = "\n".join(f"{t.get('role', 'user')}: {str(t.get('text', ''))[:400]}"
                      for t in (history or [])[-6:])
    prompt = f"DATA:\n{ctx}\n\n" + (f"CONVERSATION SO FAR:\n{turns}\n\n" if turns else "") + f"QUESTION: {q}"
    out = llm.ask(prompt, tier="fast", system=SYSTEM) or {}
    ans = str(out.get("answer") or "").strip()
    if not ans:
        return None
    valid = set(_ids(context))
    cites = [c for c in out.get("cites") or [] if isinstance(c, str) and c in valid]
    # Pick up inline citations the model wrote into the prose, then strip them from it.
    for m in re.findall(r"\b([FPR]:[A-Za-z0-9:&_.\-]+)", ans):
        if m in valid and m not in cites:
            cites.append(m)
    ans = re.sub(r"\s*[\[(]?\b[FPR]:[A-Za-z0-9:&_.\-]+[\])]?", "", ans).strip()
    ans = re.sub(r"\s+([.,;])", r"\1", ans)
    fu = [str(x)[:90] for x in (out.get("follow_ups") or []) if isinstance(x, str)][:3]
    return {"answer": ans, "cites": cites[:6], "follow_ups": fu}


def _ids(context):
    c = context or {}
    for f in c.get("filings", []):
        yield f"F:{f.get('id')}"
    for h in c.get("holdings", []):
        yield f"P:{h.get('symbol')}"
    for r in c.get("research", []):
        yield f"R:{r.get('symbol')}"
