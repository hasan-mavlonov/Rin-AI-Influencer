"""Face-only refinement pipeline for Rin AI Influencer.

This module keeps Google Gemini as the source of the full frame and only
applies SDXL + LoRA to a cropped facial region. The SDXL pipeline never
receives the full image, which prevents the instability issues observed
with whole-frame img2img runs on serverless hardware.
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
FACE_CASCADE_PATH = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")


class FaceRefinementError(RuntimeError):
    """Raised when the face-only refinement pipeline cannot proceed."""


@lru_cache(maxsize=1)
def _load_face_detector() -> cv2.CascadeClassifier:
    """Load a Haar cascade face detector once.

    Haar cascades are lightweight and deterministic, making them reliable for
    consistently finding the primary face that needs refinement.
    """

    detector = cv2.CascadeClassifier(FACE_CASCADE_PATH)
    if detector.empty():
        raise FaceRefinementError("Failed to load Haar cascade for face detection.")
    return detector


def _build_square_box(
    x: int, y: int, w: int, h: int, img_w: int, img_h: int, padding_ratio: float
) -> Tuple[int, int, int, int]:
    """Return a padded, square crop around the detected face.

    Padding ensures hairline and jaw remain inside the crop so LoRA has enough
    context to render stable facial boundaries.
    """

    side = int(max(w, h) * (1 + 2 * padding_ratio))
    cx, cy = x + w // 2, y + h // 2
    half = side // 2

    left = max(0, cx - half)
    top = max(0, cy - half)
    right = min(img_w, cx + half)
    bottom = min(img_h, cy + half)

    # Adjust to keep the box square when touching image borders
    box_w, box_h = right - left, bottom - top
    if box_w != box_h:
        if box_w < box_h:
            deficit = box_h - box_w
            left = max(0, left - deficit // 2)
            right = min(img_w, right + deficit - deficit // 2)
        else:
            deficit = box_w - box_h
            top = max(0, top - deficit // 2)
            bottom = min(img_h, bottom + deficit - deficit // 2)

    return int(left), int(top), int(right), int(bottom)


def detect_and_crop_face(
    image: Image.Image, padding_ratio: float = 0.25, output_size: int = 640
) -> tuple[Image.Image, tuple[int, int, int, int], float]:
    """Detect and crop a square face region with padding.

    The SDXL pipeline must never see the full image; this function extracts a
    face-only crop while preserving enough surrounding context for realistic
    blending after refinement.
    """

    if image.mode != "RGB":
        image = image.convert("RGB")

    img_array = np.array(image)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    detector = _load_face_detector()
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        raise FaceRefinementError("No face detected in the provided image.")

    # Select the largest detected face to align with the main subject.
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    img_w, img_h = image.size
    visible_ratio = float((w * h) / float(img_w * img_h))
    left, top, right, bottom = _build_square_box(x, y, w, h, img_w, img_h, padding_ratio)

    cropped = image.crop((left, top, right, bottom))
    resized_crop = cropped.resize((output_size, output_size), Image.LANCZOS)
    log.debug(
        "Face crop prepared",
        extra={"box": (left, top, right, bottom), "output_size": output_size},
    )
    return resized_crop, (left, top, right, bottom), visible_ratio


@lru_cache(maxsize=1)
def _load_sdxl_pipeline(base_model: str, lora_path: Path, device: str):
    """Load SDXL img2img with the RinXL LoRA attached.

    The pipeline is cached to avoid reloading weights between calls. It only
    processes cropped faces to prevent the instability seen when refining full
    images.
    """

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    kwargs = {"torch_dtype": dtype, "use_safetensors": True}
    if dtype == torch.float16:
        kwargs["variant"] = "fp16"

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(base_model, **kwargs)
    pipe.load_lora_weights(str(lora_path.parent), weight_name=lora_path.name)
    pipe.fuse_lora()
    pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    pipe.enable_vae_slicing()
    pipe.enable_attention_slicing()
    return pipe


def refine_face_with_sdxl(
    face_image: Image.Image,
    prompt: str,
    lora_path: Path = DEFAULT_LORA_PATH,
    strength: float = 0.45,
    num_inference_steps: int = 24,
    guidance_scale: float = 5.0,
    seed: Optional[int] = None,
    device: Optional[str] = None,
    base_model: str = "stabilityai/stable-diffusion-xl-base-1.0",
) -> Image.Image:
    """Refine a face crop with SDXL and RinXL LoRA only.

    Args:
        face_image: The square face crop produced by ``detect_and_crop_face``.
        prompt: Text prompt for SDXL that preserves the persona and pose.
        lora_path: Path to ``rinxl_lora.safetensors``. Never applied to full images.
        strength: Img2img strength (0.35–0.55 recommended).
        num_inference_steps: Diffusion steps (20–30 recommended).
        guidance_scale: Classifier-free guidance (4–6 recommended).
        seed: Optional seed for deterministic output.
        device: Optional torch device. Defaults to GPU when available.
        base_model: SDXL base model identifier. Do not replace SDXL.
    """

    print("[FaceRefiner] Face refinement started")

    if face_image.size[0] != face_image.size[1]:
        raise FaceRefinementError("Face image must be square before refinement.")

    # Clamp hyperparameters to the safe ranges requested for face-only refinement.
    strength = float(np.clip(strength, 0.35, 0.55))
    num_inference_steps = int(np.clip(num_inference_steps, 20, 30))
    guidance_scale = float(np.clip(guidance_scale, 4.0, 6.0))

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    generator = torch.Generator(device=device)
    if seed is not None:
        generator = generator.manual_seed(seed)

    torch.backends.cudnn.benchmark = False
    pipe = _load_sdxl_pipeline(base_model, lora_path, device)

    with torch.inference_mode():
        result = pipe(
            prompt=prompt,
            image=face_image,
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        ).images[0]

    return result


def _feather_mask(width: int, height: int, feather: int) -> Image.Image:
    mask = np.full((height, width), 255, dtype=np.uint8)
    if feather > 0:
        sigma = max(1, feather)
        mask = cv2.GaussianBlur(mask, ksize=(0, 0), sigmaX=sigma, sigmaY=sigma)
    return Image.fromarray(mask, mode="L")


def blend_face_back(
    base_image: Image.Image,
    refined_face: Image.Image,
    crop_region: tuple[int, int, int, int],
    feather: int = 9,
) -> Image.Image:
    """Blend the refined face back into the Gemini image.

    Alpha blending preserves the original background, lighting, and pose while
    swapping only the refined facial pixels.
    """

    left, top, right, bottom = crop_region
    target_w, target_h = right - left, bottom - top

    resized_face = refined_face.resize((target_w, target_h), Image.LANCZOS)
    mask = _feather_mask(target_w, target_h, feather)

    composite = base_image.copy()
    composite.paste(resized_face, (left, top), mask)
    return composite


__all__ = [
    "detect_and_crop_face",
    "refine_face_with_sdxl",
    "blend_face_back",
    "FaceRefinementError",
]
