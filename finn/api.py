"""Live API for the pull side (any ticker) + serves the web app.

GET  /api/research/{symbol}   build-or-cache research for any NSE symbol
POST /api/ask                 {symbol, q} grounded Q&A over that company's docs
POST /api/rebuild             refresh the push snapshot
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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


@app.get("/api/research/{symbol}")
def get_research(symbol: str, fresh: bool = False):
    llm = get_llm()
    sym = symbol.upper().strip()
    r = research.build(sym, llm) if fresh else research.build_cached(sym, llm)
    if r.get("error"):
        raise HTTPException(404, r["error"])
    return r


class Ask(BaseModel):
    symbol: str
    q: str


@app.post("/api/ask")
def post_ask(body: Ask):
    llm = get_llm()
    r = research.build_cached(body.symbol.upper(), llm)
    return retrieval.ask(r.get("chunks", []), body.q, llm)


@app.post("/api/rebuild")
def rebuild(days: int = 10):
    s = build_snapshot(days=days, research_syms=[])
    return {"ok": True, "announcements": len(s["announcements"]), "meta": s["meta"]}


web = Path(settings.ROOT / "web")
if web.exists():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
