import json
from pathlib import Path

from finn import build, settings
from finn.sources import announcements, screener

F = Path(__file__).parent / "fixtures"


def test_build_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WEB_DATA", tmp_path)
    monkeypatch.setattr(settings, "CACHE_DIR", tmp_path / "cache")
    import finn.cache
    monkeypatch.setattr(finn.cache, "CACHE_DIR", tmp_path / "cache")
    raw = [announcements.normalize_nse(x) for x in json.loads((F / "nse_announcements.json").read_text())]
    page = screener.parse_page((F / "screener_polycab.html").read_text())
    page.update(basis="consolidated", url="https://www.screener.in/company/POLYCAB/consolidated/")
    rows = [{"d": f"2026-10-{i:02d}", "c": 100.0 + i, "v": 1000} for i in range(1, 29)]
    monkeypatch.setattr(build.prices, "fetch_eod", lambda syms: {s: rows for s in syms})
    monkeypatch.setattr(build.announcements, "fetch_announcements",
                        lambda h, a, b, log=print: ([dict(x) for x in raw], {"nse": 1}))
    monkeypatch.setattr(build.screener, "fetch_company", lambda s, ttl=None: page)
    monkeypatch.setattr(build.research.scr, "fetch_company", lambda s, ttl=None: page)
    monkeypatch.setattr(build, "pdf_pages", lambda url, max_pages=None: [])
    monkeypatch.setattr(build.research, "pdf_pages", lambda url, max_pages=None: [])
    snap = build.build_snapshot(days=10, research_syms=["POLYCAB"], log=lambda *a: None)
    assert (tmp_path / "snapshot.json").exists() and (tmp_path / "research" / "POLYCAB.json").exists()
    res = [a for a in snap["announcements"] if a["category"] == "results"][0]
    assert res["card"]["type"] == "results"
    r = json.loads((tmp_path / "research" / "POLYCAB.json").read_text())
    assert r["numbers"]["quarters"] and r["analysis"]["bull"]
