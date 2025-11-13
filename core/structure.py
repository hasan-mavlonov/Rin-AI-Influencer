# core/structure.py
from pathlib import Path
from core.logger import get_logger

log = get_logger("Structure")

def ensure_structure():
    base = Path(__file__).resolve().parent.parent
    needed = [
        "assets/images",
        "logs",
        "personas/rin/posts",
        "personas/rin/examples"
    ]
    for sub in needed:
        path = base / sub
        path.mkdir(parents=True, exist_ok=True)
        log.info(f"Checked {sub}")

if __name__ == "__main__":
    ensure_structure()
