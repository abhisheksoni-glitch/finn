"""Two-tier model router.

fast  -> bulk extraction/classification/one-liners (cheap, high volume)
smart -> the few reasoning-heavy calls (promise vs delivery, bull/bear, Q&A)

Every call is content-hash cached on disk, rate-limited for free tiers, and
metered so each snapshot reports exactly what it cost. If no key is configured
the router reports unavailable and every caller falls back to a rules path.
"""
import json
import re
import threading
import time

import requests

from . import cache, settings


class Ledger:
    def __init__(self):
        self.calls = {"fast": 0, "smart": 0}
        self.cached = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def as_dict(self):
        return {"calls": self.calls, "cache_hits": self.cached,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


class LLM:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.models = {"fast": settings.MODEL_FAST, "smart": settings.MODEL_SMART}
        self.ledger = Ledger()
        self._lock = threading.Lock()
        self._last = 0.0

    @property
    def available(self):
        if self.provider == "gemini":
            return bool(settings.GEMINI_API_KEY)
        return bool(settings.OPENAI_COMPAT_KEY)

    def _throttle(self):
        with self._lock:
            wait = settings.LLM_MIN_INTERVAL - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    def _gemini(self, model, system, prompt, as_json):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.15}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if as_json:
            body["generationConfig"]["responseMimeType"] = "application/json"
        r = requests.post(url, json=body, timeout=120,
                          headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        if r.status_code in (429, 500, 503):
            raise _RateLimited()
        r.raise_for_status()
        j = r.json()
        u = j.get("usageMetadata", {})
        self.ledger.tokens_in += u.get("promptTokenCount", 0)
        self.ledger.tokens_out += u.get("candidatesTokenCount", 0)
        parts = j["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)

    def _openai(self, model, system, prompt, as_json):
        msgs = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
        body = {"model": model, "messages": msgs, "temperature": 0.15}
        if as_json:
            body["response_format"] = {"type": "json_object"}
        r = requests.post(settings.OPENAI_COMPAT_BASE.rstrip("/") + "/chat/completions",
                          json=body, timeout=120,
                          headers={"Authorization": f"Bearer {settings.OPENAI_COMPAT_KEY}"})
        if r.status_code in (429, 500, 503):
            raise _RateLimited()
        r.raise_for_status()
        j = r.json()
        u = j.get("usage", {})
        self.ledger.tokens_in += u.get("prompt_tokens", 0)
        self.ledger.tokens_out += u.get("completion_tokens", 0)
        return j["choices"][0]["message"]["content"]

    def ask(self, prompt, tier="fast", system=None, as_json=True):
        if not self.available:
            return None
        model = self.models[tier]
        key = json.dumps([self.provider, model, system, prompt, as_json])
        hit = cache.get("llm", key)
        if hit is not None:
            self.ledger.cached += 1
            return hit["v"]
        call = self._gemini if self.provider == "gemini" else self._openai
        out = None
        for attempt in range(4):
            self._throttle()
            try:
                out = call(model, system, prompt, as_json)
                break
            except _RateLimited:
                time.sleep(8 * (attempt + 1))
            except Exception as e:
                print(f"  ! llm {tier} failed: {e}")
                return None
        if out is None:
            return None
        self.ledger.calls[tier] += 1
        v = parse_json(out) if as_json else out.strip()
        if v is not None:
            cache.put("llm", key, {"v": v})
        return v


class _RateLimited(Exception):
    pass


def parse_json(s):
    if s is None:
        return None
    s = s.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", s, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
    return None


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
