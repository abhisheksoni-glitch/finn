"""Nightly (post-close) build: fetch -> classify -> score -> enrich -> snapshot.

Output is a static JSON the web app reads, so the push side costs nothing to
serve and works offline. Each stage is isolated: a failing source degrades the
snapshot (and is reported in meta.health) instead of breaking it.
"""
import json
import time
from datetime import datetime, timedelta

from . import settings
from .engine import alerts as al
from .engine import people, research, results, taxonomy, triage
from .llm import get_llm
from .sources import announcements, prices, screener
from .sources.docs import pdf_pages


def build_snapshot(days=10, research_syms=None, log=print):
    t0 = time.time()
    pf, rules, llm = settings.load_portfolio(), settings.load_rules(), get_llm()
    hold = {h["symbol"]: h for h in pf["holdings"]}
    syms = list(hold)
    health = {"llm": llm.available}

    log("1/5 prices")
    px = {}
    try:
        px = prices.fetch_eod(syms)
    except Exception as e:
        log(f"  ! prices failed: {e}")
    health["prices"] = f"{len(px)}/{len(syms)}"

    log("2/5 announcements")
    end = datetime.now()
    start = end - timedelta(days=days)
    anns, h = announcements.fetch_announcements(pf["holdings"], start, end, log=log)
    health["announcements"] = h

    moves = {}
    for s, rows in px.items():
        for st in al.day_stats(rows):
            if st["ret"] is not None:
                moves[(s, st["d"])] = st["ret"]

    log(f"3/5 triage {len(anns)} filings")
    for a in anns:
        a["category"], a["subtype"], a["confidence"] = taxonomy.classify(a)
    health["llm_reclassified"] = taxonomy.llm_reclassify(anns, llm)
    triage.triage(anns, hold, moves)

    log("4/5 enrich")
    pages = lambda url: "\n".join(pdf_pages(url, max_pages=4))
    for a in anns:
        if a["tier"] == "routine":
            continue
        try:
            if a["category"] == "results" and a.get("subtype") not in ("board_meeting", "results_ad"):
                page = screener.fetch_company(a["symbol"], ttl=3600)
                card = results.headline(page, a["ts"])
                if not card or card.get("stale"):
                    card = results.headline_from_pdf(pdf_pages(a["url"], max_pages=8), llm) or card
                a["card"] = {"type": "results", **(card or {})}
                a["line"] = results.summary_line(card) or a["line"]
            elif a["category"] == "management_change":
                a["card"] = {"type": "people", **people.enrich(
                    a, hold[a["symbol"]]["name"], pdf_pages(a["url"], max_pages=6), llm)}
        except Exception as e:
            log(f"  ! enrich {a['symbol']} {a['category']}: {e}")
    health["one_liners_llm"] = triage.llm_lines(anns, llm, pdf_text=pages)

    portfolio = []
    for s, hd in hold.items():
        rows = px.get(s, [])
        last = rows[-1] if rows else None
        prev = rows[-2] if len(rows) > 1 else None
        portfolio.append({**hd, "last": last["c"] if last else None,
                          "chg": round((last["c"] / prev["c"] - 1) * 100, 2) if last and prev else None,
                          "series": [[r["d"], r["c"], r["v"]] for r in rows[-130:]]})

    snap = {"meta": {"as_of": end.strftime("%Y-%m-%dT%H:%M:%S+05:30"), "source": "live",
                     "window_days": days, "health": health, "rules": rules,
                     "models": llm.models, "provider": llm.provider},
            "portfolio": portfolio,
            "announcements": anns,
            "alerts": al.price_alerts(px, rules) + al.filing_alerts(anns, rules)}

    settings.WEB_DATA.mkdir(parents=True, exist_ok=True)
    research_syms = research_syms if research_syms is not None else pf.get("research_demo", [])
    log(f"5/5 research {research_syms}")
    rdir = settings.WEB_DATA / "research"
    rdir.mkdir(exist_ok=True)
    done = []
    for s in research_syms:
        try:
            r = research.build_cached(s, llm, log=log)
            (rdir / f"{s}.json").write_text(json.dumps(r, ensure_ascii=False))
            done.append(s)
        except Exception as e:
            log(f"  ! research {s}: {e}")
    snap["meta"]["research"] = done
    snap["meta"]["usage"] = llm.ledger.as_dict()
    snap["meta"]["build_seconds"] = round(time.time() - t0, 1)
    (settings.WEB_DATA / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False))
    log(f"done in {snap['meta']['build_seconds']}s, llm usage {snap['meta']['usage']}")
    return snap
