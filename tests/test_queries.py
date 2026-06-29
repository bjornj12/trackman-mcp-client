"""Guards on the GraphQL query strings (structure, not a live call)."""

from __future__ import annotations

from trackman_mcp import queries


def test_session_measurements_covers_range_activities():
    # verify_training_progress runs SESSION_MEASUREMENTS; the range is the
    # primary venue, so range activities must resolve their strokes (or a plan
    # targeting a range-captured metric can never be graded).
    q = queries.SESSION_MEASUREMENTS
    assert "RangePracticeActivity" in q
    assert "RangeFindMyDistanceActivity" in q
    # The metrics a range bay captures and a plan may target.
    for field in ("carry", "totalSide", "curve", "spinAxis", "ballSpeed", "launchDirection"):
        assert field in q


def test_list_sessions_exposes_clubs_for_prefilter():
    # The verify path pre-filters candidate sessions by the clubs already in the
    # list response — so the list query must select them.
    assert "clubs" in queries.LIST_SESSIONS
