# core/composer.py
import json
from datetime import datetime
from pathlib import Path
from core.logger import get_logger
from core.database import get_session
from models import PostDraft
from generators.captioner import generate_caption
from generators.image_gen import generate_image
from generators.idea_generator import generate_idea

log = get_logger("Composer")

from generators.photo_fetcher import download_reference_images
from generators.idea_generator import generate_idea

def create_realworld_post(persona_name: str):
    # Step 1: Idea + location
    idea, place = generate_idea(persona_name)

    # Step 2: Download real photos
    refs = download_reference_images(place["keywords"], max_images=3)

    # Step 3: Caption
    caption = generate_caption(persona_name, idea, place)

    # Step 4: Generate image (Gemini)
    image_path = generate_image(persona_name, idea)

    # Step 5: Save post
    with get_session() as session:
        # idea might be a tuple (idea_text, location_dict)
        if isinstance(idea, tuple):
            idea_text, place = idea
        else:
            idea_text, place = idea, {}

        post = PostDraft(
            idea=idea_text,
            image_path=image_path,
            caption=caption,
            created_at=datetime.utcnow(),
            posted=False
        )

        session.add(post)
        session.commit()
        session.refresh(post)

    post_json_path = Path(f"personas/{persona_name}/posts/{post.id}_{idea.replace(' ', '_')}.json")
    post_json_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "idea": idea,
        "location": place,
        "refs": refs,
        "caption": caption,
        "image_path": image_path
    }, open(post_json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    log.info(f"✅ Rin’s real-world post saved → {post_json_path}")
    return post_json_path

def create_post_draft(persona_name: str, idea: str | None = None, existing_image: str | None = None) -> dict:
    """
    Generates a new post draft — idea + caption + image — and stores it.
    If no idea is provided, Rin decides her own theme automatically.
    If `existing_image` is provided, skips image generation.
    """
    # Let Rin decide what she wants to express if no idea is passed
    if isinstance(idea, tuple):
        idea_text, place = idea
        log.info(f"🧠 Rin’s idea: {idea_text}")
        log.info(f"📍 Location: {place.get('name')}")
    else:
        idea_text, place = idea, {}

    if not idea:
        idea = generate_idea(persona_name)
        log.info(f"🧠 Rin decided to post about: {idea}")
    else:
        log.info(f"Creating new post draft for user-specified idea: '{idea}'")

    # 1. Generate caption using her voice
    caption = generate_caption(persona_name, idea)

    # 2. Use existing image if provided, otherwise generate new
    if existing_image:
        image_path = existing_image
        log.warning(f"[Manual Mode] Using existing image → {image_path}")
    else:
        log.info("🎨 Generating new image based on Rin’s aesthetic and mood...")
        image_path = generate_image(persona_name, idea)

    # 3. Save to database
    with get_session() as session:
        post = PostDraft(
            idea=idea,
            image_path=image_path,
            caption=caption,
            created_at=datetime.utcnow(),
            posted=False
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        log.info(f"💾 Draft saved in DB with ID {post.id}")

    # 4. Save JSON copy to /personas/{persona_name}/posts/
    posts_dir = Path(f"personas/{persona_name}/posts")
    posts_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "_".join(idea.split()).replace("/", "_")
    post_json_path = posts_dir / f"{post.id}_{safe_name}.json"

    post_data = {
        "id": post.id,
        "persona": persona_name,
        "idea": idea,
        "caption": caption,
        "image_path": image_path,
        "created_at": post.created_at.isoformat(),
        "status": "draft"
    }
    with open(post_json_path, "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=4)

    log.info(f"📝 Draft saved as JSON → {post_json_path}")
    return post_data


if __name__ == "__main__":
    """
    Run Rin’s autonomous content creation flow.
    - If you want her to think for herself: just run this script directly.
    - If you want to reuse an existing image, set existing_img below.
    """
    existing_img = None  # e.g. "assets/images/generated/mock_pictures/mock_1762760932.png"
    data = create_post_draft("rin", existing_image=existing_img)
    print(json.dumps(data, indent=4, ensure_ascii=False))
