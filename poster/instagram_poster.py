import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from core.logger import get_logger
from core.config import Config

log = get_logger("IGPoster")

INSTAGRAM_URL = "https://www.instagram.com/"
STATE_DIR = Path(".auth")
STATE_PATH = STATE_DIR / "instagram_state.json"


def _proxy_config() -> Optional[Dict[str, Any]]:
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        return {"server": proxy}
    return None


def _ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _login_if_needed(page) -> None:
    username = Config.INSTAGRAM_USERNAME
    password = Config.INSTAGRAM_PASSWORD
    if not username or not password:
        raise RuntimeError("Missing INSTAGRAM_USERNAME or INSTAGRAM_PASSWORD in .env")

    log.info("Checking if already logged in...")
    try:
        if page.locator("svg[aria-label='Home']").first.is_visible(timeout=3000) \
           or page.locator("input[placeholder*='Search']").first.is_visible(timeout=3000) \
           or "stories" in page.content():
            log.info("Already logged in (session detected).")
            return
    except Exception:
        pass

    log.info("Session not detected — trying manual login.")
    page.goto(f"{INSTAGRAM_URL}accounts/login/", timeout=60000)

    try:
        page.wait_for_selector("input[name='username']", timeout=20000)
    except Exception:
        log.warning("Could not find username field; page may be blocked or redirected.")
        return

    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")

    try:
        page.wait_for_selector("input[placeholder*='Search']", timeout=20000)
        log.info("Login successful.")
    except Exception:
        log.warning("Login may need manual confirmation (2FA or challenge).")

    page.context.storage_state(path=str(STATE_PATH))
    log.info(f"Session state saved → {STATE_PATH}")


def ensure_logged_in(headless: bool = True) -> None:
    _ensure_state_dir()
    with sync_playwright() as p:
        proxy_cfg = _proxy_config()
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR),
            headless=headless,
            **({"proxy": proxy_cfg} if proxy_cfg else {})
        )
        page = context.new_page()
        page.goto(INSTAGRAM_URL, timeout=60000)
        _login_if_needed(page)
        context.close()


def post_feed(image_path: str, caption: str, headless: bool = True) -> Dict[str, Any]:
    _ensure_state_dir()
    image_abs = str(Path(image_path).resolve())
    if not Path(image_abs).exists():
        raise FileNotFoundError(f"Image not found: {image_abs}")

    with sync_playwright() as p:
        proxy_cfg = _proxy_config()
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR),
            headless=headless,
            **({"proxy": proxy_cfg} if proxy_cfg else {})
        )
        page = context.new_page()
        page.goto(INSTAGRAM_URL, timeout=60000)

        _login_if_needed(page)

        # --- Open post creation ---
        log.info("Opening Instagram 'New Post' dialog...")
        clicked = False
        for sel in [
            "svg[aria-label='New post']",
            "svg[aria-label='Create']",
            "xpath=//div[contains(.,'Create')]",
            "xpath=//span[contains(.,'Create')]",
        ]:
            try:
                page.click(sel, timeout=4000)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            try:
                page.goto("https://www.instagram.com/create/select/", timeout=20000)
                clicked = True
            except Exception:
                pass

        if not clicked:
            context.close()
            return {"status": "error", "error": "Could not open 'New post' dialog."}

        # --- Upload image ---
        try:
            log.info("Uploading image...")
            file_input = page.wait_for_selector("input[type='file']", timeout=15000, state="attached")
            file_input.set_input_files(image_abs)
            log.info(f"✅ File uploaded → {image_abs}")
        except Exception as e:
            context.close()
            return {"status": "error", "error": f"Upload failed: {e}"}

        # --- Next buttons ---
        # --- Step through Next buttons (Edit → Filter → Caption)
        for step in range(2):
            try:
                log.info(f"🔹 Waiting for 'Next' button (step {step + 1})...")
                next_button = page.wait_for_selector(
                    "div[role='button']:has-text('Next'), button:has-text('Next')",
                    timeout=15000
                )
                page.evaluate("el => el.scrollIntoView()", next_button)
                time.sleep(1.5)
                next_button.click()
                log.info(f"✅ Clicked 'Next' (step {step + 1})")
                time.sleep(4)
            except PWTimeoutError:
                log.warning(f"⚠️ Could not find 'Next' button on step {step + 1}")
                break

        # --- Caption ---
        try:
            caption_field = page.wait_for_selector("div[role='textbox']", timeout=10000)
            caption_field.click()
            caption_field.fill(caption)
            log.info("✅ Caption added successfully.")
        except Exception as e:
            log.warning(f"Caption entry failed: {e}")

        # --- Share post ---
        shared = False
        try:
            log.info("🔹 Locating the correct 'Share' button inside the Create Post dialog...")

            # Wait for the Share button to appear inside the active dialog
            share_button = page.wait_for_selector(
                "div[role='dialog'] div[role='button'] >> text=Share",
                timeout=15000
            )

            # Scroll into view and wait a moment for Instagram to enable it
            page.evaluate("(el) => el.scrollIntoView()", share_button)
            time.sleep(1.5)

            # Ensure the button isn't disabled
            try:
                page.wait_for_function(
                    """() => {
                        const btns = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"]'));
                        const share = btns.find(b => b.textContent.trim() === 'Share');
                        return share && !share.getAttribute('aria-disabled');
                    }""",
                    timeout=10000
                )
            except Exception:
                log.warning("⚠️ Share button might still be disabled, attempting click anyway.")

            share_button.click()
            log.info("✅ Clicked correct 'Share' button (within Create dialog).")
            shared = True

        except PWTimeoutError:
            log.warning("⚠️ Could not find the correct 'Share' button inside Create dialog.")
        except Exception as e:
            log.error(f"Unexpected error while sharing: {e}")

        if not shared:
            context.close()
            return {"status": "error", "error": "Failed to click Share (wrong modal or missing button)."}

        # --- Wait for confirmation ---
        log.info("⏳ Waiting for post upload to complete...")
        failed = False
        try:
            page.wait_for_selector("div[role='dialog']", state="detached", timeout=45000)
            log.info("✅ Upload completed (modal closed).")

            # Wait briefly for an error toast; if none appears, assume success
            try:
                page.wait_for_selector("text=Couldn’t upload", timeout=3000)
                failed = True
                log.warning("❌ Instagram reported an upload failure.")
            except PWTimeoutError:
                failed = False
        except PWTimeoutError:
            log.warning("⚠️ Modal did not close — upload uncertain.")

        page.screenshot(path="assets/last_instagram_screen.png")
        log.info("📸 Saved debug screenshot → assets/last_instagram_screen.png")

        if not failed:
            # Stronger success signal: modal closed & no error toast
            context.close()
            return {"status": "success", "detail": "Posted to feed successfully."}

        # Fallback check: try to detect feed/home icon
        try:
            if page.locator("svg[aria-label='Home']").is_visible(timeout=3000):
                context.close()
                return {"status": "success", "detail": "Posted to feed successfully."}
        except Exception:
            pass

        log.warning("⚠️ No clear upload confirmation.")
        context.close()
        return {"status": "pending", "detail": "Upload uncertain, check screenshot."}


if __name__ == "__main__":
    print("🔐 Launching Instagram login verification...")
    ensure_logged_in(headless=False)
    print("✅ Session check complete — ready to post.")
