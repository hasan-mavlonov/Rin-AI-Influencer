# generators/captioner.py

from personas.loader import load_recent_posts
import random
import time

from openai import OpenAI

from core.config import Config
from core.logger import get_logger
from utils.persona_cache import get_persona

log = get_logger("Captioner")

client = None
if Config.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
    except Exception as exc:  # noqa: BLE001 - broad for library initialization.
        log.error(f"Failed to initialize OpenAI client: {exc}")
        client = None


def _mock(persona, idea):
    endings = ["#ShanghaiLife", "#OOTD", "#CityDiaries"]
    return f"{idea.capitalize()} 💛 {random.choice(endings)}"


def generate_caption(persona_name: str, idea: str, place=None) -> str:
    persona = get_persona(persona_name)
    if persona is None:
        log.warning(f"Persona '{persona_name}' not found; using fallback caption generator.")
        return _mock({}, idea)
    posts = load_recent_posts(persona_name, limit=5)
    prev = "\n".join([p.get("caption") for p in posts if p.get("caption")]) or ""

    if not client:
        return _mock(persona, idea)

    sys = (
        "You are a female lifestyle influencer in Shanghai. "
        "Write short, casual, real captions. No metaphors."
    )

    usr = (
        f"Recent captions:\n{prev}\n\n"
        f"Idea: {idea}\n"
        f"Location: {place.get('name','') if place else ''}\n"
        "Rules:\n"
        "- 1–2 lines max\n"
        "- No poetic language\n"
        "- Max 3 emojis\n"
        "- End with 2–3 natural hashtags\n"
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
