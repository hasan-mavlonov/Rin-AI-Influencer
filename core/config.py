# core/config.py
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


class Config:
    # External APIs
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

    # Instagram Graph API credentials
    INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

    # Database
    DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR}/rin.db")

    # General
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    BASE_DIR = BASE_DIR


if __name__ == "__main__":
    # Sanity check
    print("Config loaded from:", ENV_PATH)
    print("Database URL:", Config.DB_URL)
