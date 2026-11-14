"""Tiny BM25 over document chunks for grounded Q&A. Mirrored client-side so
the static build can answer extractively without any server."""
import math
import re
from collections import Counter

STOP = set("the a an of to and in for on is are was were be by with that this it as at from we our "
           "you your have has had will would can could should also which there their them they its "
           "not but or if so than then into over about what how why when who".split())


def toks(s):
    return [w for w in re.findall(r"[a-z0-9%]+", (s or "").lower()) if w not in STOP and len(w) > 1]


def chunk_pages(pages, tag, title, size=900, page_numbers=None):
    out = []
    for i, p in enumerate(pages):
        pn = page_numbers[i] if page_numbers else i + 1
        txt = re.sub(r"\s+", " ", p or "").strip()
        for k in range(0, len(txt), size):
            piece = txt[k:k + size + 120]
            if len(piece) > 120:
                out.append({"id": f"{tag}:p{pn}", "title": title, "text": piece})
    return out


def search(chunks, q, k=6):
    qs = toks(q)
    if not qs or not chunks:
        return []
    docs = [toks(c["text"]) for c in chunks]
    N = len(docs)
    avg = sum(map(len, docs)) / N
    df = Counter(w for d in docs for w in set(d))
    scored = []
    for c, d in zip(chunks, docs):
        tf = Counter(d)
        s = 0.0
        for w in qs:
            if w not in tf:
                continue
            idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


ASK_SYSTEM = ("Answer the investor's question using ONLY the excerpts from the company's own "
              "transcripts / annual report below. Cite excerpt ids inline like [T2:p7]. If the "
              "excerpts don't answer it, say exactly what is missing. <= 120 words. Return JSON "
              "{\"answer\":str,\"cites\":[str]}.")


def ask(chunks, q, llm):
    hits = search(chunks, q)
    if not hits:
        return {"answer": "Nothing in the transcripts or annual report matches that question.", "cites": [], "passages": []}
    if not llm.available:
        return {"answer": None, "cites": [h["id"] for h in hits], "passages": hits}
    ctx = "\n\n".join(f"[{h['id']}] {h['text']}" for h in hits)
    out = llm.ask(f"Question: {q}\n\nExcerpts:\n{ctx}", tier="fast", system=ASK_SYSTEM) or {}
    out["passages"] = hits
    return out
