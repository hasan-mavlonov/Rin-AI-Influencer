"""Instagram posting helpers that rely on the Instagram Graph API instead of browser automation."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Any

import requests

from core.config import Config
from core.logger import get_logger

log = get_logger("IGPoster")

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class InstagramAPIError(RuntimeError):
    """Raised when the Instagram Graph API responds with an error payload."""


def _credentials() -> tuple[str, str]:
    access_token = Config.INSTAGRAM_ACCESS_TOKEN
    account_id = Config.INSTAGRAM_BUSINESS_ACCOUNT_ID
    if not access_token or not account_id:
        raise RuntimeError(
            "Missing Instagram Graph API credentials. "
            "Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID in your .env file."
        )
    return access_token, account_id


def ensure_logged_in(headless: bool = True) -> None:  # noqa: ARG001 (API flow doesn't use browser)
    """Kept for backwards compatibility with the old browser poster.

    The Graph API does not require a manual login, but we still verify credentials early so we can
    surface actionable configuration errors before attempting to post.
    """

    try:
        _credentials()
        log.info("Graph API credentials detected – ready to publish without browser automation.")
    except RuntimeError as exc:
        log.error(str(exc))
        raise


def _raise_for_response(resp: requests.Response) -> None:
    try:
        data = resp.json()
    except ValueError:
        data = {"error": {"message": resp.text or "Unknown error"}}

    if resp.status_code >= 400 or "error" in data:
        error = data.get("error", {})
        message = error.get("message", "Unknown Instagram Graph API error")
        code = error.get("code")
        raise InstagramAPIError(f"{message} (code={code})")


def _create_media_container(image_path: Path, caption: str, *, access_token: str, account_id: str) -> str:
    endpoint = f"{GRAPH_API_BASE}/{account_id}/media"
    with image_path.open("rb") as fp:
        files = {"image_file": fp}
        data = {
            "caption": caption,
            "access_token": access_token,
        }
        log.info("Uploading image bytes to Instagram Graph API...")
        resp = requests.post(endpoint, data=data, files=files, timeout=120)
    _raise_for_response(resp)
    media_id = resp.json()["id"]
    log.info(f"✅ Media container created: {media_id}")
    return media_id


def _publish_media(media_id: str, *, access_token: str, account_id: str) -> str:
    endpoint = f"{GRAPH_API_BASE}/{account_id}/media_publish"
    data = {
        "creation_id": media_id,
        "access_token": access_token,
    }
    resp = requests.post(endpoint, data=data, timeout=60)
    _raise_for_response(resp)
    publish_id = resp.json()["id"]
    log.info(f"🚀 Publish job triggered: {publish_id}")
    return publish_id


def _poll_status(media_id: str, *, access_token: str) -> str:
    endpoint = f"{GRAPH_API_BASE}/{media_id}"
    params = {
        "fields": "status_code,status",
        "access_token": access_token,
    }
    for attempt in range(15):
        resp = requests.get(endpoint, params=params, timeout=30)
        _raise_for_response(resp)
        data = resp.json()
        status_code = data.get("status_code") or data.get("status")
        if status_code in {"FINISHED", "FINISHED_SUCCESS"}:
            return "success"
        if status_code in {"ERROR", "ERROR_UNKNOWN", "FAILED"}:
            raise InstagramAPIError(f"Media container failed to process (status={status_code}).")
        time.sleep(2 + attempt * 0.5)
    log.warning("Timed out waiting for Instagram to finish processing media container.")
    return "pending"


def post_feed(image_path: str, caption: str, headless: bool = True) -> Dict[str, Any]:  # noqa: ARG001
    """Publish a photo to Instagram using the official Graph API.

    Args:
        image_path: Local filesystem path to the image to upload.
        caption: Text caption for the post.
        headless: Preserved for backwards compatibility; ignored by the API flow.

    Returns:
        Dictionary describing whether the publish attempt succeeded.
    """

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    access_token, account_id = _credentials()

    try:
        media_id = _create_media_container(path, caption, access_token=access_token, account_id=account_id)
        publish_id = _publish_media(media_id, access_token=access_token, account_id=account_id)
        status = _poll_status(media_id, access_token=access_token)
    except InstagramAPIError as exc:
        log.error(str(exc))
        return {"status": "error", "error": str(exc)}
    except requests.RequestException as exc:
        log.error(f"Network error talking to Instagram Graph API: {exc}")
        return {"status": "error", "error": "Network error communicating with Instagram."}

    detail = "Posted to feed successfully." if status == "success" else "Publish pending confirmation."
    return {"status": status, "detail": detail, "publish_id": publish_id, "creation_id": media_id}


if __name__ == "__main__":
    ensure_logged_in()
    print("Ready to post via Instagram Graph API.")
