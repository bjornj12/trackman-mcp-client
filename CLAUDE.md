# Trackman Golf MCP

## Project Overview

**Name**: Trackman Golf MCP (working name)

**Purpose**: A Model Context Protocol (MCP) server that connects to Trackman's
golf platform using the user's own login, fetches their stats (course rounds,
practice sessions, shot-level launch-monitor data, club gapping, handicap), and
exposes them as MCP tools. On top of that data, a set of Claude **skills** act
as the user's golf coach — diagnosing weaknesses and giving actionable,
specific practice plans with example drills and YouTube links to follow.

**Who it's for**: The individual golfer who already practices on Trackman bays /
ranges or plays Trackman-enabled courses, and wants their data turned into a
concrete "what should I work on next" plan.

---

## The Core Boundary (read this first)

There is a **hard separation of concerns**. Respect it in every change:

- **The MCP server only fetches and returns raw data.** Authentication,
  HTTP calls to Trackman, and shaping responses into clean JSON. It contains
  **no coaching opinions, no drill recommendations, no analysis verdicts.**
- **The Claude skills do all the thinking.** They call the MCP tools to get
  data, then diagnose, plan, and coach in prompt/markdown.

Why: coaching logic should be tunable by editing markdown, not redeploying a
server. Keep judgment out of the server and data out of the skills.

If you find yourself adding "recommend a drill" logic to the MCP, stop — that
belongs in a skill. If you find yourself hardcoding shot data in a skill, stop —
that belongs behind an MCP tool.

---

## Status & Phases

This repo currently contains **documentation and skills only** — no server code
yet. Build in this order:

- **Phase 0 — API discovery (do this first).** Trackman has no public golf API.
  Before writing a single tool, discover the real endpoints and auth flow the
  web portal uses, and write them down. Use the `trackman-api-discovery` skill.
  Output: `docs/trackman-api.md` filled in.
- **Phase 1 — MCP server.** Implement the tools below against the discovered
  API. Python + FastMCP.
- **Phase 2 — Coaching skills.** Wire `trackman-stats-analysis` and
  `golf-coaching` to real tool output; grow the `drill-library`.

Do not skip Phase 0. Tool names and shapes below are **provisional** and will be
corrected by what discovery finds.

---

## Technology Stack

- **Runtime**: Python 3.12+
- **MCP framework**: [FastMCP](https://github.com/jlowin/fastmcp) / the official
  `mcp` Python SDK
- **HTTP client**: `httpx` (async)
- **Auth/session**: `httpx` cookie/token session; tokens stored locally only
- **Data shaping**: plain dicts / `pydantic` models; `pandas` is allowed in
  *skills'* helper scripts for analysis, not required in the server
- **Package/deps**: `uv` (preferred) or `pip` + `pyproject.toml`
- **Tests**: `pytest`; record real API responses as fixtures (with secrets
  scrubbed) and test tools against those.

---

## Planned MCP Tools (provisional — confirm in Phase 0)

All tools return **raw, structured data only**. No prose, no advice.

| Tool | Returns |
|------|---------|
| `authenticate` | Performs/refreshes login using the user's credentials; establishes a session. Never returns the password or raw token to the model. |
| `get_profile` | Player identity + current **handicap** and any headline stats. |
| `list_sessions` | Practice sessions and course rounds (id, date, type, location, summary). Supports date range / type filter. |
| `get_session` | Full detail for one session: every shot and its metrics. |
| `get_course_rounds` | Scorecards: per-hole scores, fairways/greens hit, putts. |
| `get_club_stats` | Per-club aggregates for **gapping**: avg carry, total, ball speed, spin, dispersion. |
| `get_shot_data` | Shot-level launch-monitor metrics: ball speed, club speed, smash, launch angle, spin rate, carry, total, side/curve, landing angle. |

When discovery reveals the true endpoints, update this table and keep it honest.

---

## Authentication & Secrets — Rules

Treat the user's Trackman login as sensitive. **Non-negotiable:**

- **Never commit credentials, tokens, cookies, or session dumps.** They go in
  `.env` (gitignored) or the OS keychain — never in source or fixtures.
- The MCP reads credentials from environment variables only
  (`TRACKMAN_USERNAME`, `TRACKMAN_PASSWORD`, or a captured `TRACKMAN_TOKEN`).
  See `.env.example` once Phase 1 starts.
- **Do not return raw auth material to the model.** Tools may say "authenticated
  as <name>" but must not echo passwords or bearer tokens.
- **Scrub fixtures.** Any recorded API response saved for tests must have
  tokens, cookies, emails, and player IDs redacted or faked.
- Cache sessions locally under a gitignored path (e.g. `.cache/`), not in the
  repo tree.
- This MCP is for a user accessing **their own** Trackman account. Don't build
  anything that scrapes or accesses other users' data.

---

## Project Structure (target, once Phase 1 begins)

```
trackman-mcp-client/
├── CLAUDE.md                      # this file
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   └── trackman-api.md            # discovered endpoints (Phase 0 output)
├── src/
│   └── trackman_mcp/
│       ├── __init__.py
│       ├── server.py              # FastMCP app + tool registration
│       ├── client.py              # Trackman HTTP client + auth/session
│       ├── tools/                 # one module per tool group
│       └── models.py              # pydantic response models
├── tests/
│   ├── fixtures/                  # scrubbed recorded responses
│   └── test_tools.py
└── .claude/
    └── skills/                    # coaching brain (see below)
```

---

## Skills (the coaching brain)

Project-local skills live in `.claude/skills/`. Each has a `SKILL.md`.

- **`trackman-api-discovery`** — Phase 0. Reverse-engineer the portal's auth +
  data endpoints via the browser network panel; write them into
  `docs/trackman-api.md`.
- **`trackman-stats-analysis`** — Pull stats through the MCP and diagnose weak
  areas (dispersion, gapping, scoring trends, handicap movement). Analysis only.
- **`golf-coaching`** — Turn the diagnosis into specific, actionable practice:
  an example session, drills, and YouTube links. The coach persona.
- **`drill-library`** — Curated drills + vetted YouTube links, plus the
  procedure for live web-searching fresh videos matched to a weakness.

Typical flow: `authenticate` → `trackman-stats-analysis` (diagnose) →
`golf-coaching` (prescribe, pulling from `drill-library`).

---

## Conventions

- Keep tools small and single-purpose; one concern per module.
- Tools fail loudly with clear errors (auth expired, endpoint changed) rather
  than returning empty success.
- Prefer async `httpx`; don't block the event loop.
- When the API shape is uncertain, write a fixture-backed test from a real
  (scrubbed) response so regressions are caught when Trackman changes things.
- Coaching is **specific**: "10 balls, 7-iron, alternate target 140/160y, log
  carry dispersion" — never "practice your irons."

---

*Last updated: 2026-06-27 · Version 0.1.0 (scaffolding)*
