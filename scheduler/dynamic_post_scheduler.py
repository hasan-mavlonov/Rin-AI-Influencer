import random
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from run_post_cycle import run_post_cycle
from core.logger import get_logger

log = get_logger("DynamicScheduler")

# ---------- CONFIG ----------
TIMEZONES = "Asia/Shanghai"
WINDOWS = {
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 23),
}

# Post count per day (3 = morning/afternoon/evening)
DAILY_POSTS = 3


def _random_time_between(start_hour: int, end_hour: int):
    """Generate random datetime within today’s given hour window."""
    now = datetime.now()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    delta = (end - start).seconds
    rand_seconds = random.randint(0, delta)
    return start + timedelta(seconds=rand_seconds)


def _schedule_post(scheduler, post_time: datetime, label: str):
    """Schedule a single post event."""
    def _task():
        log.info(f"🕒 {label.capitalize()} post triggered at {datetime.now():%H:%M}")
        try:
            run_post_cycle("rin", auto_post=True, headless=True)
        except Exception as e:
            log.error(f"❌ Post failed: {e}")

    scheduler.add_job(_task, trigger=DateTrigger(run_date=post_time))
    log.info(f"📅 Scheduled {label} post for {post_time.strftime('%H:%M')}")


def plan_day(scheduler):
    """Plan today's posts dynamically."""
    log.info("🌞 Rin is planning her posts for today...")
    chosen_windows = list(WINDOWS.items())[:DAILY_POSTS]

    for label, (start_h, end_h) in chosen_windows:
        post_time = _random_time_between(start_h, end_h)
        _schedule_post(scheduler, post_time, label)

    log.info("🪄 Daily plan complete — waiting for next cycle.")


def start_dynamic_scheduler():
    """Main entry for dynamic posting."""
    scheduler = BackgroundScheduler(timezone=TIMEZONES)
    scheduler.start()

    # Plan immediately for today
    plan_day(scheduler)

    # Re-plan daily at 00:05 AM
    scheduler.add_job(plan_day, "cron", hour=0, minute=5, args=[scheduler])
    log.info("🕛 Daily re-planning set for 00:05 every day.")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.warning("🛑 Scheduler stopped manually.")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    start_dynamic_scheduler()
