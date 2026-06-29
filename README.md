<!-- mcp-name: io.github.bjornj12/trackman-mcp -->

# trackman-mcp

An MCP server that logs into **Trackman Golf** with your own account and exposes
your stats — course rounds, practice sessions, shot-level launch-monitor data,
club gapping, and handicap — as MCP tools. On top of that, a set of Claude
**skills** act as your golf coach: they diagnose your weaknesses and hand you a
specific practice plan with drills and YouTube links for your next session.

> [!IMPORTANT]
> **Unofficial.** This project is not affiliated with or endorsed by Trackman.
> It talks to Trackman's **private** web API using a token from *your own*
> authenticated session, and automates a browser login on your behalf. This may
> conflict with Trackman's Terms of Service — use it on your own account, at your
> own risk. Never use it to access anyone else's data.

## Design boundary

- **MCP server** = raw data fetch + auth only. No opinions.
- **Skills** = all the coaching (analysis, plans, drills).

See [`CLAUDE.md`](./CLAUDE.md) for the full architecture and auth/secret rules.

## Install

### Option A — Claude Code plugin (server + skills together)

```text
/plugin marketplace add bjornj12/trackman-mcp-client
/plugin install trackman-golf@trackman-golf
```

This installs the MCP server (run via `uvx`) **and** the six coaching skills.
Then sign in once (see [Authentication](#authentication)).

### Option B — any MCP client (Claude Desktop, etc.)

Once published to PyPI, add this to your client's MCP config (Claude Desktop:
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "trackman-golf": {
      "command": "uvx",
      "args": ["trackman-mcp"]
    }
  }
}
```

No `env` is required: after you run `trackman-mcp login` the server loads the
cached token from `~/.trackman-mcp/token.json` automatically. (You can instead
set `TRACKMAN_TOKEN` to override it — see `.env.example`.)

To run it straight from a local checkout before publishing, use
`"command": "uvx", "args": ["--from", "/abs/path/to/trackman-mcp-client", "trackman-mcp"]`.

### Option C — from source (development)

```bash
uv venv && uv pip install -e '.[login,dev]'   # [login] adds Playwright, [dev] adds test/lint tools
```

## Authentication

### Browser login (recommended)

```bash
trackman-mcp login            # opens a browser; sign in once with email+password
```

A browser window opens (an **isolated** profile, not your normal Chrome). Sign
in once; the MCP captures the access token and caches it at
`~/.trackman-mcp/token.json` (mode `0600`). The session persists, so to refresh
later (tokens last ~7 days) just run:

```bash
trackman-mcp login --headless   # silent refresh, no window
```

If you don't have Google Chrome installed, the browser flow falls back to
Playwright's bundled Chromium — install it once with `playwright install chromium`.

### Keep it fresh automatically (optional)

Schedule the headless refresh so you never think about tokens (twice weekly,
margin on the ~7-day token). Portable — paths are derived at install time:

```bash
scripts/install-refresh-schedule.sh dry-run    # preview what gets installed
scripts/install-refresh-schedule.sh            # install (macOS launchd / Linux cron)
scripts/install-refresh-schedule.sh uninstall  # remove
```

Run a headed `trackman-mcp login` **once** first to establish the browser
session; the schedule then refreshes it silently. Windows: schedule
`scripts/refresh-token.sh` via Task Scheduler.

### Alternative: paste a token manually

Set `TRACKMAN_TOKEN` (it overrides the cache). Get it from
portal.trackmangolf.com → DevTools → Network → a `graphql` request → the
`Authorization` header value. See `.env.example`.

## Run

```bash
trackman-mcp                              # start the MCP (stdio)
uv run python scripts/validate.py         # validate stats coverage (uses cached token)
```

## MCP tools

All tools return **raw data only**; the skills interpret it.

**Data (read-only):** `authenticate` · `get_profile` · `get_handicap` ·
`list_sessions` · `get_session` · `get_course_rounds` · `get_club_stats` ·
`get_shot_data` · `get_activity_summary`

**Auth:** `login`

**Session analysis (local store, deterministic):** `analyze_and_store_session` ·
`list_session_analyses` · `get_session_analysis`

**Training-plan memory:** `save_training_plan` · `get_next_training` ·
`list_training_plans` · `mark_training_done` · `verify_training_progress`

**Visualization:** `build_visualization` (self-contained animated HTML artifact)

See [`CLAUDE.md`](./CLAUDE.md) for the full table and backing GraphQL.

## Skills

Bundled under [`skills/`](./skills) (installed automatically with the plugin):

- `trackman-api-discovery` — reverse-engineer the portal's API (Phase 0)
- `trackman-stats-analysis` — diagnose weaknesses from the data
- `golf-coaching` — turn the diagnosis into an actionable practice plan
- `drill-library` — curated drills + vetted YouTube links, plus live search
- `trackman-session-analyzer` — ingest + normalize recent sessions (runs forked)
- `trackman-visualizer` — animate a diagnosis as an HTML artifact

## Development

```bash
uv run pytest        # tests
uv run ruff check    # lint
uv run mypy          # type-check
```

## License

[MIT](./LICENSE)
