"""
Daily question limit: 30 questions per user in any rolling 24 hours.

Counted in the `usage` table, which has Row Level Security switched on and NO
policies, so users can't read or delete their rows to reset the count. Only the
admin (service key) client, used on the server, can touch it.
"""
from datetime import datetime, timedelta, timezone

DAILY_LIMIT = 30
WINDOW = timedelta(hours=24)


def _since() -> str:
    return (datetime.now(timezone.utc) - WINDOW).isoformat()


def questions_left(admin, user_id: str) -> tuple[int, datetime | None]:
    """(questions left, when the next one frees up if none are left)."""
    rows = (admin.table("usage").select("created_at").eq("user_id", user_id)
            .gte("created_at", _since()).order("created_at").execute().data)
    left = max(0, DAILY_LIMIT - len(rows))
    if left > 0 or not rows:
        return left, None
    oldest = datetime.fromisoformat(str(rows[0]["created_at"]).replace("Z", "+00:00"))
    return 0, oldest + WINDOW


def record_question(admin, user_id: str):
    admin.table("usage").insert({"user_id": user_id}).execute()
