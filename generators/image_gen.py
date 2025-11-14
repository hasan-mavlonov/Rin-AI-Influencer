import os, time, json, random, io
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
# Aesthetic randomization
# ----------------------------

def _pick_pose():
    poses = [
        "natural portrait orientation selfie, phone slightly tilted, shoulders visible",
        "friend-taken portrait 4:5, standing relaxed, soft smile",
        "portrait walking shot, phone held by friend, motion in background",
        "leaning against railing, portrait shot, natural daylight",
        "portrait shot looking slightly away, candid style"
    ]
    return random.choice(poses)


def _imperfections():
    imperfections = [
        "slight natural grain",
        "tiny hair strands out of place",
        "soft light falloff on one side",
        "minor background blur inconsistency",
        "slight shadow unevenness"
    ]
    return random.choice(imperfections)


def _environment_variation():
    env = [
        "include natural ambient people in background, softly blurred",
        "include pedestrians and street shops behind her",
        "include café interior with customers working",
        "include river promenade with joggers",
        "include soft traffic blur from passing cars"
    ]
    return random.choice(env)


def _clothing_variation():
    outfits = [
        "pastel sweater with jeans",
        "cream blazer and soft top",
        "pink hoodie, hair tied casually",
        "white crop top + denim skirt",
        "athleisure set in a different color palette",
        "oversized sweater with tote bag"
    ]
    return random.choice(outfits)


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

    pose = _pick_pose()
    imperf = _imperfections()
    env = _environment_variation()
    outfit = _clothing_variation()

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
