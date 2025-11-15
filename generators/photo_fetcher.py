# generators/photo_fetcher.py

import requests
import json
import difflib
from pathlib import Path
from datetime import datetime
from threading import Lock

from core.config import Config
from core.logger import get_logger

log = get_logger("PhotoFetcher")

MEMORY_PATH = Path("data/scene_memory.json")
_MEMORY_CACHE: dict | None = None
_MEMORY_LOCK = Lock()
_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _load_memory() -> dict:
    """Load Rin's cached background references."""
    global _MEMORY_CACHE
    if _MEMORY_CACHE is not None:
        return _MEMORY_CACHE

    if MEMORY_PATH.exists():
        try:
            with MEMORY_PATH.open("r", encoding="utf-8") as fh:
                _MEMORY_CACHE = json.load(fh)
                return _MEMORY_CACHE
        except Exception as e:
            log.warning(f"Failed to load scene memory: {e}")

    _MEMORY_CACHE = {}
    return _MEMORY_CACHE


def _save_memory(memory: dict):
    global _MEMORY_CACHE
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MEMORY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(memory, fh, ensure_ascii=False, indent=4)
    _MEMORY_CACHE = memory


def _find_similar_scene(memory: dict, query: str) -> str | None:
    """Check if a similar scene already exists."""
    scenes = list(memory.keys())
    match = difflib.get_close_matches(query.lower(), scenes, n=1, cutoff=0.6)
    return match[0] if match else None


def _download_from_pexels(query: str, max_images=2) -> list[str]:
    """Download open-license images from Pexels."""
    out_dir = Path("assets/images/references")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = _get_session()
    url = f"https://api.pexels.com/v1/search?query={query}&per_page={max_images}"
    headers = {"Authorization": Config.PEXELS_API_KEY}

    try:
        res = session.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        log.error(f"Pexels API failed: {e}")
        return []

    paths = []
    safe = query.replace(" ", "_")
    for i, item in enumerate(data.get("photos", [])):
        try:
            img_url = item["src"]["large2x"]
            img_resp = session.get(img_url, timeout=10)
            img_resp.raise_for_status()
            img_data = img_resp.content
            path = out_dir / f"ref_{safe}_{i}.jpg"
            path.write_bytes(img_data)
            paths.append(str(path))
            log.info(f"Downloaded background → {path}")
        except Exception:
            pass

    return paths


def download_reference_images(keywords: list[str], max_images=2) -> list[str]:
    """Return background images but avoid re-downloading recurring places."""
    if not Config.PEXELS_API_KEY:
        return []

    with _MEMORY_LOCK:
        memory = _load_memory()
        query = " ".join(keywords).lower()

        # 1) try cached
        similar = _find_similar_scene(memory, query)
        if similar:
            entry = memory[similar]
            entry["last_used"] = datetime.utcnow().isoformat()
            _save_memory(memory)
            log.info(f"🧠 Using cached scene → {similar}")
            return entry["photo_refs"]

    # 2) download new
    refs = _download_from_pexels(query, max_images=max_images)
    if refs:
        with _MEMORY_LOCK:
            memory = _load_memory()
            memory[query] = {
                "keywords": keywords,
                "photo_refs": refs,
                "last_used": datetime.utcnow().isoformat(),
            }
            _save_memory(memory)

    return refs
