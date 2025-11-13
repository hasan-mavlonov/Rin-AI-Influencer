# generators/photo_fetcher.py

import requests
import json
import difflib
from pathlib import Path
from datetime import datetime
from core.config import Config
from core.logger import get_logger

log = get_logger("PhotoFetcher")

MEMORY_PATH = Path("data/scene_memory.json")


def _load_memory() -> dict:
    """Load Rin's cached background references."""
    if MEMORY_PATH.exists():
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Failed to load scene memory: {e}")
    return {}


def _save_memory(memory: dict):
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=4), encoding="utf-8")


def _find_similar_scene(memory: dict, query: str) -> str | None:
    """Check if a similar scene already exists."""
    scenes = list(memory.keys())
    match = difflib.get_close_matches(query.lower(), scenes, n=1, cutoff=0.6)
    return match[0] if match else None


def _download_from_pexels(query: str, max_images=2) -> list[str]:
    """Download open-license images from Pexels."""
    out_dir = Path("assets/images/references")
    out_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://api.pexels.com/v1/search?query={query}&per_page={max_images}"
    headers = {"Authorization": Config.PEXELS_API_KEY}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        log.error(f"Pexels API failed: {e}")
        return []

    paths = []
    for i, item in enumerate(data.get("photos", [])):
        try:
            img_url = item["src"]["large2x"]
            img_data = requests.get(img_url, timeout=10).content
            safe = query.replace(" ", "_")
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
        memory[query] = {
            "keywords": keywords,
            "photo_refs": refs,
            "last_used": datetime.utcnow().isoformat(),
        }
        _save_memory(memory)

    return refs
