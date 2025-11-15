# cli.py (append to the previous boot script)
import argparse
from core.logger import get_logger
from core.structure import ensure_structure
from core.database import init_db
from personas.loader import validate_persona
from core.publisher import publish_to_instagram
from utils.persona_cache import get_persona

log = get_logger("Rin")

def boot():
    log.info("Booting Rin AI Influencer Agent 🌙✨")
    ensure_structure()
    init_db()
    persona = get_persona("rin")
    validate_persona(persona)
    log.info(f"Persona loaded: {persona['display_name']} ({persona['id']})")
    log.info("System ready ✅")

def main():
    parser = argparse.ArgumentParser(description="Rin CLI")
    parser.add_argument("--publish", action="store_true", help="Publish latest unposted draft to Instagram")
    parser.add_argument("--draft-id", type=int, help="Specify a draft id to publish")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    args = parser.parse_args()

    if not any([args.publish]):
        boot()
        return

    if args.publish:
        res = publish_to_instagram(draft_id=args.draft_id, headless=not args.headed)
        if res.get("ok"):
            log.info(f"✅ Published: {res.get('detail')}")
        else:
            log.error(f"❌ Publish failed: {res.get('error')}")

if __name__ == "__main__":
    main()
