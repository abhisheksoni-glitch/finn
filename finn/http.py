import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class FetchError(RuntimeError):
    pass


def session(**headers):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", **headers})
    return s


def get(s, url, tries=3, timeout=25, ok=(200,), **kw):
    last = None
    for i in range(tries):
        try:
            r = s.get(url, timeout=timeout, **kw)
            if r.status_code in ok:
                return r
            last = FetchError(f"{r.status_code} for {url}")
            if r.status_code == 404:
                break
        except requests.RequestException as e:
            last = e
        time.sleep(1.2 * (i + 1))
    raise FetchError(str(last))
