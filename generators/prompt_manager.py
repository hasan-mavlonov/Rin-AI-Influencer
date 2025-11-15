# generators/prompt_manager.py

import json
from pathlib import Path
from typing import Dict, Optional

_STATE = Path(".runtime/image_variation_state.json")


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

    display_name = persona.get("display_name") or persona.get("id", "Rin")

    return (
        f"{display_name} is a fitness-minded lifestyle creator in Shanghai. "
        "Match her face, hair, and proportions strictly to the attached reference photos—do not invent or describe new facial details. "
        f"Location: {loc}. {desc} "
        f"Style keywords: {style}. "
        f"Wardrobe vibe: {signature_outfit}. "
        f"Post idea: {idea}. "
        f"Scene hints: {kws}. "
        "Keep lighting believable and rooted in real-world photography."
    )
