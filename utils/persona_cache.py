"""Lightweight persona caching helpers for per-run reuse."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from personas.loader import load_persona


@lru_cache(maxsize=16)
def get_persona(persona_name: str) -> Mapping[str, Any]:
    """Return cached persona data for the given persona name."""

    # Personas are static during a single run, so re-use the loaded mapping.
    return load_persona(persona_name)
