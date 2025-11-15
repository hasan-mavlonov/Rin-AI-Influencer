"""CLI-friendly entry point for launching the dynamic posting scheduler."""
# Re-exports the real scheduler logic from core.scheduler for backward imports.

from core.scheduler import plan_day, start_dynamic_scheduler

__all__ = ["plan_day", "start_dynamic_scheduler"]


if __name__ == "__main__":
    start_dynamic_scheduler()
