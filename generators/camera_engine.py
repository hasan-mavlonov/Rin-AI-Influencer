from typing import Optional

from typing import Optional

from generators.variation_state import VariationState


def _select_option(
    state: Optional[VariationState],
    key: str,
    options: list[str],
    advance: bool,
) -> str:
    if not options:
        return ""
    if not state:
        return options[0]

    idx = state.get_index(key, len(options))
    value = options[idx]
    if advance:
        state.advance(key, len(options))
    return value


def get_camera_instructions(
    pose: dict,
    state: Optional[VariationState] = None,
    pose_key: Optional[str] = None,
    advance: bool = True,
) -> str:
    """Generate camera + angle instructions from pose spec."""

    if not pose:
        return ""

    lines = []
    base_key = f"camera:{pose_key or pose.get('id', 'default')}"

    if pose["type"] == "selfie":
        dist = pose.get("camera_distance_cm", "35-45")
        lines.append(f"Camera distance: {dist} cm (selfie).")
    else:
        dist = pose.get("camera_distance_m", "1.0-2.0")
        lines.append(f"Camera distance: {dist} meters (friend-taken).")

    angle = _select_option(state, f"{base_key}:angle", pose.get("angle", []), advance)
    if angle:
        lines.append(f"Angle: {angle}.")

    framing = pose.get("framing")
    if framing:
        lines.append(f"Framing: {framing}.")

    expression = _select_option(
        state, f"{base_key}:expression", pose.get("expression", []), advance
    )
    if expression:
        lines.append(f"Expression: {expression}.")

    hands = pose.get("hands")
    if hands:
        lines.append(f"Hands: {hands}.")

    motion = _select_option(state, f"{base_key}:motion", pose.get("motion", []), advance)
    if motion:
        lines.append(f"Motion cues: {motion}.")

    clip_motion = _select_option(
        state,
        f"{base_key}:clip",
        pose.get("clip_motion", ["slow push-in for reel", "gentle pan left", "handheld sway"]),
        advance,
    )
    if clip_motion:
        lines.append(f"Clip pacing: {clip_motion}.")

    return " ".join(lines)
