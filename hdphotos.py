"""Original, full-resolution catalog photos.

The local images/ folder only has 60x80 px thumbnails, but every product has a full-size photo
(1800x2400) on Myntra's image server. image_urls.csv maps product id -> URL (from the public
Hugging Face copy of the dataset). A photo is downloaded only when it is about to be shown,
shrunk to a screen-friendly size and kept in hd_cache/, so each one is fetched once.
"""
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(HERE, "image_urls.csv")
CACHE_DIR = os.path.join(HERE, "hd_cache")
MAX_SIDE = 720                  # longest side kept on disk (shown at ~165-420 px wide)
_urls = None


def _url_for(product_id):
    global _urls
    if _urls is None:
        _urls = {}
        if os.path.exists(URL_FILE):
            m = pd.read_csv(URL_FILE)
            _urls = dict(zip(m["id"].astype(int), m["url"]))
    return _urls.get(int(product_id))


def product_id(path):
    m = re.search(r"(\d+)\.\w+$", os.path.basename(str(path)))
    return int(m.group(1)) if m else None


def cache_path(pid):
    return os.path.join(CACHE_DIR, f"orig_{pid}.jpg")


def original_photo(path):
    """JPEG bytes of the full-resolution photo for a catalog thumbnail path, or None if it cannot
    be fetched (no URL, offline, removed from the server). Cached on disk."""
    pid = product_id(path)
    if pid is None:
        return None
    cached = cache_path(pid)
    if os.path.exists(cached):
        with open(cached, "rb") as f:
            return f.read()
    url = _url_for(pid)
    if not url:
        return None
    for _ in range(2):
        try:
            r = requests.get(url.replace("http://", "https://"), timeout=15)
            if r.status_code != 200 or not r.content:
                continue
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            if min(img.size) < 200:                 # a placeholder, not a real photo
                return None
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=92, optimize=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = cached + ".part"
            with open(tmp, "wb") as f:
                f.write(buf.getvalue())
            os.replace(tmp, cached)
            return buf.getvalue()
        except Exception:
            continue
    return None


def prefetch(paths, workers=8):
    """Download the originals for several photos at once (so a row of 5-10 appears quickly)."""
    todo = [p for p in dict.fromkeys(paths)
            if product_id(p) is not None and not os.path.exists(cache_path(product_id(p)))]
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(original_photo, todo))
