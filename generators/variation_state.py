"""Utilities for persisting deterministic variation cycles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


STATE_PATH = Path(".runtime/image_variation_state.json")


class VariationState:
    """Persisted index tracker for deterministic prompt variation cycles."""

    def __init__(self, path: Path | str = STATE_PATH):
        self.path = Path(path)
        self._data = self._load()
        self._indexes: Dict[str, int] = self._data.setdefault("indexes", {})
        self._dirty = False

    # ------------------------------------------------------------------
    # Core persistence helpers
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                # Corrupted state → start over with a clean slate.
                return {"indexes": {}}
        return {"indexes": {}}

    def save(self):
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._dirty = False

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------
    def get_index(self, key: str, length: int) -> int:
        if length <= 0:
            return 0
        return self._indexes.get(key, 0) % length

    def advance(self, key: str, length: int):
        if length <= 0:
            return
        current = self._indexes.get(key, 0) % length
        self._indexes[key] = (current + 1) % length
        self._dirty = True

    def reset(self, key: str):
        if key in self._indexes:
            del self._indexes[key]
            self._dirty = True
