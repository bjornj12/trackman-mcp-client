"""Trackman Golf MCP server (FastMCP).

Exposes the user's Trackman golf data as MCP tools. The server ONLY fetches and
returns raw data — coaching/analysis lives in the Claude skills. See CLAUDE.md.

Run:  trackman-mcp           (stdio transport)
Auth: set TRACKMAN_TOKEN to a Bearer access token captured from an authenticated
      portal session (see docs/trackman-api.md).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastmcp import FastMCP

from . import queries
from .client import TrackmanAuthError, TrackmanClient
from .config import Config

mcp = FastMCP(
    name="trackman-golf",
    instructions=(
        "Fetches the signed-in user's Trackman Golf statistics: profile and "
        "handicap, practice/course sessions, scorecards, shot-level launch "
        "metrics, and club gapping. Returns raw data only — interpret it with "
        "the golf coaching skills. Call `authenticate` first to confirm the "
        "token works."
    ),
)


# Seconds to wait for a silent refresh before giving up (dead session fails fast).
SILENT_REFRESH_TIMEOUT = 30.0


async def _try_silent_refresh() -> bool:
    """Try to refresh the token headlessly using the persisted browser session.

    Returns True if a fresh token was captured (the saved portal session is still
    valid), False otherwise (session expired, or Playwright not installed).
    """
    try:
        from .login import capture_token

        await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
        return True
    except Exception:
        return False


async def _run(
    query: str, variables: dict[str, Any] | None = None, _allow_refresh: bool = True
) -> dict[str, Any]:
    """Execute a GraphQL query with a fresh authenticated client.

    On an auth failure, transparently try a one-time silent token refresh (using
    the saved browser session) and retry. If that fails too, the auth error
    propagates with guidance to re-login.
    """
    config = Config.from_env()
    try:
        async with TrackmanClient(config) as client:
            return await client.execute(query, variables)
    except TrackmanAuthError:
        if _allow_refresh and await _try_silent_refresh():
            return await _run(query, variables, _allow_refresh=False)
        raise


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def authenticate() -> dict[str, Any]:
    """Verify the configured Trackman token and report who you're signed in as.

    Does not perform a password login (the portal client is server-side only).
    It validates the Bearer token in TRACKMAN_TOKEN against the OIDC userinfo
    endpoint. If this fails, re-capture the token from an authenticated portal
    session.
    """
    config = Config.from_env()
    if not config.has_token:
        return {
            "authenticated": False,
            "reason": "No Trackman token. You're not signed in.",
            "how_to_fix": "Use the `login` tool to sign in (it opens a browser).",
        }
    try:
        async with TrackmanClient(config) as client:
            info = await client.whoami()
    except TrackmanAuthError:
        return {
            "authenticated": False,
            "reason": "Your Trackman session has expired.",
            "how_to_fix": "Use the `login` tool to sign in again.",
        }
    # Return identity claims only; never echo the token.
    return {
        "authenticated": True,
        "subject": info.get("sub"),
        "name": info.get("name"),
        "email": info.get("email"),
    }


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
async def login(open_browser: bool = True) -> dict[str, Any]:
    """Sign in to Trackman — the easy way to (re)authenticate when expired.

    Tries a **silent** refresh first (using the saved browser session — no window,
    instant if the session is still valid). If the session has expired and
    `open_browser` is true, it **opens a browser window** for you to sign in once;
    the new token is then captured and cached automatically.

    Returns who you're signed in as, or a clear message if login couldn't complete.
    """
    from .login import TrackmanLoginError, capture_token

    # 1) Silent refresh (fast; works while the saved session is valid).
    try:
        await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
    except Exception:
        # 2) Session likely expired — open a window for an interactive sign-in.
        if not open_browser:
            return {
                "success": False,
                "message": "Saved session expired and open_browser is false. "
                           "Call login with open_browser=true, or run "
                           "`trackman-mcp login` in a terminal.",
            }
        try:
            await capture_token(headless=False)
        except TrackmanLoginError as exc:
            return {"success": False, "message": f"Login didn't complete: {exc}"}

    config = Config.from_env()
    try:
        async with TrackmanClient(config) as client:
            info = await client.whoami()
    except TrackmanAuthError:
        return {"success": False,
                "message": "Captured a token but it was rejected — try login again."}
    return {"success": True, "name": info.get("name") or info.get("subject"),
            "message": "Signed in. The MCP will use this automatically."}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_profile() -> dict[str, Any]:
    """Get the player's profile and current handicap.

    Returns identity (name, email, nationality, dexterity, category) and the
    current handicap (`hcp.currentHcp`, plus the most recent handicap record).
    """
    data = await _run(queries.PROFILE)
    return data.get("me", {})


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_handicap(skip: int = 0, take: int = 20, only_in_avg: bool = False) -> dict[str, Any]:
    """Get handicap history: per-round differentials and how the index moved.

    Args:
        skip: paging offset.
        take: number of records to return.
        only_in_avg: only records counted in the handicap average.
    """
    data = await _run(
        queries.HANDICAP_HISTORY,
        {"skip": skip, "take": take, "onlyInAvg": only_in_avg},
    )
    return data.get("me", {}).get("hcp", {})


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def list_sessions(
    skip: int = 0,
    take: int = 25,
    kinds: list[str] | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List the player's activities (practice sessions and course rounds).

    Args:
        skip / take: paging.
        kinds: optional ActivityKind filter, e.g. ["RANGE_PRACTICE", "COURSE_PLAY"].
        time_from / time_to: ISO-8601 timestamps to bound the window.
        include_hidden: include activities the user has hidden.

    Returns totalCount and a page of items (id, time, kind, plus a per-kind
    summary). Use `get_session` with an item's id for full detail.
    """
    data = await _run(
        queries.LIST_SESSIONS,
        {
            "skip": skip,
            "take": take,
            "kinds": kinds,
            "timeFrom": time_from,
            "timeTo": time_to,
            "includeHidden": include_hidden,
        },
    )
    return data.get("me", {}).get("activities", {})


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_session(activity_id: str) -> dict[str, Any]:
    """Get one activity in full by its id.

    For RANGE_PRACTICE: every stroke with its launch-monitor measurement.
    For COURSE_PLAY: the scorecard with per-hole scores and per-shot metrics.
    """
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    node = data.get("node")
    if not node:
        raise ValueError(f"No activity found for id {activity_id!r}.")
    return node


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_course_rounds(
    skip: int = 0, take: int = 20, completed: bool | None = True
) -> dict[str, Any]:
    """Get the player's course rounds (scorecards).

    Each round includes per-hole scores (score, putts, GIR, hcp strokes) and
    round aggregates (`stat`: driving, FIR, GIR, putts, score distribution).

    Args:
        skip / take: paging.
        completed: filter by completion (True = finished rounds only).
    """
    data = await _run(
        queries.COURSE_ROUNDS, {"skip": skip, "take": take, "completed": completed}
    )
    return {"scorecards": data.get("me", {}).get("scorecards", [])}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_club_stats(include_retired: bool = False) -> dict[str, Any]:
    """Get per-club gapping and dispersion ("My Bag" / Find My Distance).

    For each club: average carry and total, carry/total standard deviation, and
    the dispersion ellipse. This is the source for gapping analysis.
    """
    data = await _run(queries.CLUB_STATS, {"includeRetired": include_retired})
    return data.get("me", {}).get("equipment", {})


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_shot_data(activity_id: str) -> dict[str, Any]:
    """Get shot-level launch-monitor metrics for one activity.

    Convenience wrapper over `get_session` that returns the same full detail
    (strokes/shots with ball speed, club speed, smash, launch, spin, carry,
    side, curve, landing angle, …). Pass a RANGE_PRACTICE or COURSE_PLAY id.
    """
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    node = data.get("node")
    if not node:
        raise ValueError(f"No activity found for id {activity_id!r}.")
    return node


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def get_activity_summary(
    time_from: str | None = None,
    time_to: str | None = None,
    skip: int = 0,
    take: int = 50,
) -> dict[str, Any]:
    """Get activity counts grouped by kind over an optional time window."""
    data = await _run(
        queries.ACTIVITY_SUMMARY,
        {"timeFrom": time_from, "timeTo": time_to, "skip": skip, "take": take},
    )
    return data.get("me", {}).get("activitySummary", {})


async def _login_cmd(headless: bool) -> int:
    """Run the browser login, cache the token, and confirm identity."""
    from .login import TrackmanLoginError, capture_token

    mode = "headless" if headless else "a browser window"
    print(f"Opening Trackman login ({mode})… sign in if prompted.")
    try:
        await capture_token(headless=headless)
    except TrackmanLoginError as exc:
        print(f"Login failed: {exc}")
        return 1

    # Confirm the captured token works (and show who it belongs to).
    config = Config.from_env()
    async with TrackmanClient(config) as client:
        info = await client.whoami()
    print(f"✓ Logged in as {info.get('name') or info.get('sub')}. "
          "Token cached — the MCP will use it automatically.")
    return 0


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
async def analyze_and_store_session(activity_id: str) -> dict[str, Any]:
    """Analyze one session, store the analysis locally, and return it.

    Fetches the session detail, runs the deterministic analyzer (classify
    warm-up vs serious practice vs game; per-session metrics; course difficulty;
    normalization against previously stored sessions; used vs available clubs),
    saves the result to the local store (kept to the last 30, latest first), and
    returns the stored record. Intended to be driven by the analyzer skill.
    """
    from . import analysis, session_store

    node = (await _run(queries.GET_SESSION, {"id": activity_id})).get("node") or {}
    if not node:
        return {"error": f"no session found for id {activity_id}"}

    clubs_available: list[str] | None = None
    try:
        equip = (await _run(queries.CLUB_STATS, {"includeRetired": False})) \
            .get("me", {}).get("equipment", {})
        clubs_available = [
            c.get("displayName") for c in (equip.get("clubs") or [])
            if c.get("displayName")
        ]
    except Exception:  # club data is a nice-to-have, not required
        clubs_available = None

    history = [
        r for r in session_store.list_analyses()
        if r.get("session_id") != activity_id
    ]
    record = analysis.analyze(
        node, session_id=activity_id, history=history,
        clubs_available=clubs_available,
    )
    session_store.save_analysis(record)
    return record


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
async def list_session_analyses() -> dict[str, Any]:
    """List stored session analyses, most recent first (max 30).

    Returns a lightweight index (id, time, kind, category, seriousness, summary)
    plus the total count. Use `get_session_analysis` for a full record.
    """
    from . import session_store

    items = session_store.list_analyses()
    index = [
        {
            "session_id": r.get("session_id"),
            "time": r.get("time"),
            "kind": r.get("kind"),
            "category": (r.get("analysis") or {}).get("category"),
            "seriousness": (r.get("analysis") or {}).get("seriousness"),
            "summary": (r.get("analysis") or {}).get("summary"),
        }
        for r in items
    ]
    return {"count": len(index), "latest_id": index[0]["session_id"] if index else None,
            "items": index}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
async def get_session_analysis(activity_id: str) -> dict[str, Any]:
    """Get one full stored session-analysis record by id."""
    from . import session_store

    return session_store.get_analysis(activity_id) or {
        "error": f"no stored analysis for {activity_id}"
    }


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False})
async def save_training_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Save a prescribed training plan so the coach remembers it later.

    The plan is a structured dict (the coach builds it), e.g.:
    {
      "title": "<short plan name>",
      "focus": ["<gap it targets>"],
      "diagnosis": "<one line: the numbers behind it>",
      "blocks": [{"name": "<drill>", "club": "<club>", "reps": N,
                  "detail": "…", "link": "https://…", "goal": "<measurable goal>"}],
      "targets": {"<metric>": "<target range>"}
    }
    Adds it to the pending queue. Returns the stored plan (with id). Plans are
    capped at the most recent 50.
    """
    from . import training_store

    if not isinstance(plan, dict) or not plan:
        raise ValueError("plan must be a non-empty object describing the session.")
    return training_store.save_plan(plan)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
async def get_next_training() -> dict[str, Any]:
    """Get the next pending training session — the answer to 'what's today's training?'.

    Returns the oldest pending plan, or a note if there are none. Does not mark
    it done; call `mark_training_done` once the session is completed.
    """
    from . import training_store

    plan = training_store.next_pending()
    if not plan:
        return {"has_plan": False,
                "message": "No pending training plan. Ask the coach for one."}
    pending = training_store.list_plans(status="pending")
    return {"has_plan": True, "plan": plan, "pending_count": len(pending)}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
async def list_training_plans(
    status: Literal["pending", "done"] | None = None,
) -> dict[str, Any]:
    """List stored training plans (oldest→newest). Optional status filter
    ('pending' or 'done')."""
    from . import training_store

    plans = training_store.list_plans(status=status)
    return {"count": len(plans), "plans": plans}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True, "openWorldHint": False})
async def mark_training_done(
    plan_id: str, result_session_id: str | None = None
) -> dict[str, Any]:
    """Mark a training plan completed (optionally link the session that did it).

    After this, `get_next_training` returns the following pending plan.
    """
    from . import training_store

    updated = training_store.mark_done(plan_id, result_session_id=result_session_id)
    return updated or {"error": f"no training plan with id {plan_id}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True})
async def verify_training_progress(
    plan_id: str, activity_id: str | None = None
) -> dict[str, Any]:
    """Grade a recent session against a saved plan's target metrics.

    Reads the plan's `target_specs` (structured targets, e.g. driver clubPath
    between -1 and +2), finds the session to check (the given `activity_id`, or
    else the most recent session that has shots for the plan's target club),
    pulls that session's real shot measurements, and reports each target's
    session-mean value vs the target and whether it's met.

    Returns per-target results, `all_met`, and a recommendation (e.g. mark the
    plan done once every target is met). Does not auto-complete the plan.
    """
    from . import analysis, training_store

    plan = training_store.get_plan(plan_id)
    if not plan:
        return {"error": f"no training plan with id {plan_id}"}
    specs = plan.get("target_specs")
    if not specs:
        return {"error": "this plan has no machine-readable target_specs to verify",
                "plan_id": plan_id}

    target_clubs = {analysis.canonical_club(s.get("club")) for s in specs if s.get("club")}

    async def _strokes_for(aid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        node = (await _run(queries.SESSION_MEASUREMENTS, {"id": aid})).get("node") or {}
        return node, (node.get("strokes") or [])

    scan_window = 20
    chosen_id = activity_id
    node: dict[str, Any] = {}
    strokes: list[dict[str, Any]] = []
    if chosen_id:
        node, strokes = await _strokes_for(chosen_id)
    else:
        # Newest first: first session that has shots for a target club.
        acts = (await _run(queries.LIST_SESSIONS, {
            "skip": 0, "take": scan_window, "kinds": None,
            "timeFrom": None, "timeTo": None, "includeHidden": False,
        })).get("me", {}).get("activities", {}).get("items", [])
        for it in acts:
            aid = it.get("id")
            if not aid:
                continue
            # Pre-filter: if the list already names this session's clubs and none
            # match a target club, skip the per-session measurement fetch.
            if target_clubs and it.get("clubs") is not None:
                listed = {analysis.canonical_club(c) for c in it["clubs"]}
                if not (listed & target_clubs):
                    continue
            n, s = await _strokes_for(aid)
            has_target_club = any(
                analysis.canonical_club(st.get("club")) in target_clubs for st in s
            ) if target_clubs else bool(s)
            if has_target_club:
                chosen_id, node, strokes = aid, n, s
                break

    if not strokes:
        scope = "the session you gave" if activity_id else \
            f"the last {scan_window} activities"
        return {"plan_id": plan_id, "checked_session": chosen_id,
                "has_data": False,
                "message": f"No shots for this plan's target club(s) in {scope}."}

    verdict = analysis.verify_targets(strokes, specs)
    return {
        "plan_id": plan_id,
        "plan_title": plan.get("title"),
        "checked_session": chosen_id,
        "session_time": node.get("time"),
        "session_kind": node.get("kind"),
        "results": verdict["results"],
        "all_met": verdict["all_met"],
        "has_data": verdict["has_data"],
        "recommendation": (
            "All targets met — call mark_training_done to graduate this plan."
            if verdict["all_met"] else
            "Not all targets met yet — keep this as the current focus."
        ),
    }


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
async def build_visualization(data: dict[str, Any]) -> dict[str, Any]:
    """Render a coaching diagnosis into a self-contained animated HTML page.

    Returns `{html}` — one standalone document (inline canvas/JS, no network, no
    external resources) ready to drop straight into a Claude **HTML artifact** in
    Claude Desktop / claude.ai, or to write to a file in Claude Code.

    `data` shape (all optional; the viz adapts): {title, subtitle, diagnosis,
    handedness "RH"|"LH", shots:[{launchDirection,carry,totalSide,curve}],
    swing:{clubPath,faceAngle,faceToPath}, targets:[{label,value,target,low,high,
    met}], blocks:[{name,detail,goal,link}]}. See the trackman-visualizer skill.
    """
    from .visualize import build_html

    html = build_html(data)
    return {"html": html, "bytes": len(html.encode()),
            "render_as": "text/html artifact"}


def main() -> None:
    """Console-script entry point.

    Usage:
        trackman-mcp                 run the MCP server (stdio)
        trackman-mcp login           open a browser to sign in and cache a token
        trackman-mcp login --headless  silently refresh using the saved session
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="trackman-mcp")
    sub = parser.add_subparsers(dest="command")
    login = sub.add_parser("login", help="Capture a Trackman token via a browser.")
    login.add_argument(
        "--headless", action="store_true",
        help="Refresh silently using the saved session (no window).",
    )
    args = parser.parse_args()

    if args.command == "login":
        raise SystemExit(asyncio.run(_login_cmd(args.headless)))
    if args.command is None:
        mcp.run()
        return
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
