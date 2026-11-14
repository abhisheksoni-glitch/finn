"""python -m finn <command>

  doctor            check every data source and the model key
  build [--days N]  nightly snapshot -> web/data/snapshot.json (+ demo research)
  research SYMBOL   build research for any NSE symbol -> web/data/research/SYMBOL.json
  notify            send today's alerts to Telegram
  serve [--port P]  live API + web app on http://localhost:P
  sample            regenerate the bundled sample snapshot (no network)
"""
import argparse
import json
import sys
from datetime import datetime, timedelta


def doctor():
    from . import settings
    from .llm import get_llm
    from .sources import announcements, prices, screener
    ok = lambda b: "✓" if b else "✗"
    pf = settings.load_portfolio()
    h = pf["holdings"][:2]
    try:
        px = prices.fetch_eod([x["symbol"] for x in h], period="1mo")
        print(f"{ok(px)} Yahoo prices      {', '.join(f'{k}:{len(v)}d' for k, v in px.items()) or 'none'}")
    except Exception as e:
        print(f"✗ Yahoo prices      {e}")
    end = datetime.now()
    try:
        a = announcements.NSE().fetch(h[0]["symbol"], end - timedelta(days=30), end)
        print(f"✓ NSE filings       {len(a)} for {h[0]['symbol']} in 30d")
    except Exception as e:
        print(f"✗ NSE filings       {e}  (BSE fallback will be used)")
    try:
        a = announcements.BSE().fetch(h[0]["symbol"], h[0]["bse"], end - timedelta(days=30), end)
        print(f"✓ BSE filings       {len(a)} for {h[0]['symbol']} in 30d")
    except Exception as e:
        print(f"✗ BSE filings       {e}")
    try:
        p = screener.fetch_company("POLYCAB", ttl=0)
        print(f"{ok(p)} Screener          {p and len(p['tables'])} tables, "
              f"{p and len(p['docs']['concalls'])} concalls, {p and len(p['docs']['annual_reports'])} ARs")
    except Exception as e:
        print(f"✗ Screener          {e}")
    llm = get_llm()
    if llm.available:
        r = llm.ask('Return {"ok": true}', tier="fast")
        print(f"{ok(r)} LLM ({llm.provider}) fast={llm.models['fast']} smart={llm.models['smart']}")
    else:
        print("✗ LLM               no key set - numbers-only mode (set GEMINI_API_KEY in .env)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    b = sub.add_parser("build")
    b.add_argument("--days", type=int, default=10)
    b.add_argument("--no-research", action="store_true")
    r = sub.add_parser("research")
    r.add_argument("symbol")
    r.add_argument("--fresh", action="store_true")
    sub.add_parser("notify")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    sub.add_parser("sample")
    a = p.parse_args(argv)
    if a.cmd == "doctor":
        doctor()
    elif a.cmd == "build":
        from .build import build_snapshot
        build_snapshot(days=a.days, research_syms=[] if a.no_research else None)
    elif a.cmd == "research":
        from . import settings
        from .engine import research
        from .llm import get_llm
        llm = get_llm()
        out = (research.build if a.fresh else research.build_cached)(a.symbol, llm)
        d = settings.WEB_DATA / "research"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.symbol.upper()}.json").write_text(json.dumps(out, ensure_ascii=False))
        print(json.dumps(out.get("analysis"), indent=2, ensure_ascii=False)[:3000])
        print("usage", llm.ledger.as_dict())
    elif a.cmd == "notify":
        from .notify import send
        send()
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("finn.api:app", host="0.0.0.0", port=a.port)
    elif a.cmd == "sample":
        from .sample import write_sample
        write_sample()
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
