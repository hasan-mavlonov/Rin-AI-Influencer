"""
Face-only refinement pipeline for Rin AI Influencer.

Robust face detection with graceful fallback for angled / lifestyle photos.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import torch
from diffusers import StableDiffusionXLImg2ImgPipeline
from PIL import Image

from core.logger import get_logger

log = get_logger("FaceRefiner")

DEFAULT_LORA_PATH = Path(__file__).resolve().parent.parent / "rinxl_lora.safetensors"

HAAR_DIR = Path(cv2.data.haarcascades)
FRONTAL = str(HAAR_DIR / "haarcascade_frontalface_default.xml")
PROFILE = str(HAAR_DIR / "haarcascade_profileface.xml")


class FaceRefinementError(RuntimeError):
    pass


# -------------------------------------------------------
# Face detectors
# -------------------------------------------------------

@lru_cache(maxsize=1)
def _load_detectors():
    frontal = cv2.CascadeClassifier(FRONTAL)
    profile = cv2.CascadeClassifier(PROFILE)
    if frontal.empty():
        raise FaceRefinementError("Failed to load frontal Haar.")
    if profile.empty():
        log.warning("Profile Haar not available.")
    return frontal, profile


# -------------------------------------------------------
# Crop helpers
# -------------------------------------------------------

def _square_crop(cx, cy, side, img_w, img_h):
    half = side // 2
    left = max(0, cx - half)
    top = max(0, cy - half)
    right = min(img_w, cx + half)
    bottom = min(img_h, cy + half)
    return int(left), int(top), int(right), int(bottom)


# -------------------------------------------------------
# Face detection + fallback
# -------------------------------------------------------

def detect_and_crop_face(
    image: Image.Image,
    output_size: int = 640,
) -> tuple[Image.Image, tuple[int, int, int, int], float]:

    if image.mode != "RGB":
        image = image.convert("RGB")

    img_w, img_h = image.size
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

    frontal, profile = _load_detectors()

    faces = frontal.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=3,
        minSize=(80, 80),
    )

    source = "frontal"

    if len(faces) == 0 and profile:
        faces = profile.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=3,
            minSize=(80, 80),
        )
        source = "profile"

    if len(faces) > 0:
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        cx, cy = x + w // 2, y + h // 2
        side = int(max(w, h) * 1.6)
        crop = _square_crop(cx, cy, side, img_w, img_h)

        face_scale = w / float(min(img_w, img_h))


        log.info(f"Face detected via {source} Haar (scale={face_scale:.3f})")

    else:
        log.info("No Haar face found → using fallback portrait crop")

        side = int(min(img_w, img_h) * 0.55)
        cx = img_w // 2
        cy = int(img_h * 0.35)
        crop = _square_crop(cx, cy, side, img_w, img_h)

        visible_ratio = 0.18  # conservative fallback

    cropped = image.crop(crop).resize((output_size, output_size), Image.LANCZOS)

    return cropped, crop, float(face_scale)


# -------------------------------------------------------
# SDXL + LoRA
# -------------------------------------------------------

@lru_cache(maxsize=1)
def _load_sdxl_pipeline(base_model: str, lora_path: Path, device: str):
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    kwargs = {"torch_dtype": dtype, "use_safetensors": True}
    if dtype == torch.float16:
        kwargs["variant"] = "fp16"

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(base_model, **kwargs)
    pipe.load_lora_weights(str(lora_path.parent), weight_name=lora_path.name)
    pipe.fuse_lora()
    pipe.to(device)
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    pipe.set_progress_bar_config(disable=True)
    return pipe


def refine_face_with_sdxl(
    face_image: Image.Image,
    prompt: str,
    strength: float = 0.42,
    guidance_scale: float = 5.0,
    steps: int = 24,
    device: Optional[str] = None,
    base_model: str = "stabilityai/stable-diffusion-xl-base-1.0",
) -> Image.Image:

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    pipe = _load_sdxl_pipeline(base_model, DEFAULT_LORA_PATH, device)

    with torch.inference_mode():
        return pipe(
            prompt=prompt,
            image=face_image,
            strength=strength,
            guidance_scale=guidance_scale,
            num_inference_steps=steps,
        ).images[0]


# -------------------------------------------------------
# Blending
# -------------------------------------------------------

def blend_face_back(
    base_image: Image.Image,
    refined_face: Image.Image,
    crop: tuple[int, int, int, int],
    feather: int = 9,
) -> Image.Image:

    left, top, right, bottom = crop
    w, h = right - left, bottom - top

    refined = refined_face.resize((w, h), Image.LANCZOS)
    mask = Image.fromarray(
        cv2.GaussianBlur(np.full((h, w), 255, np.uint8), (0, 0), feather),
        mode="L",
    )

    result = base_image.copy()
    result.paste(refined, (left, top), mask)
    return result
