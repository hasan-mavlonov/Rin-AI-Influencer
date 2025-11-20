# Agent Notes

- Instagram Graph API integrations (posting + commenting) are pinned to v21.0. Keep this version aligned across modules when touching Instagram calls.
- Engagement cadence can be tuned via ENV values: `ENGAGEMENT_MIN_DELAY_SECONDS`, `ENGAGEMENT_MAX_DELAY_SECONDS`, and `ENGAGEMENT_ACCOUNT_COOLDOWN_HOURS`.
- Engagement history is stored in `data/engagement_history.json`; keep its shape (account_id, username, media_id, comment, timestamp, mood, beat, status).
