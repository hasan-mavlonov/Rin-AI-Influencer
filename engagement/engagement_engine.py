from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests

from core.config import Config
from core.logger import get_logger
from generators.idea_generator import get_scene_memory_snapshot
from poster.instagram_poster import GRAPH_API_BASE, comment_on_media

log = get_logger("EngagementEngine")

TARGETS_PATH = Path(__file__).resolve().parent / "targets.json"
HISTORY_PATH = Path("data/engagement_history.json")
MAX_POST_AGE = timedelta(days=10)


def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Could not decode %s; resetting file.", path)
        return []


def _write_json(path: Path, payload: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _resolve_account_id(username: str) -> str | None:
    token = Config.INSTAGRAM_ACCESS_TOKEN
    owner = Config.INSTAGRAM_BUSINESS_ACCOUNT_ID
    if not token or not owner:
        log.debug("Cannot resolve account id for %s: credentials missing.", username)
        return None

    endpoint = f"{GRAPH_API_BASE}/{owner}"
    fields = f"business_discovery.username({username}){{id,username,followers_count,media_count}}"
    params = {"fields": fields, "access_token": token}
    try:
        resp = requests.get(endpoint, params=params, timeout=20)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Business discovery failed for %s: %s", username, exc)
        return None

    biz = (data or {}).get("business_discovery")
    if biz and biz.get("id"):
        return biz["id"]
    log.debug("Business discovery did not return an id for %s: %s", username, data)
    return None


def discover_targets() -> List[Dict[str, Any]]:
    """Return a shuffled list of prioritized targets for engagement."""

    seeds = _load_json(TARGETS_PATH)
    for seed in seeds:
        if not seed.get("account_id") and seed.get("username"):
            account_id = _resolve_account_id(seed["username"])
            if account_id:
                seed["account_id"] = account_id

    keyword_targets: list[dict] = []
    token = Config.INSTAGRAM_ACCESS_TOKEN
    if token:
        for keyword in ["Shanghai cafe", "Shanghai photographer", "quiet shanghai", "TX Huaihai", "Taikoo Li"]:
            try:
                resp = requests.get(
                    f"{GRAPH_API_BASE}/search",
                    params={"access_token": token, "type": "page", "q": keyword, "limit": 3},
                    timeout=15,
                )
                data = resp.json() if resp.ok else {}
                for item in data.get("data", []):
                    keyword_targets.append(
                        {
                            "username": item.get("username") or item.get("name"),
                            "account_id": item.get("id"),
                            "category": "discovery",
                            "source": keyword,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.debug("Keyword discovery failed for '%s': %s", keyword, exc)
    else:
        log.debug("Skipping keyword discovery: missing Instagram token.")

    combined = [t for t in seeds + keyword_targets if t.get("username") or t.get("account_id")]

    def _priority(target: dict) -> int:
        category = target.get("category", "")
        order = ["micro_influencer", "lifestyle", "photographer", "cafe", "mall", "discovery"]
        return order.index(category) if category in order else len(order)

    combined.sort(key=_priority)
    random.shuffle(combined)
    return combined


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def fetch_recent_posts(account_id: str) -> List[Dict[str, Any]]:
    """Fetch the last few posts for an account via the Graph API."""

    token = Config.INSTAGRAM_ACCESS_TOKEN
    if not token:
        log.warning("Cannot fetch posts: Instagram token missing.")
        return []

    endpoint = f"{GRAPH_API_BASE}/{account_id}/media"
    params = {
        "access_token": token,
        "fields": "id,caption,timestamp,media_type,permalink,children.limit(1){media_type}",
        "limit": 5,
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=20)
        data = resp.json() if resp.ok else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch media for %s: %s", account_id, exc)
        return []

    now = datetime.utcnow()
    posts: list[dict] = []
    for post in data.get("data", []):
        ts = _parse_timestamp(post.get("timestamp"))
        if not ts:
            continue
        if now - ts > MAX_POST_AGE:
            continue
        posts.append({"id": post.get("id"), "caption": post.get("caption", ""), "timestamp": ts})

    return posts


def _recent_history() -> list[dict]:
    history = _load_json(HISTORY_PATH)
    trimmed = history[-400:]
    if len(trimmed) != len(history):
        _write_json(HISTORY_PATH, trimmed)
    return trimmed


def _has_commented(media_id: str, history: list[dict]) -> bool:
    return any(entry.get("media_id") == media_id for entry in history)


def _account_in_cooldown(account_id: str, history: list[dict]) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=Config.ENGAGEMENT_ACCOUNT_COOLDOWN_HOURS)
    for entry in reversed(history):
        if entry.get("account_id") == account_id:
            ts = _parse_timestamp(entry.get("timestamp"))
            if ts and ts > cutoff:
                return True
            break
    return False


def _unique_comment_text(history: list[dict], candidate: str) -> bool:
    recent_texts = {entry.get("comment") for entry in history[-80:] if entry.get("comment")}
    return candidate not in recent_texts


def generate_comment(post_context: Dict[str, Any]) -> str:
    """Craft a soft, curious comment based on Rin's Shanghai tone."""

    caption = (post_context.get("caption") or "").lower()
    mood = post_context.get("mood", "calm")
    beat = post_context.get("beat", "")
    hints: list[str] = []

    if "cafe" in caption or post_context.get("category") == "cafe":
        hints.append("this café feels gentle")
    if "night" in caption or "evening" in beat:
        hints.append("soft evening light")
    if "river" in caption or "bund" in caption:
        hints.append("the river air")

    base_comments = [
        "Love the colors here — feels like a quiet moment in the middle of the city.",
        "I've walked past this place so many times, it always feels warm.",
        "This lighting is beautiful, Shanghai evenings always look like this.",
        "This café looks so peaceful… adding it to my list.",
        "The textures feel so calm, like a pause from the rush outside.",
        "Feels like a soft pocket of Shanghai, gentle and close.",
    ]

    mood_overlays = {
        "reflective": "Something about this looks thoughtful, like the city exhaling.",
        "playful": "This looks so fun — makes me want to wander over right now.",
        "focused": "Quiet scene, it feels like a good place to settle in for a while.",
        "hopeful": "Light looks tender here, the kind of place that lifts the day.",
    }

    overlay = mood_overlays.get(mood)
    if overlay:
        base_comments.append(overlay)

    if hints:
        base_comments.append(" ".join(["Love how", random.choice(hints), "sits in the scene."]))

    return random.choice(base_comments)


def post_comment(media_id: str, text: str) -> Dict[str, Any]:
    """Post a comment and retry once if an error occurs."""

    try:
        return comment_on_media(media_id, text)
    except Exception as exc:  # noqa: BLE001
        log.warning("Comment failed for %s, retrying once: %s", media_id, exc)
        try:
            time.sleep(2)
            return comment_on_media(media_id, text)
        except Exception as exc2:  # noqa: BLE001
            log.error("Comment retry failed for %s: %s", media_id, exc2)
            return {"status": "error", "error": str(exc2)}


def _select_candidates(targets: list[dict], history: list[dict], desired: int) -> list[dict]:
    chosen: list[dict] = []
    for target in targets:
        if len(chosen) >= desired:
            break
        account_id = target.get("account_id")
        username = target.get("username")
        if not account_id and username:
            account_id = _resolve_account_id(username)
        if not account_id:
            continue
        if _account_in_cooldown(account_id, history):
            continue
        posts = fetch_recent_posts(account_id)
        for post in posts:
            if len(chosen) >= desired:
                break
            if not post.get("id") or _has_commented(post["id"], history):
                continue
            chosen.append(
                {
                    "account_id": account_id,
                    "username": username,
                    "category": target.get("category"),
                    "post": post,
                }
            )
            break
    return chosen


def run_engagement_cycle() -> None:
    """Execute one engagement batch with delays and history tracking."""

    history = _recent_history()
    arc = get_scene_memory_snapshot()
    mood = arc.get("current_mood", "calm")
    beat = arc.get("beat", "")

    targets = discover_targets()
    desired_comments = random.randint(3, 7)
    candidates = _select_candidates(targets, history, desired_comments)

    if not candidates:
        log.info("No eligible posts found for engagement.")
        return

    min_delay = Config.ENGAGEMENT_MIN_DELAY_SECONDS
    max_delay = max(Config.ENGAGEMENT_MAX_DELAY_SECONDS, min_delay + 1)

    for item in candidates:
        post = item["post"]
        media_id = post["id"]
        context = {
            "caption": post.get("caption", ""),
            "category": item.get("category"),
            "mood": mood,
            "beat": beat,
        }
        comment = generate_comment(context)
        if not _unique_comment_text(history, comment):
            continue

        result = post_comment(media_id, comment)
        success = result.get("status") == "success"
        history.append(
            {
                "account_id": item.get("account_id"),
                "username": item.get("username"),
                "media_id": media_id,
                "comment": comment,
                "timestamp": datetime.utcnow().isoformat(),
                "mood": mood,
                "beat": beat,
                "status": result.get("status"),
            }
        )
        _write_json(HISTORY_PATH, history)

        if not success:
            continue

        delay = random.randint(min_delay, max_delay)
        log.info("Cooling down for %ss before next engagement.", delay)
        time.sleep(delay)
