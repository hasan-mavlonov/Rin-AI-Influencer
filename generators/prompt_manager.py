# generators/prompt_manager.py

from typing import Dict, Optional
import json
from pathlib import Path

_STATE = Path(".runtime/image_variation_state.json")


def _load():
    if _STATE.exists():
        try:
            return json.loads(_STATE.read_text())
        except:
            pass
    return {"cycle": 0}


def _save(data):
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(data))


def _identity_sentence(persona: Dict) -> str:
    display_name = persona.get("display_name") or persona.get("id", "Rin")
    appearance = persona.get("appearance", {})

    def _val(key: str) -> str:
        return appearance.get(key) or "unspecified"

    return (
        f"{display_name}'s hair: {_val('hair')}; "
        f"eyes: {_val('eyes')}; "
        f"skin tone: {_val('skin_tone')}; "
        f"distinct features: {_val('distinct_features')}; "
        f"expression: {_val('facial_expression')}."
    )


def build_image_prompt(persona: Dict, idea: str, place: Optional[Dict] = None) -> str:
    """Basic personality → identity sentence → idea → location description."""
    st = _load()
    st["cycle"] += 1
    _save(st)

    appearance = persona.get("appearance", {})
    base = appearance.get("summary", "young East Asian woman with long dark hair")
    style = ", ".join(appearance.get("aesthetic_keywords", []))

    loc = (place or {}).get("name", "Shanghai")
    desc = (place or {}).get("description", "")
    kws = ", ".join((place or {}).get("keywords", [])[:6])

    identity_sentence = _identity_sentence(persona)
    display_name = persona.get("display_name") or persona.get("id", "Rin")
    negative_clause = (
        f"Do not change {display_name}'s facial structure, eye color, or signature hairstyle."
    )

    return (
        f"{base}, casual lifestyle influencer in Shanghai. "
        f"{identity_sentence} "
        f"Location: {loc}. {desc} "
        f"Style keywords: {style}. "
        f"Post idea: {idea}. "
        f"Scene hints: {kws}. "
        f"{negative_clause}"
    )
