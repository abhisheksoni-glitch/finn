"""Live API for the pull side (any ticker) + serves the web app.

GET  /api/research/{symbol}   build-or-cache research for any NSE symbol
POST /api/ask                 {symbol, q} grounded Q&A over that company's docs
POST /api/rebuild             refresh the push snapshot
"""
import json
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import settings
from .build import build_snapshot
from .engine import research, retrieval
from .llm import get_llm

app = FastAPI(title="FINN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    llm = get_llm()
    return {"ok": True, "llm": llm.available, "models": llm.models, "usage": llm.ledger.as_dict()}


# Research takes a few minutes (four transcripts, an annual report, two model tiers).
# Holding one HTTP request open that long gets cut by proxies and phones, so the
# build runs in a background thread and the app polls: 202 while building, 200 when done.
JOBS = {}
LOCK = threading.Lock()


def _run(sym):
    job = JOBS[sym]
    try:
        r = research.build_cached(sym, get_llm(), log=lambda m: job.update(step=str(m).strip()))
        if r.get("error"):
            job.update(state="error", detail=r["error"])
        else:
            job.update(state="done")
    except Exception as e:
        job.update(state="error", detail=f"Research failed: {e}")


@app.get("/api/research/{symbol}")
def get_research(symbol: str, fresh: bool = False):
    llm = get_llm()
    sym = symbol.upper().strip().replace(".NS", "")
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
        raise HTTPException(400, "That doesn't look like an NSE symbol.")
    if not fresh:
        r = research.cached_only(sym, llm)
        if r and not r.get("error"):
            return r
    with LOCK:
        job = JOBS.get(sym)
        if job and job["state"] == "error" and time.time() - job["t0"] > 60:
            job = None                                   # let a failed symbol be retried
        if not job or (fresh and job["state"] != "building"):
            job = JOBS[sym] = {"state": "building", "step": "starting", "t0": time.time()}
            threading.Thread(target=_run, args=(sym,), daemon=True).start()
    if job["state"] == "error":
        raise HTTPException(404, job.get("detail") or "Research failed.")
    if job["state"] == "done":
        r = research.cached_only(sym, llm)
        if r:
            return r
        JOBS.pop(sym, None)                              # cache went missing: rebuild on next poll
    return JSONResponse({"status": "building", "step": job.get("step"),
                         "seconds": round(time.time() - job["t0"])}, status_code=202)


class Ask(BaseModel):
    symbol: str
    q: str


@app.post("/api/ask")
def post_ask(body: Ask):
    llm = get_llm()
    sym = body.symbol.upper()
    r = research.cached_only(sym, llm)
    f = settings.WEB_DATA / "research" / f"{sym}.json"
    if not r and f.exists():                             # prebuilt by the nightly job
        r = json.loads(f.read_text())
    return retrieval.ask((r or {}).get("chunks", []), body.q, llm)


@app.post("/api/rebuild")
def rebuild(days: int = 10):
    s = build_snapshot(days=days, research_syms=[])
    return {"ok": True, "announcements": len(s["announcements"]), "meta": s["meta"]}


web = Path(settings.ROOT / "web")
if web.exists():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
