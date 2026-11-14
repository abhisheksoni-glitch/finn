"""Threshold alerts on EOD data and material filings.

The same logic is mirrored in the web client so the investor can drag a
threshold and see, instantly, how many times it would have fired in the last
60 sessions - tuning the noise level before committing to it.
"""


def day_stats(rows, lookback=20):
    out = []
    for i, r in enumerate(rows):
        prev = rows[i - 1]["c"] if i else None
        win = [x["v"] for x in rows[max(0, i - lookback):i] if x["v"]]
        avg = sum(win) / len(win) if len(win) >= max(5, lookback // 2) else None
        out.append({"d": r["d"], "c": r["c"], "v": r["v"],
                    "ret": round((r["c"] / prev - 1) * 100, 2) if prev else None,
                    "vmult": round(r["v"] / avg, 2) if avg else None})
    return out


def price_alerts(prices, rules, last_n=1):
    alerts = []
    for sym, rows in prices.items():
        st = day_stats(rows, rules.get("volume_lookback_days", 20))
        for s in st[-last_n:]:
            hits = []
            if s["ret"] is not None and abs(s["ret"]) >= rules["price_move_pct"]:
                hits.append(f"{s['ret']:+.1f}% on the day")
            if s["vmult"] is not None and s["vmult"] >= rules["volume_multiple"]:
                hits.append(f"volume {s['vmult']:.1f}× its {rules.get('volume_lookback_days', 20)}-day average")
            if hits:
                alerts.append({"kind": "price", "symbol": sym, "d": s["d"], "ret": s["ret"],
                               "vmult": s["vmult"], "close": s["c"], "text": " and ".join(hits)})
    return alerts


def filing_alerts(anns, rules):
    cats = set(rules.get("alert_categories", []))
    m = rules.get("min_priority_for_alert", 70)
    return [{"kind": "filing", "symbol": a["symbol"], "d": a["ts"][:10], "id": a["id"],
             "text": f"{a['label']}: {a['line']}"} for a in anns
            if a["category"] in cats and a["score"] >= m]
