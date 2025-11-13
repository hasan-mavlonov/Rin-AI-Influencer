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


def build_image_prompt(persona: Dict, idea: str, place: Optional[Dict] = None) -> str:
    """Basic personality → idea → location description."""
    st = _load()
    st["cycle"] += 1
    _save(st)

    appearance = persona.get("appearance", {})
    base = appearance.get("summary", "young East Asian woman with long dark hair")
    style = ", ".join(appearance.get("aesthetic_keywords", []))

    loc = (place or {}).get("name", "Shanghai")
    desc = (place or {}).get("description", "")
    kws = ", ".join((place or {}).get("keywords", [])[:6])

    return (
        f"{base}, casual lifestyle influencer in Shanghai. "
        f"Location: {loc}. {desc} "
        f"Style keywords: {style}. "
        f"Post idea: {idea}. "
        f"Scene hints: {kws}."
    )
