import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
WEB_DATA = ROOT / "web" / "data"


def _load_env():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

CACHE_DIR = Path(os.getenv("FINN_CACHE", ROOT / ".cache"))
LLM_PROVIDER = os.getenv("FINN_LLM_PROVIDER", "gemini")
MODEL_FAST = os.getenv("FINN_MODEL_FAST", "gemini-3.5-flash-lite")
MODEL_SMART = os.getenv("FINN_MODEL_SMART", "gemini-3.6-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_COMPAT_BASE = os.getenv("FINN_OPENAI_BASE", "https://api.groq.com/openai/v1")
OPENAI_COMPAT_KEY = os.getenv("FINN_OPENAI_KEY", "")
LLM_MIN_INTERVAL = float(os.getenv("FINN_LLM_MIN_INTERVAL", "4.2"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# New research builds allowed per nightly run, for results-vs-guidance on results cards
RESULTS_RESEARCH_MAX = int(os.getenv("FINN_RESULTS_RESEARCH_MAX", "2"))


def load_portfolio():
    return json.loads((CONFIG / "portfolio.json").read_text())


def load_rules():
    return json.loads((CONFIG / "rules.json").read_text())


IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Wall-clock time in India, whatever the server's timezone (GitHub runners are UTC)."""
    return datetime.now(IST).replace(tzinfo=None)
