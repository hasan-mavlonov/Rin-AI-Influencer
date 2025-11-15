"""Coordinate background scheduling for automated post cycles."""
# Centralizes scheduling helpers so CLI wrappers can stay lightweight.

import random
import time
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from core.logger import get_logger
from run_post_cycle import run_post_cycle

log = get_logger("DynamicScheduler")

# Default configuration for daily scheduling windows.
TIMEZONES = "Asia/Shanghai"
WINDOWS = {
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 23),
}

# Post count per day (3 = morning/afternoon/evening)
DAILY_POSTS = 3


def _random_time_between(start_hour: int, end_hour: int) -> datetime:
    """Generate a random datetime within today's given hour window."""

    now = datetime.now()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    delta = (end - start).seconds
    rand_seconds = random.randint(0, delta)
    return start + timedelta(seconds=rand_seconds)


def _schedule_post(scheduler: BackgroundScheduler, post_time: datetime, label: str) -> None:
    """Schedule a single post event that triggers the posting pipeline."""

    def _task():
        log.info(f"🕒 {label.capitalize()} post triggered at {datetime.now():%H:%M}")
        try:
            run_post_cycle("rin", auto_post=True, headless=True)
        except Exception as e:  # noqa: BLE001 - logging the error suffices here.
            log.error(f"❌ Post failed: {e}")

    try:
        scheduler.add_job(_task, trigger=DateTrigger(run_date=post_time))
        log.info(f"📅 Scheduled {label} post for {post_time.strftime('%H:%M')}")
    except Exception as exc:  # noqa: BLE001 - APScheduler may raise various errors.
        log.error(f"Failed to schedule {label} post at {post_time}: {exc}")


def plan_day(scheduler: BackgroundScheduler) -> None:
    """Plan today's posts dynamically by sampling from configured windows."""

    log.info("🌞 Rin is planning her posts for today...")
    chosen_windows = list(WINDOWS.items())[:DAILY_POSTS]

    for label, (start_h, end_h) in chosen_windows:
        post_time = _random_time_between(start_h, end_h)
        _schedule_post(scheduler, post_time, label)

    log.info("🪄 Daily plan complete — waiting for next cycle.")


def start_dynamic_scheduler() -> None:
    """Main entry point used by CLIs to launch the background scheduler."""

    scheduler = BackgroundScheduler(timezone=TIMEZONES)
    try:
        scheduler.start()
    except Exception as exc:  # noqa: BLE001 - ensure failure is surfaced cleanly.
        log.error(f"Failed to start scheduler: {exc}")
        return

    try:
        plan_day(scheduler)
    except Exception as exc:  # noqa: BLE001 - keep scheduler alive on planning issues.
        log.error(f"Initial planning failed: {exc}")

    try:
        scheduler.add_job(plan_day, "cron", hour=0, minute=5, args=[scheduler])
        log.info("🕛 Daily re-planning set for 00:05 every day.")
    except Exception as exc:  # noqa: BLE001 - cron setup should not crash runtime.
        log.error(f"Failed to register daily re-planning job: {exc}")

    try:
        while True:
            try:
                time.sleep(60)
            except Exception as exc:  # noqa: BLE001 - keep loop resilient to OS signals.
                log.warning(f"Scheduler sleep interrupted: {exc}")
    except KeyboardInterrupt:
        log.warning("🛑 Scheduler stopped manually.")
    except Exception as exc:  # noqa: BLE001 - catch-all to avoid silent exits.
        log.error(f"Scheduler loop terminated unexpectedly: {exc}")
    finally:
        scheduler.shutdown(wait=False)
