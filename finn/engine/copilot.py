"""Ask FINN: a conversational layer over the investor's own book.

The phone sends a compact, already-filtered view of what it is showing (holdings,
the ranked filings in the window, price moves, alerts). For any company the question
names, the server adds that company's research (numbers, promise ledger, guidance,
bull/bear) and the transcript or annual-report passages that best match the question,
so the model can answer "what did TCS guide on margins?" from primary documents.
One fast-model call per question. Answers must cite what they rest on; the app turns
citations back into the cards and passages they came from.
"""
import json
import re

from . import retrieval

SYSTEM = (
    "You are FINN, a sharp, terse analyst working for a portfolio manager. Answer ONLY from "
    "the context below: their holdings, exchange filings, end-of-day prices and alerts, and, "
    "for companies they name, research built from the company's own earnings-call "
    "transcripts and annual report (with the matching passages). Never use outside knowledge "
    "about any company and never give buy/sell advice or price targets.\n"
    "Style: lead with the answer in the first sentence; at most 120 words; plain prose, no "
    "headings or bullet symbols; name stocks by symbol; quote numbers exactly as given; when "
    "comparing companies, compare the same metric side by side. Never mention 'DATA', "
    "'context' or how you were prompted.\n"
    "If the investor asks about a company that has no research in the context, say in one "
    "sentence that you haven't researched it yet and list its symbol in needs_research.\n"
    "Citations: filings as F:<id>, prices as P:<SYMBOL>, research as R:<SYMBOL>, and document "
    "passages by their passage id (e.g. R:TCS:T2:p7). Cite every item you rely on.\n"
    "follow_ups: up to 3 short, specific next questions that build on THIS answer and that "
    "the same context can answer (name the stock and the metric); never generic.\n"
    "Return JSON {\"answer\": str, \"cites\": [str], \"follow_ups\": [str], "
    "\"needs_research\": [str]}."
)

MAX_CONTEXT = 48000


def research_brief(r, q, k=4):
    """Compact research for one company, plus the passages that best match the question."""
    an = r.get("analysis") or {}
    sym = r.get("symbol")
    nums = (r.get("numbers") or {})
    tr = nums.get("trajectory") or {}
    out = {
        "symbol": sym, "name": r.get("name"), "about": (r.get("about") or "")[:300],
        "snapshot": nums.get("snapshot"),
        "trajectory": {k2: tr.get(k2) for k2 in ("years", "revenue", "pat", "opm", "rev_cagr_3y",
                                                 "pat_cagr_3y", "opm_change_3y_bps") if tr.get(k2) is not None},
        "verdict": an.get("verdict"),
        "guidance_now": (an.get("guidance_now") or [])[:5],
        "guidance_drift": an.get("guidance_drift"),
        "promises": [{k2: x.get(k2) for k2 in ("said_in", "promise", "target", "delivered", "verdict")}
                     for x in (an.get("ledger") or [])[:8]],
        "bull": [x.get("point") for x in an.get("bull") or []],
        "bear": [x.get("point") for x in an.get("bear") or []],
    }
    hits = retrieval.search(r.get("chunks") or [], q, k=k)
    out["passages"] = [{"id": f"R:{sym}:{h['id']}", "source": h.get("title"), "text": h["text"][:900]}
                       for h in hits]
    return out


def chat(context, q, history, llm, research_docs=None):
    q = (q or "").strip()[:500]
    if not q:
        return {"answer": "Ask me about your book.", "cites": [], "follow_ups": [], "needs_research": []}
    if not llm.available:
        return None
    context = dict(context or {})
    briefs = [research_brief(r, q) for r in (research_docs or [])]
    if briefs:
        have = {b["symbol"] for b in briefs}
        context["research"] = briefs + [x for x in context.get("research", []) if x.get("symbol") not in have]
    ctx = json.dumps(context, ensure_ascii=False, separators=(",", ":"))[:MAX_CONTEXT]
    turns = "\n".join(f"{t.get('role', 'user')}: {str(t.get('text', ''))[:400]}"
                      for t in (history or [])[-6:])
    prompt = f"CONTEXT:\n{ctx}\n\n" + (f"CONVERSATION SO FAR:\n{turns}\n\n" if turns else "") + f"QUESTION: {q}"
    out = llm.ask(prompt, tier="fast", system=SYSTEM) or {}
    ans = str(out.get("answer") or "").strip()
    if not ans:
        return None
    valid = set(_ids(context))
    cites = [c for c in out.get("cites") or [] if isinstance(c, str) and c in valid]
    for m in re.findall(r"\b([FPR]:[A-Za-z0-9:&_.\-]+)", ans):
        m = m.rstrip(".")
        if m in valid and m not in cites:
            cites.append(m)
    ans = re.sub(r"\s*[\[(]?\b[FPR]:[A-Za-z0-9:&_.\-]+[\])]?", "", ans).strip()
    ans = re.sub(r"\s+([.,;])", r"\1", ans)
    ans = re.sub(r"\b(the )?DATA\b", "what I have", ans)
    fu = [str(x)[:90] for x in (out.get("follow_ups") or []) if isinstance(x, str)][:3]
    researched = {b.get("symbol") for b in context.get("research", [])}
    need = [s.upper() for s in (out.get("needs_research") or [])
            if isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9&\-]{2,15}", s) and s.upper() not in researched][:2]
    passages = {p["id"]: p for b in briefs for p in b.get("passages", [])}
    used = [passages[c] for c in cites if c in passages]
    return {"answer": ans, "cites": cites[:8], "follow_ups": fu, "needs_research": need, "passages": used}


def _ids(context):
    c = context or {}
    for f in c.get("filings", []):
        yield f"F:{f.get('id')}"
    for h in c.get("holdings", []):
        yield f"P:{h.get('symbol')}"
    for r in c.get("research", []):
        yield f"R:{r.get('symbol')}"
        for p in r.get("passages", []) or []:
            yield p["id"]
