from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from core.logger import get_logger

log = get_logger("RenderingRouter")


@dataclass
class ScenePlan:
    """Unified metadata for routing image generation requests."""

    prompt: str
    negative_prompt: str | None
    steps: int
    guidance: float
    subject: str
    fidelity: Literal["standard", "high"] = "standard"
    requires_high_fidelity: bool = False


def render_scene(
    plan: ScenePlan,
    gemini_renderer: Callable[[], str],
    sdxl_renderer: Callable[[], str],
) -> str:
    """Route rendering requests to SDXL or Gemini backends.

    SDXL+LoRA is attempted first when Rin requires high fidelity. Any SDXL
    failures automatically fall back to the Gemini pipeline.
    """

    should_use_sdxl = (
        plan.subject.lower() == "rin"
        and plan.fidelity == "high"
        and plan.requires_high_fidelity
    )

    if should_use_sdxl:
        try:
            log.info("Routing scene to SDXL backend (high fidelity requested).")
            return sdxl_renderer()
        except Exception as exc:  # noqa: BLE001 - downstream network errors
            log.warning("SDXL backend unavailable, falling back to Gemini: %s", exc)

    log.info("Routing scene to Gemini backend.")
    return gemini_renderer()
