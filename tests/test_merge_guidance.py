from finn import build
from finn.engine import results


def _a(i, cat, sub, ts, tier="top", score=80, sym="KAYNES"):
    return {"id": i, "symbol": sym, "category": cat, "subtype": sub, "ts": ts, "tier": tier,
            "score": score, "label": cat, "line": f"line {i}", "url": f"https://x/{i}.pdf"}


def test_results_and_board_outcome_become_one_card():
    anns = [_a("r", "results", "results", "2026-11-14T23:42:00+05:30", score=88),
            _a("m", "M&A", "deal", "2026-11-15T00:15:00+05:30", score=90),
            _a("o", "M&A", "deal", "2026-11-15T00:20:00+05:30", sym="DIXON")]
    build.merge_events(anns)
    head = anns[0]
    assert anns[1]["merged_into"] == "r" and "merged_into" not in anns[2]
    assert head["also"][0]["id"] == "m" and head["score"] == 90


def test_cfo_exit_on_results_day_stays_separate():
    anns = [_a("r", "results", "results", "2026-11-14T18:00:00+05:30"),
            _a("c", "management_change", "kmp", "2026-11-14T19:00:00+05:30")]
    build.merge_events(anns)
    assert "merged_into" not in anns[1]


def test_target_range():
    assert results._target_range("15-20%") == (15, 20)
    assert results._target_range("11–13%") == (11, 13)
    assert results._target_range("> 18%") == (18, None)
    assert results._target_range("> 1.5× industry") is None


def test_guidance_check():
    card = {"metrics": [{"k": "Revenue", "v": 120, "yoy": 29.3}, {"k": "EBITDA", "v": 12}],
            "margin": {"now": 10.0}}
    research = {"sources": {"T4": {"title": "Q1 FY27 earnings call transcript"}},
                "analysis": {"guidance_now": [
                    {"metric": "Revenue growth", "target": "15-20%", "horizon": "FY27", "src": ["T4:p3"]},
                    {"metric": "EBITDA margin", "target": "11–13%", "horizon": "FY27", "src": ["T4:p5"]},
                    {"metric": "Capex", "target": "₹500 cr", "src": ["T4:p6"]}]}}
    g = results.guidance_check(card, research)
    assert [x["verdict"] for x in g] == ["ahead", "behind"]
    assert g[0]["said_in"] == "Q1 FY27 call"


def test_quarter_names_from_pdf_labels():
    assert results._quarter_names("September 30, 2026") == ("Q2 FY27", "Q1 FY27", "Q2 FY26")
    assert results._quarter_names("Quarter ended 31.12.2026") == ("Q3 FY27", "Q2 FY27", "Q3 FY26")
    assert results._quarter_names("Q1 FY27") == ("Q1 FY27", "Q4 FY26", "Q1 FY26")
    assert results._quarter_names("30 June 2026")[0] == "Q1 FY27"


def test_now_ist_is_india_time():
    from datetime import datetime, timezone, timedelta
    from finn import settings
    d = settings.now_ist() - datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(d - timedelta(hours=5, minutes=30)) < timedelta(seconds=5)
