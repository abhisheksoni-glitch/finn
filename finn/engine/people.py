"""Management-change cards: who is coming/going, and who they are.

1. The filing itself: SEBI LODR Reg 30 requires a 'brief profile' annexure for
   appointments, so the first-party bio is usually inside the PDF already.
2. Web enrichment (allowed on the push side): search '<name> <company>
   LinkedIn' through Tavily/Serper if a key is set, and compress the snippets
   into a two-line career summary with source links.
3. Always: a one-tap LinkedIn people-search link.
"""
import re
from urllib.parse import quote_plus

import requests

from .. import settings

EXTRACT_SYSTEM = (
    "From this Indian company's management-change filing, return JSON {\"changes\":[{"
    "\"person\":str,\"role\":str,\"change\":\"appointed|resigned|retired|redesignated\","
    "\"effective\":str|null,\"replaces\":str|null,\"reason\":str|null,"
    "\"profile\":str|null (<=45 words, ONLY from the filing's brief-profile text),"
    "\"prior_roles\":[str] (from the filing only)}]}. Ignore company secretary/auditor "
    "changes unless they are the only change.")

BIO_SYSTEM = (
    "Summarise this person's professional background for an investor in <=40 words: "
    "current/most recent roles, notable prior employers, education if clear. Use only the "
    "snippets given; if snippets are about different people, say 'unclear match'. Return "
    "JSON {\"bio\":str,\"prior\":[str],\"confidence\":\"high|medium|low\"}.")


def linkedin_search_url(name, company):
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(f"{name} {company}")


def _search(q):
    try:
        if settings.TAVILY_API_KEY:
            r = requests.post("https://api.tavily.com/search", timeout=20, json={
                "api_key": settings.TAVILY_API_KEY, "query": q, "max_results": 5})
            return [{"title": x.get("title"), "url": x.get("url"), "snippet": x.get("content", "")[:400]}
                    for x in r.json().get("results", [])]
        if settings.SERPER_API_KEY:
            r = requests.post("https://google.serper.dev/search", timeout=20,
                              headers={"X-API-KEY": settings.SERPER_API_KEY}, json={"q": q, "num": 5})
            return [{"title": x.get("title"), "url": x.get("link"), "snippet": x.get("snippet", "")}
                    for x in r.json().get("organic", [])]
    except Exception as e:
        print(f"  ! search failed: {e}")
    return []


def _regex_fallback(text):
    m = re.search(r"(?:appointment of|appointed|resignation of|resigned)\s+(?:mr\.?|ms\.?|mrs\.?|dr\.?)?\s*"
                  r"([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+){1,3})", text or "")
    role = re.search(r"\b(chief executive officer|chief financial officer|managing director|"
                     r"whole[- ]time director|chairman|ceo|cfo|independent director)\b", text or "", re.I)
    if not m:
        return []
    ch = "resigned" if re.search(r"resign|cessation", text or "", re.I) else "appointed"
    return [{"person": m.group(1).strip(), "role": role.group(1).title() if role else "Director",
             "change": ch, "profile": None, "prior_roles": []}]


def enrich(a, company, pages, llm):
    text = "\n".join(pages)[:16000] if pages else a["text"]
    changes = None
    if llm.available:
        j = llm.ask(f"Company: {company}\n\n{text}", tier="fast", system=EXTRACT_SYSTEM)
        changes = (j or {}).get("changes")
    if not changes:
        changes = _regex_fallback(f"{a['text']} {text[:3000]}")
    for c in changes:
        name = c.get("person") or ""
        c["linkedin_search"] = linkedin_search_url(name, company)
        c["web"] = None
        if name and c.get("change") == "appointed":
            hits = _search(f"{name} {company} LinkedIn")
            if hits and llm.available:
                snip = "\n".join(f"- {h['title']}: {h['snippet']} ({h['url']})" for h in hits)
                b = llm.ask(f"Person: {name}, joining {company} as {c.get('role')}\n{snip}",
                            tier="fast", system=BIO_SYSTEM)
                if b:
                    b["sources"] = [h["url"] for h in hits[:3]]
                    c["web"] = b
    return {"changes": changes[:3]}
