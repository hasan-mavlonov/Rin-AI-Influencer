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

    # Crop width
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
# Deterministic variation helpers (NEW VERSION)
# ----------------------------

DEFAULT_CATEGORY = "selfie_morning"

CATEGORY_POSES = {
    "selfie_morning": [
        {
            "prompt": "relaxed morning selfie, soft natural light, shoulders visible",
            "pose_key": "selfie_arm",
            "min_confidence": 0.0,
        },
        {
            "prompt": "coffee-in-hand selfie, cozy vibe, candid smile",
            "pose_key": "selfie_coffee",
            "min_confidence": 0.15,
        },
    ],
    "selfie_gym": [
        {
            "prompt": "gym mirror selfie, toned posture, confident expression",
            "pose_key": "selfie_gym",
            "min_confidence": 0.0,
        },
        {
            "prompt": "post-workout mirror selfie, relaxed smile",
            "pose_key": "selfie_mirror",
            "min_confidence": 0.2,
        },
    ],
    "selfie_mirror": [
        {
            "prompt": "elevator mirror selfie, waist-up framing",
            "pose_key": "selfie_mirror",
            "min_confidence": 0.0,
        },
        {
            "prompt": "close mirror selfie, playful tilt",
            "pose_key": "selfie_arm",
            "min_confidence": 0.1,
        },
    ],
    "street_casual": [
        {
            "prompt": "friend-taken waist-up street portrait, relaxed smile",
            "pose_key": "street_wall_lean",
            "min_confidence": 0.2,
        },
        {
            "prompt": "street walking candid, mid-step motion, joyful",
            "pose_key": "street_walk_close",
            "min_confidence": 0.55,
        },
        {
            "prompt": "handheld selfie outside, city behind",
            "pose_key": "selfie_arm",
            "min_confidence": 0.0,
        },
    ],
    "cozy_night": [
        {
            "prompt": "cozy indoor selfie, soft evening light",
            "pose_key": "selfie_bed",
            "min_confidence": 0.0,
        },
        {
            "prompt": "close-up coffee table selfie, warm lamp glow",
            "pose_key": "selfie_coffee",
            "min_confidence": 0.0,
        },
    ],
}

CATEGORY_ENVIRONMENTS = {
    "selfie_morning": [
        {
            "text": "warm daylight from the side, hints of {location} in soft focus",
            "min_confidence": 0.0,
        },
        {
            "text": "morning café interior near {location}, blurred patrons behind",
            "min_confidence": 0.35,
        },
    ],
    "selfie_gym": [
        {
            "text": "mirrored gym interior at {location}, equipment softly blurred",
            "min_confidence": 0.0,
        },
        {
            "text": "fitness studio lighting with cool reflections and gym signage",
            "min_confidence": 0.45,
        },
    ],
    "selfie_mirror": [
        {
            "text": "mirror reflections showing outfit and {location} details",
            "min_confidence": 0.0,
        },
        {
            "text": "elevator interior with city lights reflected",
            "min_confidence": 0.35,
        },
    ],
    "street_casual": [
        {
            "text": "tree-lined street near {location}, boutique storefronts blurred",
            "min_confidence": 0.0,
        },
        {
            "text": "dynamic Shanghai street energy at {location}, passersby softly blurred",
            "min_confidence": 0.55,
        },
    ],
    "cozy_night": [
        {
            "text": "warm desk lamp glow, laptop or books in background, {location} vibes",
            "min_confidence": 0.0,
        },
        {
            "text": "soft LED lighting with city night outside window",
            "min_confidence": 0.45,
        },
    ],
}

CATEGORY_OUTFITS = {
    "selfie_morning": [
        "pastel cropped cardigan and high-waist jeans",
        "light knit sweater with pleated skirt",
        "casual athleisure set with warm-up jacket",
    ],
    "selfie_gym": [
        "matching sports bra and leggings, subtle sheen",
        "two-tone athletic set with zip-up hoodie",
        "black and blush gym set with towel over shoulder",
    ],
    "selfie_mirror": [
        "sleek pastel blazer over fitted top",
        "monochrome outfit with statement boots",
        "oversized hoodie with mini skirt",
    ],
    "street_casual": [
        "cream blazer layered over crop top and denim",
        "flowy blouse with tailored shorts and tote bag",
        "techwear windbreaker with pleated skirt",
    ],
    "cozy_night": [
        "soft loungewear set with fuzzy socks",
        "oversized sweater dress with blanket throw",
        "silky pajama top with messy bun",
    ],
}

IMPERFECTION_SEQUENCE = [
    "slight natural grain",
    "tiny hair strands out of place",
    "soft light falloff on one side",
    "minor background blur inconsistency",
    "slight shadow unevenness",
]


# ----------------------------
# Selection logic
# ----------------------------

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

    for candidate in options:
        if confidence >= candidate.get("min_confidence", 0.0):
            return candidate, False

    return options[0], False


def _infer_category(place: Optional[dict], idea: str) -> str:
    if place:
        shot_category = place.get("shot_category")
        if shot_category in CATEGORY_POSES:
            return shot_category

    idea_lower = idea.lower()
    keywords = (place or {}).get("keywords", [])
    joined = " ".join(keywords).lower()

    if any(k in idea_lower or k in joined for k in ["gym", "workout", "leg day", "training"]):
        return "selfie_gym"
    if any(k in idea_lower or k in joined for k in ["mirror", "elevator"]):
        return "selfie_mirror"
    if any(k in idea_lower or k in joined for k in ["night", "late", "evening", "cozy", "sleep"]):
        return "cozy_night"
    if any(k in idea_lower or k in joined for k in ["street", "walk", "wander", "city", "outside"]):
        return "street_casual"

    return DEFAULT_CATEGORY


def _resolve_pose(state: VariationState, category: str, confidence: float):
    options = CATEGORY_POSES.get(category) or CATEGORY_POSES[DEFAULT_CATEGORY]
    key = f"pose:{category}"
    return _select_with_confidence(state, key, options, confidence)


def _resolve_environment(state: VariationState, category: str, confidence: float, place: Optional[dict]):
    options = CATEGORY_ENVIRONMENTS.get(category) or CATEGORY_ENVIRONMENTS[DEFAULT_CATEGORY]
    env_option, _ = _select_with_confidence(
        state, f"environment:{category}", options, confidence
    )
    location = (place or {}).get("name") or "the location"
    text = env_option.get("text", "")
    return text.format(location=location)


def _resolve_outfit(state: VariationState, category: str) -> str:
    outfits = CATEGORY_OUTFITS.get(category) or CATEGORY_OUTFITS[DEFAULT_CATEGORY]
    return _cycle_text(state, f"outfit:{category}", outfits)


def _score_reference(path: Path) -> int:
    try:
        with Image.open(path) as img:
            width, height = img.size
        return width * height
    except Exception:
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0


def _top_reference_images(directory: Path, limit: int = 3) -> list[Path]:
    refs = []
    for p in directory.glob("*"):
        if p.is_file():
            refs.append((p, _score_reference(p)))

    refs.sort(key=lambda item: item[1], reverse=True)
    return [p for p, _ in refs[:limit]]


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

    category = _infer_category(place, idea)
    log.debug(f"Pose category → {category}")

    pose_option, pose_advanced = _resolve_pose(state, category, confidence)
    pose = pose_option.get(
        "prompt",
        "natural portrait orientation selfie, phone slightly tilted, shoulders visible",
    )

    env = _resolve_environment(state, category, confidence, place)
    imperf = _cycle_text(state, "imperfection", IMPERFECTION_SEQUENCE)
    outfit = _resolve_outfit(state, category)

    pose_library = _load_pose_library()
    pose_spec = pose_library.get(pose_option.get("pose_key", ""))
    camera_instructions = get_camera_instructions(
        pose_spec or {},
        state=state,
        pose_key=pose_option.get("pose_key"),
        advance=pose_advanced,
    )

    # save variation state
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
"""

    if place:
        location_name = place.get('name', '')
        location_desc = place.get('description', '')
        location_line = location_name
        if location_desc:
            location_line += f" — {location_desc}"
        full_prompt += f"\nLocation inspiration: {location_line}"

    full_prompt += "\nMake it look like a real Instagram lifestyle blogger photo."

    if camera_instructions:
        full_prompt += f"\nCamera direction: {camera_instructions}"

    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    persona_refs = _top_reference_images(REF_DIR, limit=3)

    contents = [full_prompt]
    for p in persona_refs:
        contents.append(_upload_persona(client, p))
    for r in bg_refs:
        contents.append(_as_part(Path(r)))

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents
    )

    part = next(p for p in response.parts if getattr(p, "inline_data", None))
    img = Image.open(io.BytesIO(part.inline_data.data))

    img = _instagram_crop(img)
    img = img.resize((1080, 1350), Image.LANCZOS)

    out = Path("assets/images/generated") / f"rin_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

    _apply_filter(out)
    log.info(f"Image saved → {out}")
    return str(out)
