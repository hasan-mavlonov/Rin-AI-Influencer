"""Coordinate background scheduling for automated post cycles.

This scheduler now favors one deeply crafted reel per day with an optional
second post when the storyline benefits from an extra beat. Timing adapts to
Shanghai daily rhythms and Rin's current narrative arc.
"""

import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from core.logger import get_logger
from personas.loader import load_recent_posts
from generators.idea_generator import get_scene_memory_snapshot
from run_post_cycle import run_post_cycle
from engagement.engagement_engine import run_engagement_cycle

log = get_logger("DynamicScheduler")

# Default configuration for daily scheduling windows (local Shanghai time)
TIMEZONES = "Asia/Shanghai"
WINDOWS: Dict[str, Tuple[int, int]] = {
    "sunrise": (7, 10),
    "late_morning": (10, 12),
    "afternoon": (13, 16),
    "evening": (18, 21),
    "night": (21, 23),
}
ENGAGEMENT_WINDOW = (9, 22)
ENGAGEMENT_BUFFER_MINUTES = 45


def _random_time_between(start_hour: int, end_hour: int) -> datetime:
    """Generate a random datetime within today's given hour window."""

    now = datetime.now()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    delta = max(1, int((end - start).total_seconds()))
    rand_seconds = random.randint(0, delta)
    return start + timedelta(seconds=rand_seconds)


def _engagement_hint(recent_posts: List[dict]) -> float:
    """Estimate engagement to decide whether an extra post is worth it."""

    if not recent_posts:
        return 0.5

    scores = []
    for p in recent_posts:
        metrics = p.get("metrics") or {}
        likes = metrics.get("likes") or p.get("likes", 0)
        comments = metrics.get("comments") or p.get("comments", 0)
        followers = metrics.get("followers", metrics.get("followers_at_post", 1)) or 1
        scores.append((likes + comments * 2) / max(followers, 1))

    if not scores:
        return 0.4

    avg = sum(scores) / len(scores)
    return max(0.1, min(avg * 3, 0.9))


def _recent_hours_since_last_post(recent_posts: List[dict]) -> float:
    if not recent_posts:
        return 999
    try:
        latest = recent_posts[0].get("created_at") or recent_posts[0].get("timestamp")
        if latest:
            if isinstance(latest, str):
                latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            else:
                latest_dt = latest
            delta = datetime.now(latest_dt.tzinfo) - latest_dt
            return delta.total_seconds() / 3600
    except Exception:
        return 999
    return 999


def _decide_post_count(recent_posts: List[dict]) -> int:
    """Choose 1–2 posts per day based on rhythm and engagement."""

    engagement = _engagement_hint(recent_posts)
    hours_since = _recent_hours_since_last_post(recent_posts)

    # Default to a single, strong post. Add a second slot if audience is warm
    # and Rin hasn't posted in a while.
    if hours_since > 28 and engagement > 0.35:
        return 2
    if engagement > 0.55 and hours_since > 18:
        return 2
    if random.random() < 0.15:  # occasional bonus reel
        return 2
    return 1


def _preferred_windows(arc_snapshot: dict) -> List[str]:
    """Return time-window labels that match the current storyline mood."""

    mood = (arc_snapshot or {}).get("current_mood", "")
    beat = (arc_snapshot or {}).get("beat", "")
    if "night" in beat or mood in {"reflective", "restless"}:
        return ["evening", "night"]
    if "study" in beat or mood in {"focused", "hopeful"}:
        return ["sunrise", "late_morning", "afternoon"]
    if mood in {"playful", "adventurous"}:
        return ["late_morning", "afternoon", "evening"]
    return ["late_morning", "evening"]


def _choose_windows(count: int, arc_snapshot: dict) -> List[Tuple[str, Tuple[int, int]]]:
    candidates = list(WINDOWS.items())
    priority = _preferred_windows(arc_snapshot)

    sorted_candidates = sorted(
        candidates,
        key=lambda item: priority.index(item[0]) if item[0] in priority else len(priority),
    )

    # Ensure variety while following preference order
    selected = []
    for name, window in sorted_candidates:
        if len(selected) >= count:
            break
        selected.append((name, window))

    # If priority windows are exhausted, fill with random remaining unique slots
    while len(selected) < count:
        remaining = [c for c in candidates if c not in selected]
        if not remaining:
            break
        selected.append(random.choice(remaining))

    return selected


def _is_far_from_post(candidate: datetime, post_times: List[datetime]) -> bool:
    buffer = timedelta(minutes=ENGAGEMENT_BUFFER_MINUTES)
    return all(abs(candidate - pt) > buffer for pt in post_times)


def _engagement_slots(
    desired: int, arc_snapshot: dict, post_times: List[datetime]
) -> List[datetime]:
    start_hour, end_hour = ENGAGEMENT_WINDOW
    mood = (arc_snapshot or {}).get("current_mood", "")
    if mood in {"reflective", "restless"}:
        end_hour = min(23, end_hour + 1)
    if mood in {"playful", "adventurous"}:
        start_hour = max(8, start_hour - 1)

    slots: list[datetime] = []
    attempts = 0
    while len(slots) < desired and attempts < desired * 6:
        candidate = _random_time_between(start_hour, end_hour)
        if _is_far_from_post(candidate, post_times) and _is_far_from_post(
            candidate, slots
        ):
            slots.append(candidate)
        attempts += 1
    return slots


def _schedule_post(
    scheduler: BackgroundScheduler, post_time: datetime, label: str
) -> datetime:
    """Schedule a single post event that triggers the posting pipeline."""

    def _task():
        log.info(f"🕒 {label.capitalize()} post triggered at {datetime.now():%H:%M}")
        try:
            run_post_cycle("rin", auto_post=True, headless=True)
        except Exception as e:  # noqa: BLE001 - logging the error suffices here.
            log.error(f"❌ Post failed: {e}")

    try:
        scheduler.add_job(
            _task,
            trigger=DateTrigger(run_date=post_time),
            name=f"{label}_post",
        )
        log.info(f"📅 Scheduled {label} post for {post_time.strftime('%H:%M')}")
    except Exception as exc:  # noqa: BLE001 - APScheduler may raise various errors.
        log.error(f"Failed to schedule {label} post at {post_time}: {exc}")
    return post_time


def _schedule_engagement(
    scheduler: BackgroundScheduler, run_time: datetime, label: str
) -> None:
    """Schedule one engagement burst."""

    def _task():
        log.info(f"💬 {label} engagement window opened at {datetime.now():%H:%M}")
        try:
            run_engagement_cycle()
        except Exception as exc:  # noqa: BLE001
            log.error(f"❌ Engagement cycle failed: {exc}")

    try:
        scheduler.add_job(
            _task,
            trigger=DateTrigger(run_date=run_time),
            name=f"{label}_engagement",
        )
        log.info(f"🗨️ Scheduled engagement burst for {run_time.strftime('%H:%M')}")
    except Exception as exc:  # noqa: BLE001
        log.error(f"Failed to schedule engagement at {run_time}: {exc}")


def _plan_engagement_day(
    scheduler: BackgroundScheduler, post_times: List[datetime], arc_snapshot: dict
) -> None:
    desired = random.randint(2, 5)
    slots = _engagement_slots(desired, arc_snapshot, post_times)
    for idx, slot in enumerate(slots, start=1):
        label = f"engagement-{idx}"
        _schedule_engagement(scheduler, slot, label)


def plan_day(scheduler: BackgroundScheduler) -> None:
    """Plan today's posts with a narrative-first cadence (1–2 posts)."""

    log.info("🌞 Rin is planning her Shanghai story beats for today...")
    recent_posts = load_recent_posts("rin", limit=6)
    arc_snapshot = get_scene_memory_snapshot()
    daily_posts = _decide_post_count(recent_posts)

    windows = _choose_windows(daily_posts, arc_snapshot)

    post_times = []
    for label, (start_h, end_h) in windows:
        post_time = _random_time_between(start_h, end_h)
        post_times.append(_schedule_post(scheduler, post_time, label))

    _plan_engagement_day(scheduler, post_times, arc_snapshot)

    log.info(
        "🪄 Daily plan complete — %s post(s) scheduled with arc '%s'.",
        daily_posts,
        (arc_snapshot or {}).get("arc", "unknown"),
    )


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
