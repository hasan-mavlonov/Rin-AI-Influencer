# generators/idea_generator.py

import json
import random
import re
from typing import Optional
from openai import OpenAI
from core.config import Config
from core.logger import get_logger
from personas.loader import load_recent_posts

log = get_logger("IdeaGen")
client = OpenAI(api_key=Config.OPENAI_API_KEY)


BANNED_PHRASES = {
    "threads of life", "woven in pixels", "fragments of silence",
    "echoes of yesterday", "electric dreams", "whispers of the past",
}

BANNED_LOCATIONS = {"the bund", "bund", "yu garden", "yuyuan", "lujiazui"}

RARE_SPOTS = [
    "Anfu Road", "Wukang Road", "Ferguson Lane", "Yongkang Road",
    "Tianzifang back lanes", "Xintiandi side streets", "Sinan Mansions",
    "French Concession alleys", "Middle Huaihai Road alleys",
    "West Bund riverside path", "Suzhou Creek boardwalk",
    "Jing'an Park", "Zhongshan Park corner paths", "Xiangyang Park",
    "Columbia Circle", "Kerry Parkside gym area", "Jing'an Kerry Center",
    "Raffles City Changning", "TX Huaihai", "K11 Art Mall",
    "1933 Old Millfun", "Cool Docks", "Sihang Warehouse riverfront",
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


def _pick_shot_category():
    return random.choices(
        ["selfie_morning", "selfie_gym", "selfie_mirror", "street_casual", "cozy_night"],
        weights=[2, 2, 2, 1, 1],
        k=1,
    )[0]


SEEDS = {
    "selfie_morning": ["morning coffee run", "slow start kind of day", "sunlight selfie moment", "first coffee then life"],
    "selfie_gym": ["today's gym fit", "post workout glow", "back to the gym", "leg day again lol"],
    "selfie_mirror": ["mirror fit check", "getting ready outfit", "elevator selfie again", "nothing special just me"],
    "street_casual": ["little walk in the city", "afternoon street vibes", "wandering around shanghai", "soft city day"],
    "cozy_night": ["late night laptop time", "cozy night in", "sleepy but online", "pjs and blue light"],
}


def generate_idea(persona_name: str) -> tuple[str, dict]:
    posts = load_recent_posts(persona_name, limit=5)
    recent_tokens = [_tokenize(_normalized(p.get("idea"))) for p in posts if p.get("idea")]

    category = _pick_shot_category()
    base_seed = random.choice(SEEDS[category])

    # --- IDEA (2–6 words)
    prompt = f"""
Write a SHORT post idea (2–6 words).
Everyday English. No metaphors. No poetic language.
Tone: Fit Aitana, casual, real.
Seed: "{base_seed}"

Return ONLY the idea phrase.
"""
    idea = None
    for _ in range(3):
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=16,
        )
        cand = res.choices[0].message.content.strip()
        if not _too_similar(cand, recent_tokens):
            idea = cand
            break

    if not idea:
        idea = base_seed

    log.info(f"🧠 Idea: {idea} ({category})")

    # --- LOCATION JSON ---
    place_prompt = f"""
Given idea "{idea}" and category "{category}", pick ONE real Shanghai place.

Rules:
- Gym ideas → gym-like areas (Columbia Circle, mall gym areas, etc.)
- Selfie at home → "apartment hallway", "bedroom mirror", "elevator"
- Street casual → Anfu Rd, Wukang Rd, Tianzifang alleys, etc.
- Avoid Bund, Yu Garden, Lujiazui.

Return strict JSON:
{{
 "name": "...",
 "description": "...",
 "keywords": ["k1","k2","k3"],
 "shot_category": "{category}"
}}
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": place_prompt}],
        temperature=0.8,
        max_tokens=200,
    )

    raw = res.choices[0].message.content.strip()
    try:
        place = _extract_json(raw)
        nn = _normalized(place["name"])
        if nn in BANNED_LOCATIONS:
            raise ValueError
    except Exception:
        name = random.choice(RARE_SPOTS)
        place = {
            "name": name,
            "description": f"Simple casual spot near {name}.",
            "keywords": ["shanghai", "street", "selfie"],
            "shot_category": category,
        }

    log.info(f"📍 Location: {place['name']}")
    return idea, place
