"""PDF fetch + text extraction (filings, transcripts, annual reports).
Immutable documents are cached forever, keyed by URL."""
import io
from urllib.parse import urlparse

from .. import cache
from ..http import get, session


def _referer(url):
    host = urlparse(url).netloc
    if "bseindia" in host:
        return "https://www.bseindia.com/"
    if "nseindia" in host:
        return "https://www.nseindia.com/"
    return f"https://{host}/"


def pdf_pages(url, max_pages=None):
    if not url:
        return []

    def load():
        from pypdf import PdfReader
        s = session(Referer=_referer(url))
        r = get(s, url, timeout=60)
        if b"%PDF" not in r.content[:1024]:
            return [r.text[:20000]] if "html" in r.headers.get("content-type", "") else []
        reader = PdfReader(io.BytesIO(r.content))
        pages = []
        for i, p in enumerate(reader.pages):
            if max_pages and i >= max_pages:
                break
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        return pages

    key = f"{url}|{max_pages}"
    try:
        hit = cache.get("pdf", key)
        if hit is not None:
            return hit
        pages = load() or []
        # Only cache documents that actually yielded text. An empty read (file not
        # yet uploaded, HTML error page, scanned PDF) is retried on the next build
        # instead of being frozen in the cache forever.
        if sum(len(p or "") for p in pages) >= 200:
            cache.put("pdf", key, pages)
        return pages
    except Exception as e:
        print(f"  ! pdf {url[:80]}: {e}")
        return []
