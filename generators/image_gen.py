import time, json, io
from pathlib import Path
from PIL import Image, ImageEnhance
from typing import Optional
from google import genai

from core.config import Config
from core.logger import get_logger
from generators.prompt_manager import build_image_prompt
from generators.photo_fetcher import download_reference_images
from generators.camera_engine import get_camera_instructions
from generators.variation_state import VariationState

log = get_logger("ImageGen")

REF_DIR = Path("personas/rin/examples")
from google.genai.types import Part


# ----------------------------
# Upload helpers
# ----------------------------

def _as_part(path: Path):
    mime = "image/jpeg"
    if path.suffix.lower() == ".png":
        mime = "image/png"

    return Part.from_bytes(
        data=path.read_bytes(),
        mime_type=mime
    )


def _upload_persona(client, p: Path):
    return client.files.upload(file=str(p))


# ----------------------------
# Enhancement filter
# ----------------------------

def _apply_filter(path: Path):
    try:
        img = Image.open(path).convert("RGB")
        img = ImageEnhance.Color(img).enhance(1.02)
        img = ImageEnhance.Contrast(img).enhance(1.03)
        img = ImageEnhance.Brightness(img).enhance(1.01)
        img.save(path)
    except:
        pass
    return path


# ----------------------------
# 4:5 Crop
# ----------------------------

def _instagram_crop(img: Image.Image) -> Image.Image:
    target_ratio = 4 / 5
    w, h = img.size
    current_ratio = w / h

    if abs(current_ratio - target_ratio) < 0.03:
        return img

    # Crop width (most common)
    new_width = int(h * target_ratio)
    if new_width < w:
        left = (w - new_width) // 2
        right = left + new_width
        return img.crop((left, 0, right, h))

    # Crop height
    new_height = int(w / target_ratio)
    top = (h - new_height) // 2
    bottom = top + new_height
    return img.crop((0, top, w, bottom))


# ----------------------------
# Deterministic variation helpers
# ----------------------------

POSE_SEQUENCE = [
    {
        "prompt": "natural portrait orientation selfie, phone slightly tilted, shoulders visible",
        "pose_key": "selfie_arm",
        "min_confidence": 0.0,
    },
    {
        "prompt": "portrait shot looking slightly away, candid style",
        "pose_key": "selfie_coffee",
        "min_confidence": 0.1,
    },
    {
        "prompt": "leaning against railing, portrait shot, natural daylight",
        "pose_key": "street_wall_lean",
        "min_confidence": 0.45,
    },
    {
        "prompt": "friend-taken portrait 4:5, standing relaxed, soft smile",
        "pose_key": "cafe_sit_waist",
        "min_confidence": 0.45,
    },
    {
        "prompt": "portrait walking shot, phone held by friend, motion in background",
        "pose_key": "street_walk_close",
        "min_confidence": 0.8,
    },
]

IMPERFECTION_SEQUENCE = [
    "slight natural grain",
    "tiny hair strands out of place",
    "soft light falloff on one side",
    "minor background blur inconsistency",
    "slight shadow unevenness",
]

ENVIRONMENT_SEQUENCE = [
    {
        "text": "include natural ambient people in background, softly blurred",
        "min_confidence": 0.0,
    },
    {
        "text": "include pedestrians and street shops behind her",
        "min_confidence": 0.45,
    },
    {
        "text": "include café interior with customers working",
        "min_confidence": 0.35,
    },
    {
        "text": "include river promenade with joggers",
        "min_confidence": 0.65,
    },
    {
        "text": "include soft traffic blur from passing cars",
        "min_confidence": 0.8,
    },
]

OUTFIT_SEQUENCE = [
    "pastel sweater with jeans",
    "cream blazer and soft top",
    "pink hoodie, hair tied casually",
    "white crop top + denim skirt",
    "athleisure set in a different color palette",
    "oversized sweater with tote bag",
]


def _load_pose_library() -> dict:
    poses_path = Path("personas/rin/poses.json")
    try:
        return json.loads(poses_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning(f"Unable to load pose library: {exc}")
        return {}


def _background_confidence(bg_refs: list[str], place: Optional[dict]) -> float:
    confidence = 0.15
    if place and place.get("keywords"):
        confidence += 0.15
    confidence += min(len(bg_refs), 3) * 0.25
    return min(confidence, 1.0)


def _cycle_text(state: VariationState, key: str, options: list[str]) -> str:
    if not options:
        return ""
    idx = state.get_index(key, len(options))
    value = options[idx]
    state.advance(key, len(options))
    return value


def _select_with_confidence(
    state: VariationState,
    key: str,
    options: list[dict],
    confidence: float,
) -> tuple[dict, bool]:
    if not options:
        return ({}, False)

    idx = state.get_index(key, len(options))
    option = options[idx]

    if confidence >= option.get("min_confidence", 0.0):
        state.advance(key, len(options))
        return option, True

    # Fallback to the safest option available without advancing the cycle.
    for candidate in options:
        if confidence >= candidate.get("min_confidence", 0.0):
            return candidate, False

    # If nothing qualifies, return the first option.
    return options[0], False


# ----------------------------
# MAIN GENERATOR
# ----------------------------

def generate_image(persona_name: str, idea: str, place: Optional[dict] = None) -> str:
    persona = json.loads(Path(f"personas/{persona_name}/persona.json").read_text())
    base_prompt = build_image_prompt(persona, idea, place)

    bg_refs = download_reference_images(
        place.get("keywords", []),
        max_images=3
    ) if place else []

    state = VariationState()
    confidence = _background_confidence(bg_refs, place)
    log.debug(f"Background confidence → {confidence:.2f} (refs={len(bg_refs)})")

    pose_option, pose_advanced = _select_with_confidence(
        state, "pose", POSE_SEQUENCE, confidence
    )
    pose = pose_option.get("prompt", "natural portrait orientation selfie, phone slightly tilted, shoulders visible")

    env_option, _ = _select_with_confidence(
        state, "environment", ENVIRONMENT_SEQUENCE, confidence
    )
    env = env_option.get(
        "text", "include natural ambient people in background, softly blurred"
    )

    imperf = _cycle_text(state, "imperfection", IMPERFECTION_SEQUENCE)
    outfit = _cycle_text(state, "outfit", OUTFIT_SEQUENCE)

    pose_library = _load_pose_library()
    pose_spec = pose_library.get(pose_option.get("pose_key", ""))
    camera_instructions = get_camera_instructions(
        pose_spec or {},
        state=state,
        pose_key=pose_option.get("pose_key"),
        advance=pose_advanced,
    )

    # Persist variation progress now that selections are finalized.
    state.save()

    full_prompt = f"""
{base_prompt}

Generate a portrait orientation photograph.
Aspect ratio: 4:5 portrait. 
It must look like a real iPhone 15 Pro photo.

STYLE REQUIREMENTS:
- Absolutely NO text, NO captions, NO words, NO numbers anywhere in the image.
- No signs, logos, or readable letters in the background.
- Skin texture must be natural, not smooth or plastic.
- Real shadows, natural lighting, handheld realism.
- Avoid dramatic or cinematic lighting.
- Avoid studio perfection. Keep it natural.

SCENE STYLE:
Pose: {pose}
Outfit: {outfit}
Background style: {env}
Small natural imperfections: {imperf}

Make it look like a real Instagram lifestyle blogger photo.
"""

    if camera_instructions:
        full_prompt += f"\nCamera direction: {camera_instructions}"

    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    persona_refs = sorted(list(REF_DIR.glob("*")))[:3]

    contents = [full_prompt]
    for p in persona_refs:
        contents.append(_upload_persona(client, p))
    for r in bg_refs:
        contents.append(_as_part(Path(r)))

    # ----------------------------
    # GEMINI REQUEST
    # ----------------------------

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents
    )

    part = next(p for p in response.parts if getattr(p, "inline_data", None))

    # PROPER PIL conversion:
    img = Image.open(io.BytesIO(part.inline_data.data))

    # ----------------------------
    # POSTPROCESS: 4:5 + resize
    # ----------------------------

    img = _instagram_crop(img)
    img = img.resize((1080, 1350), Image.LANCZOS)

    out = Path("assets/images/generated") / f"rin_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

    _apply_filter(out)
    log.info(f"Image saved → {out}")
    return str(out)
