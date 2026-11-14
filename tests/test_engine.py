import json
from pathlib import Path

from finn.engine import alerts, research, results, retrieval, taxonomy, triage
from finn.sources import announcements, screener

F = Path(__file__).parent / "fixtures"


def nse():
    return [announcements.normalize_nse(x) for x in json.loads((F / "nse_announcements.json").read_text())]


def page():
    p = screener.parse_page((F / "screener_polycab.html").read_text())
    p["basis"], p["url"] = "consolidated", "https://www.screener.in/company/POLYCAB/consolidated/"
    return p


def test_nse_normalize():
    a = nse()
    assert a[0]["ts"] == "2026-11-14T18:12:05+05:30"
    assert a[0]["id"] == "nse:104771001" and a[0]["url"].endswith(".pdf")


def test_bse_normalize():
    rows = json.loads((F / "bse_announcements.json").read_text())["Table"]
    a = announcements.normalize_bse(rows[0], "POLYCAB")
    assert a["subject"] == "Credit Rating" and "downgraded" in a["text"]
    assert a["url"].endswith("a1b2c3d4.pdf")


def test_classify_and_tiers():
    a = triage.triage(nse(), {"POLYCAB": {"weight": 5}})
    by = {x["id"]: x for x in a}
    assert by["nse:104771001"]["category"] == "results" and by["nse:104771001"]["tier"] == "top"
    assert by["nse:104770002"]["category"] == "management_change" and by["nse:104770002"]["tier"] == "top"
    assert by["nse:104770003"]["tier"] == "routine"
    assert by["nse:104770004"]["category"] == "investor_meetings" and by["nse:104770004"]["tier"] == "routine"
    assert by["nse:104770005"]["category"] == "unclassified"
    assert by["nse:104770006"]["category"] == "credit_rating" and by["nse:104770006"]["tier"] == "routine"
    assert by["nse:104770002"]["line"].startswith("Resignation of Mr. Gandharv")


def test_downgrade_escalates():
    rows = json.loads((F / "bse_announcements.json").read_text())["Table"]
    a = triage.triage([announcements.normalize_bse(rows[0], "POLYCAB")], {})
    assert a[0]["category"] == "credit_rating" and a[0]["tier"] == "top"


def test_screener_parse():
    p = page()
    assert p["name"] == "Polycab India Ltd"
    assert p["ratios"]["Market Cap"] == 108000
    assert p["tables"]["quarters"]["cols"][-1] == "Sep 2025"
    assert screener.row(p["tables"]["quarters"], "sales")[-1] == 6478
    assert len(p["docs"]["concalls"]) == 4 and p["docs"]["concalls"][0]["links"]["transcript"].endswith("t4.pdf")
    assert p["docs"]["annual_reports"][0]["year"] == 2025


def test_results_headline():
    h = results.headline(page(), "2025-10-17T18:00:00+05:30")
    assert h["quarter"] == "Q2 FY26" and h["vs_qoq"] == "Q1 FY26" and h["vs_yoy"] == "Q2 FY25"
    m = {x["k"]: x for x in h["metrics"]}
    assert m["Revenue"]["v"] == 6478 and m["Revenue"]["yoy"] == 17.8
    assert m["PAT"]["qoq"] == 15.5
    assert h["margin"]["bps"] > 0


def test_results_stale_detection():
    h = results.headline(page(), "2026-02-10T18:00:00+05:30")
    assert h["stale"]


def test_fq_label_and_calls():
    assert results.fq_label("Mar 2025") == "Q4 FY25"
    assert results.fq_label("Dec 2025") == "Q3 FY26"
    assert research.call_quarter("Oct 2025") == "Q2 FY26"
    assert research.call_quarter("Jan 2026") == "Q3 FY26"
    assert research.call_quarter("May 2025") == "Q4 FY25"


def test_research_numbers():
    n = research.numbers(page())
    assert n["trajectory"]["rev_cagr_3y"] > 15
    assert n["cash"]["conversion_5y"] is not None
    assert n["balance"]["de"][-1] < 0.1
    assert n["quarters"][-1]["q"] == "Q2 FY26" and n["quarters"][-1]["rev_yoy"] == 17.8
    v = research.heuristic_view(n, [])
    assert v["bull"]


def test_price_alerts():
    rows = [{"d": f"2026-10-{i:02d}", "c": 100 + i * 0.1, "v": 1000} for i in range(1, 25)]
    rows.append({"d": "2026-10-25", "c": 110, "v": 3500})
    al = alerts.price_alerts({"X": rows}, {"price_move_pct": 4, "volume_multiple": 2})
    assert al and "volume 3.5" in al[0]["text"] and "+" in al[0]["text"]


def test_retrieval():
    ch = retrieval.chunk_pages(["We guide for 20-25% revenue growth in FY26 with EBITDA margin of 11-13%."
                                " " * 10 + "Capex will be Rs 1,200 crore over two years. " * 3], "T1", "call")
    hits = retrieval.search(ch, "what is margin guidance")
    assert hits and hits[0]["id"] == "T1:p1"


def test_money():
    assert triage.money_cr("order worth Rs. 1,250 crore") == 1250
    assert triage.money_cr("INR 500 million") == 50
