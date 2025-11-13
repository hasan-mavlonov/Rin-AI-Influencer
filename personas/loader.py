# personas/loader.py
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PERSONAS_DIR = BASE_DIR / "personas"

def load_persona(slug: str = "rin") -> dict:
    pfile = PERSONAS_DIR / slug / "persona.json"
    if not pfile.exists():
        raise FileNotFoundError(f"Persona '{slug}' not found at {pfile}")
    with pfile.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # resolve sample image paths to absolute (if present)
    samples = []
    for rel in data.get("image_style", {}).get("sample_images", []):
        ap = (PERSONAS_DIR / slug / rel).resolve()
        if ap.exists():
            samples.append(str(ap))
    data["image_style"]["sample_images_resolved"] = samples
    data["_persona_dir"] = str((PERSONAS_DIR / slug).resolve())
    data["_persona_file"] = str(pfile.resolve())
    return data

def validate_persona(data: dict) -> bool:
    required = ["id", "display_name", "prompt_templates"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"persona.json missing required fields: {missing}")
    return True

def load_recent_posts(slug: str = "rin", limit: int = 5):
    """
    Read up to 'limit' most recent post JSONs for this persona.
    Used as context for caption generation.
    """
    pdir = PERSONAS_DIR / slug / "posts"
    if not pdir.exists():
        return []
    files = sorted(pdir.glob("*.json"), reverse=True)
    recent = []
    for f in files[:limit]:
        try:
            with f.open("r", encoding="utf-8") as fp:
                recent.append(json.load(fp))
        except Exception:
            continue
    return recent

if __name__ == "__main__":
    p = load_persona("rin")
    validate_persona(p)
    print(f"Loaded persona: {p['display_name']} ({p['id']})")
    if p.get("image_style", {}).get("sample_images_resolved"):
        print("Resolved samples:", *p["image_style"]["sample_images_resolved"], sep="\n - ")
