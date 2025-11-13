import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from generators.idea_generator import generate_idea
from generators.image_gen import generate_image
from generators.captioner import generate_caption
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

    # Step 2: Generate single image  ✅ pass `place`
    log.info("🎨 Generating image...")
    img_path = generate_image(persona_name, idea, place)
    log.info(f"🖼️ Image generated → {img_path}")

    # Step 3: Generate caption (already passes `place`, keep as is)
    log.info("📝 Generating caption...")
    caption = generate_caption(persona_name, idea, place)
    log.info(f"💬 Caption → {caption}")

    ##

if __name__ == "__main__":
    # Run in preview mode first (no real upload)
    run_post_cycle("rin", auto_post=True, headless=False)

    # To post automatically:
    # run_post_cycle("rin", auto_post=True, headless=True)
