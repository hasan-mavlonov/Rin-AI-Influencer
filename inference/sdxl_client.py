from __future__ import annotations

import base64
import io
from typing import Callable

import requests
from PIL import Image

from core.config import Config
from core.logger import get_logger

log = get_logger("SDXLClient")


class SDXLClientError(RuntimeError):
    """Raised when SDXL inference cannot be completed."""


_DEF_TIMEOUT_SECONDS = 90


def _decode_image_bytes(response: requests.Response) -> bytes:
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type.startswith("application/json"):
        data = response.json()
        encoded = data.get("image") or data.get("data")
        if not encoded:
            raise SDXLClientError("SDXL response missing image payload")
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise SDXLClientError("Failed to decode base64 image from SDXL") from exc

    return response.content


def generate_sdxl_image(
    *,
    prompt: str,
    negative_prompt: str | None,
    steps: int,
    guidance: float,
    save_image: Callable[[Image.Image], str],
) -> str:
    """Send a text prompt to the SDXL inference server and return the saved path."""

    endpoint = Config.SDXL_ENDPOINT
    if not endpoint:
        raise SDXLClientError("SDXL endpoint is not configured.")

    headers = {"Content-Type": "application/json"}
    if Config.SDXL_API_KEY:
        headers["Authorization"] = f"Bearer {Config.SDXL_API_KEY}"

    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "guidance": guidance,
    }

    timeout = Config.SDXL_TIMEOUT or _DEF_TIMEOUT_SECONDS

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:  # noqa: BLE001 - requests exceptions vary
        raise SDXLClientError(f"SDXL request failed: {exc}") from exc

    if response.status_code >= 400:
        raise SDXLClientError(
            f"SDXL server returned {response.status_code}: {response.text.strip()}"
        )

    image_bytes = _decode_image_bytes(response)

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - PIL can throw many errors
        raise SDXLClientError("Unable to parse SDXL image response") from exc

    return save_image(image)
