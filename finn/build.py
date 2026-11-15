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
    end = settings.now_ist()
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

    merge_events(anns)
    health["merged"] = sum(1 for a in anns if a.get("merged_into"))

    log("4/5 enrich")
    pages = lambda url: "\n".join(pdf_pages(url, max_pages=4))
    research_for = []
    for a in anns:
        if a["tier"] == "routine" or a.get("merged_into"):
            continue
        try:
            if a["category"] == "results" and a["subtype"] == "results":
                a["card"] = results_card(a, llm, log)
                a["line"] = results.summary_line(a["card"]) or a["line"]
                if a["card"].get("metrics"):
                    research_for.append(a)
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
            "alerts": al.price_alerts(px, rules) + al.filing_alerts([a for a in anns if not a.get("merged_into")], rules)}

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

    # Results vs guidance: put each fresh results card next to what management
    # guided on its last call. Reuses research already built; builds at most
    # RESULTS_RESEARCH_MAX new ones per run to keep the nightly job cheap.
    built = 0
    for a in research_for:
        s = a["symbol"]
        r = None
        f = rdir / f"{s}.json"
        try:
            if f.exists():
                r = json.loads(f.read_text())
            elif llm.available and built < settings.RESULTS_RESEARCH_MAX:
                log(f"  research for results card {s}")
                r = research.build_cached(s, llm, log=log)
                built += 1
                if r and not r.get("error"):
                    f.write_text(json.dumps(r, ensure_ascii=False))
            if r and not r.get("error"):
                a["card"]["guidance"] = results.guidance_check(a["card"], r)
                if s not in done:
                    done.append(s)
        except Exception as e:
            log(f"  ! guidance check {s}: {e}")
    snap["meta"]["research"] = done
    snap["meta"]["usage"] = llm.ledger.as_dict()
    snap["meta"]["build_seconds"] = round(time.time() - t0, 1)
    (settings.WEB_DATA / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False))
    log(f"done in {snap['meta']['build_seconds']}s, llm usage {snap['meta']['usage']}")
    return snap


def results_card(a, llm, log=print):
    """Headline numbers for a results filing, from the most reliable source that has them:
    Screener's reported table, then the results PDF (and any merged sibling filing's PDF),
    and otherwise an honest 'pending' card that says why."""
    card, latest = None, None
    try:
        page = screener.fetch_company(a["symbol"], ttl=3600)
        card = results.headline(page, a["ts"])
    except Exception as e:
        log(f"  ! screener {a['symbol']}: {e}")
    if card and card.get("stale"):
        latest, card = card.get("latest"), None
    if not card:
        urls = [a.get("url")] + [x.get("url") for x in a.get("also", [])]
        for u in [u for u in urls if u]:
            try:
                card = results.headline_from_pdf(pdf_pages(u, max_pages=12), llm)
            except Exception as e:
                log(f"  ! results pdf {a['symbol']}: {e}")
            if card:
                break
    if card:
        return {"type": "results", **card}
    why = (f"Reported tables only go up to {results.fq_label(latest)} so far" if latest
           else "The reported tables haven't been updated yet")
    why += ", and the filing PDF had no readable numbers." if llm.available else \
        ". Add a model key to read the numbers straight from the filing."
    return {"type": "results", "pending": True, "reason": why}


def merge_events(anns, hours=36):
    """One event, one card. Companies often file the same news more than once: the results
    PDF, the board-meeting outcome that approved them, a press release. Fold same-company
    filings that land within `hours` of a results filing (or of each other, when both are
    material) into the most important one, keeping each as a line under it."""
    def t(a):
        return datetime.fromisoformat(a["ts"][:19])

    live = [a for a in anns if a["tier"] in ("top", "glance")]
    by_sym = {}
    for a in live:
        by_sym.setdefault(a["symbol"], []).append(a)
    for items in by_sym.values():
        items.sort(key=lambda a: (-(a["category"] == "results" and a.get("subtype") == "results"),
                                  -a.get("score", 0)))
        for i, head in enumerate(items):
            if head.get("merged_into"):
                continue
            is_results = head["category"] == "results" and head.get("subtype") == "results"
            for o in items[i + 1:]:
                if o.get("merged_into") or abs((t(o) - t(head)).total_seconds()) > hours * 3600:
                    continue
                same_kind = o["category"] == head["category"]
                if not (is_results or (same_kind and o["tier"] == head["tier"] == "top")):
                    continue
                if o["category"] == "management_change" and not same_kind:
                    continue      # a CFO exit on results day is its own story
                o["merged_into"] = head["id"]
                head.setdefault("also", []).append(
                    {"id": o["id"], "label": o.get("label"), "category": o["category"],
                     "line": o.get("line"), "url": o.get("url"), "ts": o["ts"]})
                head["score"] = max(head.get("score", 0), o.get("score", 0))
                if o["tier"] == "top":
                    head["tier"] = "top"
    return anns
