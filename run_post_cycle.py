import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from generators.captioner import generate_caption
from generators.idea_generator import generate_idea
from generators.image_gen import create_motion_clip, generate_image
from utils.persona_cache import get_persona
from poster.instagram_poster import post_feed

log = get_logger("PostCycle")


def run_post_cycle(
    persona_name: str,
    auto_post: bool = False,
    headless: bool = True,
    trigger_engagement: bool = False,
):
    """
    Full pipeline: idea → 1 detailed photo → caption → (optional) Instagram post.
    Rin becomes fully autonomous here.
    """
    start = time.time()
    persona = get_persona(persona_name)
    if not persona:
        log.error(f"Persona '{persona_name}' could not be loaded; aborting cycle.")
        return {
            "idea": None,
            "place": None,
            "caption": None,
            "image": None,
            "posted": False,
        }

    display_name = persona.get("display_name", persona_name)
    log.info(f"🚀 Starting autonomous post cycle for {display_name}...")

    # Step 1: Generate idea & location
    idea, place = generate_idea(persona_name)
    log.info(f"🧠 Idea: {idea}")
    location_name = (place or {}).get("name", "")
    location_desc = (place or {}).get("description", "")
    location_line = (
        f"{location_name} — {location_desc}" if location_desc else location_name or "Unknown"
    )
    log.info(f"📍 Location: {location_line}")

    # Step 2: Generate imagery (still + reel motion by default)
    log.info("🎨 Generating image...")
    img_path = generate_image(persona_name, idea, place)
    log.info(f"🖼️ Image generated → {img_path}")

    clip_path = create_motion_clip(img_path)
    media_path = clip_path or img_path
    media_type = "video" if clip_path else "image"
    if clip_path:
        log.info(f"🎞️ Reel-first asset prepared → {clip_path}")

    # Step 3: Generate caption (already passes `place`, keep as is)
    log.info("📝 Generating caption...")
    caption = generate_caption(persona_name, idea, place)
    log.info(f"💬 Caption → {caption}")

    # Step 4: Post or Preview
    if auto_post:
        log.info("📲 Uploading to Instagram...")
        try:
            result = post_feed(
                media_path,
                caption,
                media_type=media_type,
                cover_path=img_path if clip_path else None,
                headless=headless,
            )
            if result.get("status") == "success":
                log.info(f"✅ Posted successfully → {result}")
            else:
                log.warning(f"⚠️ Posting failed → {result}")
        except Exception as e:
            log.error(f"Instagram posting failed: {e}")
        if trigger_engagement:
            from engagement.engagement_engine import run_engagement_cycle

            now_hour = datetime.now().hour
            if 9 <= now_hour <= 22:
                log.info("💬 Triggering a light engagement burst after posting.")
                try:
                    run_engagement_cycle()
                except Exception as exc:  # noqa: BLE001
                    log.error(f"Follow-up engagement failed: {exc}")
            else:
                log.info("Engagement skipped — outside daytime window.")
    else:
        # Save preview file (not uploaded)
        log.info("💡 Preview mode: post not uploaded automatically.")
        preview_dir = Path("assets/preview")
        try:
            preview_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            meta_path = preview_dir / f"{persona_name}_{ts}.txt"
            meta_path.write_text(
                f"Idea: {idea}\n\n"
                f"Location: {location_line}\n\n"
                f"Caption:\n{caption}\n\n"
                f"Media:\n{media_path} ({media_type})",
                encoding="utf-8",
            )
            log.info(f"🗂️ Preview saved → {meta_path}")
        except OSError as exc:
            log.error(f"Failed to save preview metadata: {exc}")

    end = time.time()
    log.info(f"✨ Cycle complete in {end - start:.2f}s.")

    return {
        "idea": idea,
        "place": place,
        "caption": caption,
        "image": img_path,
        "media_path": media_path,
        "media_type": media_type,
        "posted": auto_post,
    }


if __name__ == "__main__":
    # Run one full cycle
    run_post_cycle("rin", auto_post=True, headless=True)

    # To post automatically (headless Chrome):
    # run_post_cycle("rin", auto_post=True, headless=True)
