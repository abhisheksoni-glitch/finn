"""Real push: send today's triggered alerts to Telegram after the nightly
build. One HTTP call, free, and lands where investors already are."""
import json

import requests

from . import settings


def format_alerts(snap, max_items=8):
    alerts = snap.get("alerts", [])
    if not alerts:
        return None
    lines = [f"FINN — {len(alerts)} alert(s) for {snap['meta']['as_of'][:10]}"]
    for a in alerts[:max_items]:
        icon = "▲" if (a.get("ret") or 0) > 0 else "▼" if a["kind"] == "price" else "●"
        lines.append(f"{icon} {a['symbol']}: {a['text']}")
    if len(alerts) > max_items:
        lines.append(f"+{len(alerts) - max_items} more in the app")
    return "\n".join(lines)


def send(snap=None):
    if snap is None:
        snap = json.loads((settings.WEB_DATA / "snapshot.json").read_text())
    msg = format_alerts(snap)
    if not msg:
        print("no alerts to send")
        return False
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID):
        print(msg)
        print("(set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to deliver this)")
        return False
    r = requests.post(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": msg}, timeout=20)
    print("sent" if r.ok else f"telegram error {r.status_code}: {r.text[:200]}")
    return r.ok
