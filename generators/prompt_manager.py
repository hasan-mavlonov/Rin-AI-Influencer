# generators/prompt_manager.py

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

_STATE = Path(".runtime/image_variation_state.json")


def _shanghai_weather_hint() -> str:
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "cool Shanghai morning haze"
    if 10 <= hour < 16:
        return "bright but soft daytime light"
    if 16 <= hour < 19:
        return "golden hour glow over plane trees"
    if 19 <= hour < 23:
        return "neon reflections on humid streets"
    return "quiet midnight LEDs and window glow"


def build_image_prompt(persona: Dict, idea: str, place: Optional[Dict] = None) -> str:
    """Persona framing without facial description + idea + location context."""
    if _STATE.exists():
        try:
            st = json.loads(_STATE.read_text())
        except Exception:
            st = {"cycle": 0}
    else:
        st = {"cycle": 0}

    st["cycle"] += 1
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(st))

    appearance = persona.get("appearance", {})
    style = ", ".join(appearance.get("aesthetic_keywords", []))
    signature_outfit = appearance.get("signature_outfit", "Pastel athleisure fits")

    loc = (place or {}).get("name", "Shanghai")
    desc = (place or {}).get("description", "")
    kws = ", ".join((place or {}).get("keywords", [])[:6])
    arc = (place or {}).get("arc")
    mood = (place or {}).get("arc_mood") or "calm"
    beat = (place or {}).get("arc_beat")

    display_name = persona.get("display_name") or persona.get("id", "Rin")

    return (
        f"{display_name} is a Shanghai-based digital girl living a daily storyline. "
        "Match her face, hair, and proportions strictly to the attached reference photos—do not invent or describe new facial details. "
        f"Location: {loc}. {desc} "
        f"Weather/air mood: {_shanghai_weather_hint()}. "
        f"Style keywords: {style}. "
        f"Wardrobe vibe: {signature_outfit}. "
        f"Post idea: {idea}. "
        f"Scene hints: {kws}. "
        f"Arc: {arc or 'daily life'}; beat: {beat or 'quiet transition'}; mood: {mood}. "
        "Keep lighting believable and rooted in Shanghai street and café photography."
    )
