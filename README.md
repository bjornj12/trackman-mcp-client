# trackman-mcp-client

An MCP server that logs into **Trackman Golf** with your own account and exposes
your stats — course rounds, practice sessions, shot-level launch-monitor data,
club gapping, and handicap — as MCP tools. On top of that, a set of Claude
**skills** act as your golf coach: they diagnose your weaknesses and hand you a
specific practice plan with drills and YouTube links for your next session.

## Design boundary

- **MCP server** = raw data fetch + auth only. No opinions.
- **Skills** = all the coaching (analysis, plans, drills).

See [`CLAUDE.md`](./CLAUDE.md) for the full architecture, the build phases, and
the auth/secret-handling rules.

## Status

Scaffolding only (docs + skills). **Phase 0** — discovering Trackman's private
golf API — comes first; see [`docs/trackman-api.md`](./docs/trackman-api.md) and
the `trackman-api-discovery` skill.

## Skills

- `trackman-api-discovery` — reverse-engineer the portal's API (Phase 0)
- `trackman-stats-analysis` — diagnose weaknesses from the data
- `golf-coaching` — turn the diagnosis into an actionable practice plan
- `drill-library` — curated drills + vetted YouTube links, plus live search
