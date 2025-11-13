import random

def get_camera_instructions(pose):
    """Generate camera + angle instructions from pose spec."""
    lines = []

    if pose["type"] == "selfie":
        dist = pose.get("camera_distance_cm", "35-45")
        lines.append(f"Camera distance: {dist} cm (selfie).")
    else:
        dist = pose.get("camera_distance_m", "1.0-2.0")
        lines.append(f"Camera distance: {dist} meters (friend-taken).")

    angle = random.choice(pose["angle"])
    lines.append(f"Angle: {angle}.")

    lines.append(f"Framing: {pose['framing']}.")
    lines.append(f"Expression: {random.choice(pose['expression'])}.")
    lines.append(f"Hands: {pose['hands']}.")
    lines.append(f"Motion cues: {random.choice(pose['motion'])}.")

    return " ".join(lines)
