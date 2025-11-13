# generators/image_gen.py

import os, time, json, random
from pathlib import Path
from PIL import Image, ImageEnhance
from typing import Optional
from google import genai

from core.config import Config
from core.logger import get_logger
from generators.prompt_manager import build_image_prompt
from generators.photo_fetcher import download_reference_images

log = get_logger("ImageGen")

REF_DIR = Path("personas/rin/examples")


# ----------------------------
# HELPERS
# ----------------------------
from google.genai.types import Part

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



def _apply_filter(path: Path):
    try:
        img = Image.open(path).convert("RGB")
        img = ImageEnhance.Color(img).enhance(0.98)
        img = ImageEnhance.Contrast(img).enhance(1.02)
        img.save(path)
    except:
        pass
    return path


def _pick_pose():
    """Much more varied blogger-style poses"""
    poses = [
        # SELFIE VARIANTS
        "arm-length selfie, slightly tilted phone angle, face + shoulders in frame",
        "front camera selfie with hair slightly messy from wind",
        "seated selfie, casual, phone slightly below eye level",
        "walking selfie with motion blur on background",
        "mirror selfie but HAND NOT covering face, phone partially blocking cheek",

        # FRIEND SHOT CLOSE
        "friend-taken candid from 1.5 meters, waist-up, natural walk",
        "friend-taken portrait, standing relaxed, one hand fixing hair",
        "friend shot from low angle but subtle (not dramatic), 2 meters",
        "leaning on railing, friend shot, soft smile",
        "looking slightly away from camera, candid moment",
    ]
    return random.choice(poses)


def _imperfections():
    """Real Instagram bloggers ALWAYS have imperfections."""
    imperfections = [
        "slight hand shake",
        "soft natural grain",
        "tiny flyaway hair strands",
        "subtle uneven lighting on face",
        "slight blur on one edge",
        "minor color noise from indoor lights",
    ]
    return random.choice(imperfections)


def _environment_variation():
    """Avoid empty-looking fake rooms."""
    env = [
        "include people naturally in background, slightly blurred",
        "include pedestrians walking behind her",
        "include 1–2 gym visitors casually in background",
        "include street shops and signs with real Chinese text",
        "include café customers working on laptops",
        "include cars passing softly blurred",
        "include joggers by the river in far background"
    ]
    return random.choice(env)


def _clothing_variation():
    """Force Rin to not always wear pastel top + leggings."""
    outfits = [
        "soft pastel sweater with jeans",
        "cream blazer over simple top",
        "pink hoodie + ponytail casual look",
        "white crop top + denim skirt",
        "athleisure set but different color palette",
        "oversized knitted sweater with tote bag",
        "casual streetwear jacket with slim jeans",
    ]
    return random.choice(outfits)


# ----------------------------
# MAIN GENERATOR
# ----------------------------

def generate_image(persona_name: str, idea: str, place: Optional[dict] = None) -> str:
    persona = json.loads(Path(f"personas/{persona_name}/persona.json").read_text())
    base_prompt = build_image_prompt(persona, idea, place)

    is_selfie = random.random() < 0.75  # Reduce selfie dominance a bit

    # always allow referencing real background
    bg_refs = download_reference_images(
        place.get("keywords", []),
        max_images=3
    ) if place else []

    # extra realism signals
    pose = _pick_pose()
    imperf = _imperfections()
    env = _environment_variation()
    outfit = _clothing_variation()

    camera = (
        "iPhone 15 Pro front camera, close framing, strong natural realism."
        if is_selfie else
        "iPhone 15 Pro rear camera, handheld by friend at 1.5–2 meters."
    )

    full_prompt = f"""
{base_prompt}

Camera: {camera}
Pose: {pose}
Outfit variation: {outfit}

Realism rules:
- MUST look like a real human photo.
- Skin texture visible, no plastic smoothing.
- {imperf}
- {env}
- Real shadows, real reflections, correct perspective.
- DO NOT make empty rooms.
- DO NOT use perfect studio lighting.
- DO NOT use cinematic vibes.
- DO NOT make symmetrical composition.
- Color grading must be natural iPhone look.

The background MUST match the real-world location {place.get("name")} from {place.get("keywords")}.
"""

    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    # Upload persona reference images
    persona_refs = sorted(list(REF_DIR.glob("*")))[:3]
    # Build parts for Gemini
    contents = [full_prompt]

    # 1. PERSONA grounding ALWAYS FIRST
    for p in persona_refs:
        contents.append(_upload_persona(client, p))

    # 2. BACKGROUND grounding AFTER
    for r in bg_refs:
        contents.append(_as_part(Path(r)))

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents
    )

    part = next(p for p in response.parts if getattr(p, "inline_data", None))
    img = part.as_image()

    out = Path("assets/images/generated") / f"rin_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

    _apply_filter(out)
    log.info(f"Image saved → {out}")
    return str(out)
