# generators/idea_generator.py

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI

from core.config import Config
from core.logger import get_logger
from personas.loader import load_recent_posts

log = get_logger("IdeaGen")

client: OpenAI | None = None
if Config.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
    except Exception as exc:  # noqa: BLE001 - third-party initialization.
        log.error(f"Failed to initialize OpenAI client: {exc}")
        client = None
else:
    log.warning("OPENAI_API_KEY missing; using fallback idea generation.")


DATA_DIR = Path("data")
SCENE_MEMORY_PATH = DATA_DIR / "scene_memory.json"

BANNED_PHRASES = {
    "threads of life",
    "woven in pixels",
    "fragments of silence",
    "echoes of yesterday",
    "electric dreams",
    "whispers of the past",
}

# Allow Bund; keep only tourist traps we want to avoid overusing
BANNED_LOCATIONS = {"yu garden", "yuyuan"}

WEEKLY_ARCS = [
    {
        "name": "Cafe Drift Week",
        "description": "Rin spends the week journaling in different French Concession cafés, chasing soft daylight and quiet corners.",
        "locations": [
            "Anfu Road cafés",
            "Ferguson Lane courtyard",
            "Tianzifang back lanes",
            "Xintiandi side streets",
            "Wukang Road windows",
        ],
        "beats": [
            "soft morning journal",
            "noon latte refill",
            "rainy window reflection",
            "evening latte art study",
            "weekend slow brunch",
        ],
        "moods": ["sleepy", "focused", "reflective", "hopeful"],
        "shot_bias": "selfie_morning",
    },
    {
        "name": "Metro Echoes",
        "description": "Commuting across Line 2 and 10, watching strangers and neon tunnels, collecting feelings between stations.",
        "locations": [
            "Jing'an Temple metro station",
            "Xujiahui exit crowd",
            "Lujiazui platform edge",
            "Zhongshan Park transfer",
            "West Nanjing Road escalators",
        ],
        "beats": [
            "morning commute",
            "crowded noon ride",
            "quiet carriage scroll",
            "rain on metro windows",
            "late ride home",
        ],
        "moods": ["observant", "introspective", "restless"],
        "shot_bias": "street_casual",
    },
    {
        "name": "Night Walks by the River",
        "description": "Night walks around Suzhou Creek and the Bund, letting neon and humidity soften the day.",
        "locations": [
            "North Bund boardwalk",
            "West Bund riverside path",
            "Sihang Warehouse riverfront",
            "Cool Docks",
            "Fuxing Park after dark",
        ],
        "beats": [
            "blue hour walk",
            "post-edit stretch",
            "humid neon pause",
            "footbridge reflections",
            "late ferry breeze",
        ],
        "moods": ["melancholy", "curious", "calm"],
        "shot_bias": "cozy_night",
    },
    {
        "name": "Study Chinese Week",
        "description": "Preparing for a test with vocab cards, café study sessions, and conversations with baristas.",
        "locations": [
            "Fuxing Park benches",
            "Sinan Mansions library café",
            "K11 study corner",
            "Taikoo Li community tables",
            "apartment desk near Jing'an",
        ],
        "beats": [
            "morning vocab warmup",
            "tone practice at lunch",
            "flashcards on the metro",
            "tired evening review",
            "weekend mock test",
        ],
        "moods": ["hopeful", "focused", "tired", "determined"],
        "shot_bias": "selfie_mirror",
    },
    {
        "name": "Mall Weekends",
        "description": "Escaping weather by roaming malls, trying snacks, and watching escalator lights.",
        "locations": [
            "Taikoo Li Qiantan",
            "MixC Mall",
            "TX Huaihai",
            "K11 Art Mall",
            "Jing'an Kerry Center",
        ],
        "beats": [
            "morning escalator ride",
            "window shopping pause",
            "food court break",
            "arcade detour",
            "night roof deck",
        ],
        "moods": ["playful", "restless", "cosy"],
        "shot_bias": "street_casual",
    },
]


_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z]+")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _normalized(s):
    return _WHITESPACE_RE.sub(" ", (s or "").lower().strip())


def _tokenize(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(text))


def _too_similar(s, recent_tokens):
    cand = _normalized(s)
    if any(p in cand for p in BANNED_PHRASES):
        return True
    tokens = _tokenize(cand)
    for rt in recent_tokens:
        if tokens and len(tokens & rt) / max(1, len(tokens)) > 0.6:
            return True
    return False


def _extract_json(txt):
    m = _JSON_OBJECT_RE.search(txt)
    if not m:
        raise ValueError("no json")
    return json.loads(m.group(0))


def _start_of_week(dt: datetime) -> datetime:
    return dt - timedelta(days=dt.weekday())


def _load_scene_memory() -> dict:
    if SCENE_MEMORY_PATH.exists():
        try:
            return json.loads(SCENE_MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - we want deterministic fallback.
            log.warning(f"Unable to read scene memory, recreating. Error: {exc}")
    week_start = _start_of_week(datetime.now()).date().isoformat()
    return {
        "week_start": week_start,
        "arc": None,
        "beat_index": 0,
        "recent_locations": [],
        "recent_moods": [],
    }


def _persist_scene_memory(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_MEMORY_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _choose_new_arc(previous: Optional[str]) -> dict:
    pool = [arc for arc in WEEKLY_ARCS if arc["name"] != previous] or WEEKLY_ARCS
    return random.choice(pool)


def _ensure_arc(memory: dict) -> tuple[dict, dict]:
    current_week = _start_of_week(datetime.now()).date().isoformat()
    if memory.get("week_start") != current_week:
        memory = {
            "week_start": current_week,
            "arc": None,
            "beat_index": 0,
            "recent_locations": [],
            "recent_moods": [],
        }

    arc_name = memory.get("arc")
    arc = next((a for a in WEEKLY_ARCS if a["name"] == arc_name), None)
    if arc is None:
        arc = _choose_new_arc(previous=arc_name)
        memory["arc"] = arc["name"]
        memory["beat_index"] = 0
    return memory, arc


def _pick_shot_category(preferred: Optional[str] = None):
    categories = [
        "selfie_morning",
        "selfie_gym",
        "selfie_mirror",
        "street_casual",
        "cozy_night",
    ]
    if preferred in categories:
        categories.insert(0, preferred)
    return random.choice(categories)


SEEDS = {
    "selfie_morning": [
        "morning coffee run",
        "slow start kind of day",
        "sunlight on sleepy eyes",
        "first coffee then life",
    ],
    "selfie_gym": [
        "today's gym fit",
        "post workout glow",
        "back to the gym",
        "leg day again lol",
    ],
    "selfie_mirror": [
        "mirror fit check",
        "getting ready outfit",
        "elevator selfie again",
        "study break stretch",
    ],
    "street_casual": [
        "little walk in the city",
        "afternoon street vibes",
        "wandering around shanghai",
        "soft city day",
    ],
    "cozy_night": [
        "late night laptop time",
        "cozy night in",
        "sleepy but online",
        "pjs and blue light",
    ],
}


def _fallback_location(arc: dict, category: str) -> dict:
    name = random.choice(arc.get("locations", []) or ["Shanghai side street"])
    return {
        "name": name,
        "description": f"Scene for {arc['name']} arc.",
        "keywords": ["shanghai", "street", category],
        "shot_category": category,
        "arc": arc["name"],
        "arc_mood": random.choice(arc.get("moods", ["calm"])),
        "arc_beat": arc.get("beats", [""])[0] if arc.get("beats") else "",
    }


def _apply_location_rules(place: dict, recent_locations: list[str]) -> dict:
    nn = _normalized(place.get("name"))
    if nn in BANNED_LOCATIONS:
        raise ValueError("location banned")
    if place.get("name") in recent_locations:
        place["description"] += "; choose a new angle to keep it fresh"
    return place


def _update_memory(memory: dict, arc: dict, place: dict, mood: str) -> None:
    memory["arc"] = arc["name"]
    memory["beat_index"] = memory.get("beat_index", 0) + 1
    recents = memory.get("recent_locations", [])
    recents = ([place.get("name")] + recents)[:6]
    memory["recent_locations"] = recents
    moods = memory.get("recent_moods", [])
    moods = ([mood] + moods)[:6]
    memory["recent_moods"] = moods
    memory["last_update"] = datetime.now().isoformat()
    _persist_scene_memory(memory)


def get_scene_memory_snapshot() -> dict:
    """Lightweight accessor used by the scheduler and captioner."""

    memory = _load_scene_memory()
    _, arc = _ensure_arc(memory)
    beat_index = memory.get("beat_index", 0)
    beat = (arc.get("beats") or [""])[beat_index % max(1, len(arc.get("beats") or [""]))]
    mood = (arc.get("moods") or ["calm"])[beat_index % max(1, len(arc.get("moods") or ["calm"]))]
    return {
        "arc": arc["name"],
        "beat": beat,
        "current_mood": mood,
        "week_start": memory.get("week_start"),
    }


def generate_idea(persona_name: str) -> Tuple[str, dict]:
    posts = load_recent_posts(persona_name, limit=6)
    recent_tokens = [_tokenize(_normalized(p.get("idea"))) for p in posts if p.get("idea")]

    memory = _load_scene_memory()
    memory, arc = _ensure_arc(memory)
    beat_index = memory.get("beat_index", 0)
    beat = (arc.get("beats") or [""])[beat_index % max(1, len(arc.get("beats") or [""]))]
    mood = (arc.get("moods") or ["calm"])[beat_index % max(1, len(arc.get("moods") or ["calm"]))]

    category = _pick_shot_category(arc.get("shot_bias"))
    base_seed = random.choice(SEEDS.get(category, ["soft shanghai day"]))
    location_candidates = ", ".join(arc.get("locations", []))
    prev_ideas = " | ".join([p.get("idea", "") for p in posts[:3] if p.get("idea")])

    prompt = f"""
You are Rin's narrative planner. Continue her Shanghai weekly arc with a grounded content beat.

Arc: {arc['name']} — {arc['description']}
Today's beat: {beat}
Mood keywords: {mood}
Location candidates: {location_candidates}
Shot category: {category}
Recent ideas: {prev_ideas}
Seed to riff on: "{base_seed}"

Return ONLY compact JSON:
{{
  "idea": "4-10 word idea, present tense, no poetry",
  "location": {{
    "name": "realistic Shanghai spot",
    "description": "one short clause about the moment",
    "keywords": ["k1","k2","k3"],
    "shot_category": "{category}",
    "arc": "{arc['name']}",
    "arc_mood": "{mood}",
    "arc_beat": "{beat}"
  }}
}}
"""

    idea = None
    place = None
    if client is not None:
        for attempt in range(1, 4):
            try:
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=180,
                    timeout=30,
                )
                raw = res.choices[0].message.content.strip()
                data = _extract_json(raw)
                cand_idea = data.get("idea") or ""
                cand_place = data.get("location") or {}
                if not _too_similar(cand_idea, recent_tokens):
                    idea = cand_idea.strip()
                    place = cand_place
                    break
            except Exception as exc:  # noqa: BLE001 - API errors vary widely.
                log.warning(
                    "OpenAI idea attempt %s/3 failed: %s",
                    attempt,
                    exc,
                )
                time.sleep(1.5)

    if not idea:
        idea = f"{beat} near {random.choice(arc.get('locations', ['Shanghai']))}".strip()
    if not place:
        place = _fallback_location(arc, category)

    try:
        place = _apply_location_rules(place, memory.get("recent_locations", []))
    except Exception as exc:  # noqa: BLE001 - maintain robustness
        log.warning(f"Location rule fallback: {exc}")
        place = _fallback_location(arc, category)

    place.setdefault("arc", arc["name"])
    place.setdefault("arc_mood", mood)
    place.setdefault("arc_beat", beat)
    place.setdefault("shot_category", category)

    _update_memory(memory, arc, place, mood)

    log.info(f"🧠 Idea: {idea} ({category}) — arc '{arc['name']}', beat '{beat}'")
    log.info(f"📍 Location: {place['name']} | mood: {mood}")
    return idea, place
