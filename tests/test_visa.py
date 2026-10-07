from datetime import date

from visa import opt_clock


def profile(**imm):
    return {"immigration": {"status": "F1-OPT", **imm}}


def test_not_applicable_for_other_statuses():
    assert opt_clock({"immigration": {"status": "H1B"}}) == {"applicable": False}


def test_clock_accrues_while_unemployed():
    c = opt_clock(profile(unemployment_days_used=20, unemployment_as_of="2026-09-01"),
                  today=date(2026, 9, 11))
    assert (c["used"], c["left"], c["limit"], c["urgency"]) == (30, 60, 90, "ok")


def test_clock_paused_while_employed_and_stem_limit():
    c = opt_clock(profile(unemployment_days_used=100, unemployment_as_of="2026-01-01",
                          currently_employed=True, stem_opt=True), today=date(2026, 9, 1))
    assert (c["used"], c["left"], c["limit"], c["urgency"]) == (100, 50, 150, "ok")


def test_urgency_and_floor_at_zero():
    assert opt_clock(profile(unemployment_days_used=70), today=date.today())["urgency"] == "warn"
    assert opt_clock(profile(unemployment_days_used=80), today=date.today())["urgency"] == "critical"
    c = opt_clock(profile(unemployment_days_used=85, unemployment_as_of="2026-01-01"),
                  today=date(2026, 6, 1))
    assert c["left"] == 0 and c["used"] == 90


def test_bad_input_is_tolerated():
    c = opt_clock(profile(unemployment_days_used="abc", unemployment_as_of="not a date"))
    assert c["used"] == 0 and c["left"] == 90
