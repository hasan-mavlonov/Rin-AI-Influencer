# generators/captioner.py

from personas.loader import load_recent_posts
import random
import time

from openai import OpenAI

from core.config import Config
from core.logger import get_logger
from utils.persona_cache import get_persona
from generators.idea_generator import get_scene_memory_snapshot

log = get_logger("Captioner")

client = None
if Config.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
    except Exception as exc:  # noqa: BLE001 - broad for library initialization.
        log.error(f"Failed to initialize OpenAI client: {exc}")
        client = None


def _mock(persona, idea):
    endings = ["#ShanghaiLife", "#CityDiaries", "#RinInShanghai"]
    return f"{idea.capitalize()} — keeping it gentle today. {random.choice(endings)}"


def generate_caption(persona_name: str, idea: str, place=None) -> str:
    persona = get_persona(persona_name)
    if persona is None:
        log.warning(f"Persona '{persona_name}' not found; using fallback caption generator.")
        return _mock({}, idea)
    posts = load_recent_posts(persona_name, limit=5)
    prev = "\n".join([p.get("caption") for p in posts if p.get("caption")]) or ""

    if not client:
        return _mock(persona, idea)

    arc = get_scene_memory_snapshot()
    location_line = (place or {}).get("name", "Shanghai")
    mood = (place or {}).get("arc_mood") or arc.get("current_mood") or "calm"
    beat = (place or {}).get("arc_beat") or arc.get("beat") or "daily note"

    sys = (
        "You are Rin, a soft-spoken Shanghai digital girl. "
        "Your captions feel like diary fragments: grounded, sincere, sometimes slightly melancholic but hopeful. "
        "Stay concise, in English with occasional simple Chinese phrases."
    )

    usr = (
        f"Recent captions to avoid repeating tone:\n{prev}\n\n"
        f"Idea: {idea}\n"
        f"Location: {location_line}\n"
        f"Arc: {arc.get('arc')} | Beat: {beat} | Mood: {mood}\n"
        "Write 1-2 short lines that show what she notices and how she feels.\n"
        "Rules:\n"
        "- Keep it intimate and cinematic but not flowery.\n"
        "- Include a small introspective thought about Shanghai (streets, weather, metro, light).\n"
        "- Use up to 3 emojis maximum, if any.\n"
        "- End with 2-3 natural hashtags mixing English and light pinyin (no spam).\n"
        "- Never start with 'Good morning' or generic greetings.\n"
    )

    retries = 3
    delay = 1.5
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": sys},
                          {"role": "user", "content": usr}],
                temperature=0.8,
                max_tokens=120,
                timeout=30,
            )
            return r.choices[0].message.content.strip()
        except Exception as exc:  # noqa: BLE001 - surface errors while preserving fallback.
            last_error = exc
            log.warning(
                "OpenAI caption attempt %s/%s failed: %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(delay)

    if last_error:
        log.error(f"Falling back to mock caption after API failures: {last_error}")
    return _mock(persona, idea)
