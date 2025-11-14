import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from generators.captioner import generate_caption
from generators.idea_generator import generate_idea
from generators.image_gen import generate_image
from personas.loader import load_persona
from poster.instagram_poster import post_feed

log = get_logger("PostCycle")


def run_post_cycle(persona_name: str, auto_post: bool = False, headless: bool = True):
    """
    Full pipeline: idea → 1 detailed photo → caption → (optional) Instagram post.
    Rin becomes fully autonomous here.
    """
    start = time.time()
    persona = load_persona(persona_name)
    log.info(f"🚀 Starting autonomous post cycle for {persona['display_name']}...")

    # Step 1: Generate idea & location
    idea, place = generate_idea(persona_name)
    log.info(f"🧠 Idea: {idea}")
    log.info(f"📍 Location: {place['name']} — {place['description']}")

    # Step 2: Generate single image ✅ pass `place`
    log.info("🎨 Generating image...")
    img_path = generate_image(persona_name, idea, place)
    log.info(f"🖼️ Image generated → {img_path}")

    # Step 3: Generate caption (already passes `place`, keep as is)
    log.info("📝 Generating caption...")
    caption = generate_caption(persona_name, idea, place)
    log.info(f"💬 Caption → {caption}")

    # Step 4: Post or Preview
    if auto_post:
        log.info("📲 Uploading to Instagram...")
        try:
            result = post_feed(img_path, caption, headless=headless)
            if result.get("status") == "success":
                log.info(f"✅ Posted successfully → {result}")
            else:
                log.warning(f"⚠️ Posting failed → {result}")
        except Exception as e:
            log.error(f"Instagram posting failed: {e}")
    else:
        # Save preview file (not uploaded)
        log.info("💡 Preview mode: post not uploaded automatically.")
        preview_dir = Path("assets/preview")
        preview_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        meta_path = preview_dir / f"{persona_name}_{ts}.txt"
        meta_path.write_text(
            f"Idea: {idea}\n\n"
            f"Location: {place['name']} — {place['description']}\n\n"
            f"Caption:\n{caption}\n\n"
            f"Image:\n{img_path}",
            encoding="utf-8",
        )
        log.info(f"🗂️ Preview saved → {meta_path}")

    end = time.time()
    log.info(f"✨ Cycle complete in {end - start:.2f}s.")

    return {
        "idea": idea,
        "place": place,
        "caption": caption,
        "image": img_path,
        "posted": auto_post,
    }


if __name__ == "__main__":
    # Run one full cycle
    run_post_cycle("rin", auto_post=False, headless=False)

    # To post automatically (headless Chrome):
    # run_post_cycle("rin", auto_post=True, headless=True)
