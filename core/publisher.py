# core/publisher.py
from pathlib import Path
from datetime import datetime, timezone
from sqlmodel import select
from core.logger import get_logger
from core.database import get_session
from models import PostDraft, PostHistory
from poster.instagram_poster import comment_on_media, ensure_logged_in, post_feed

log = get_logger("Publisher")

def _get_draft(draft_id: int | None) -> PostDraft:
    with get_session() as s:
        if draft_id is not None:
            d = s.get(PostDraft, draft_id)
            if not d:
                raise ValueError(f"Draft {draft_id} not found.")
            return d
        # else: latest unposted draft
        stmt = select(PostDraft).where(PostDraft.posted == False).order_by(PostDraft.created_at.desc())
        d = s.exec(stmt).first()
        if not d:
            raise ValueError("No unposted drafts available.")
        return d

def publish_to_instagram(draft_id: int | None = None, headless: bool = True) -> dict:
    draft = _get_draft(draft_id)
    if not draft.image_path or not Path(draft.image_path).exists():
        raise FileNotFoundError(f"Draft image is missing: {draft.image_path}")

    log.info(f"Preparing to post draft #{draft.id}: '{draft.idea}'")
    ensure_logged_in(headless=headless)

    media_type = "video" if Path(draft.image_path).suffix.lower() in {".mp4", ".mov"} else "image"
    resp = post_feed(
        draft.image_path,
        draft.caption or "",
        media_type=media_type,
        headless=headless,
    )
    log.info(f"Instagram response: {resp}")

    if resp.get("status") == "success":
        with get_session() as s:
            db_draft = s.get(PostDraft, draft.id)
            db_draft.posted = True
            s.add(db_draft)
            hist = PostHistory(
                draft_id=draft.id,
                instagram_post_id=resp.get("detail", "posted"),
                posted_at=datetime.now(timezone.utc),
                likes=0,
                comments=0,
                followers_at_post=0
            )
            s.add(hist)
            s.commit()
        return {"ok": True, "detail": resp.get("detail")}
    else:
        return {"ok": False, "error": resp.get("error", "Unknown error")}


def publish_comment(media_id: str, text: str) -> dict:
    """Lightweight helper to post a comment through the Graph API."""

    ensure_logged_in()
    try:
        resp = comment_on_media(media_id, text)
    except Exception as exc:  # noqa: BLE001 - surface cleanly to CLI users.
        log.error(f"Failed to publish comment: {exc}")
        return {"ok": False, "error": str(exc)}

    return {"ok": resp.get("status") == "success", "comment_id": resp.get("comment_id")}
