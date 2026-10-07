"""
OPT unemployment clock.

F-1 OPT allows 90 days of unemployment; a STEM OPT extension adds 60 more
(150 total). The user records how many days they had used as of a date and
whether they are currently employed; days keep accruing while unemployed.
"""

from datetime import date, datetime

OPT_LIMIT      = 90
STEM_OPT_LIMIT = 150


def _parse(d) -> date | None:
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def opt_clock(profile: dict, today: date = None) -> dict:
    imm   = (profile or {}).get("immigration", {})
    today = today or date.today()

    if imm.get("status") != "F1-OPT":
        return {"applicable": False}

    limit    = STEM_OPT_LIMIT if imm.get("stem_opt") else OPT_LIMIT
    try:
        used = max(0, int(imm.get("unemployment_days_used") or 0))
    except (TypeError, ValueError):
        used = 0
    as_of    = _parse(imm.get("unemployment_as_of")) or today
    employed = bool(imm.get("currently_employed"))

    if not employed:
        used += max(0, (today - as_of).days)

    left = max(0, limit - used)
    urgency = "critical" if left <= 15 else "warn" if left <= 30 else "ok"

    return {
        "applicable": True,
        "limit":      limit,
        "used":       min(used, limit),
        "left":       left,
        "employed":   employed,
        "stem":       bool(imm.get("stem_opt")),
        "urgency":    urgency,
    }
