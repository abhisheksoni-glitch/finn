import hashlib
import json
import time

from .settings import CACHE_DIR


def _path(ns, key):
    h = hashlib.sha256(key.encode()).hexdigest()[:24]
    d = CACHE_DIR / ns
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def get(ns, key, ttl=None):
    p = _path(ns, key)
    if not p.exists():
        return None
    if ttl is not None and time.time() - p.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def put(ns, key, value):
    _path(ns, key).write_text(json.dumps(value, ensure_ascii=False))
    return value


def cached(ns, key, fn, ttl=None):
    v = get(ns, key, ttl)
    if v is not None:
        return v
    v = fn()
    if v is not None:
        put(ns, key, v)
    return v
