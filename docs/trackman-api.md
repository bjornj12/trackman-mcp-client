# Trackman Golf API — Discovered Endpoints

> **Status: TODO (Phase 0 not yet done).** This file is the output of the
> `trackman-api-discovery` skill. Trackman has no public golf API — fill this in
> by observing the real web portal's network calls. The Phase 1 MCP server is
> built against this document.
>
> **Never paste real tokens, cookies, passwords, or emails here.** Redact all
> secrets: `"token": "<REDACTED>"`.

## Authentication

- **Identity provider / login URL**: _TODO_ (Trackman uses an identity server,
  e.g. `login.trackmangolf.com` — confirm)
- **Flow type**: _TODO (OAuth2/OIDC? password grant? cookie session?)_
- **Token type & location**: _TODO (bearer JWT in `Authorization` header? cookie?)_
- **How attached to data requests**: _TODO_
- **Refresh / expiry**: _TODO_
- **Env vars the MCP will use**: `TRACKMAN_USERNAME`, `TRACKMAN_PASSWORD`
  and/or `TRACKMAN_TOKEN` _(confirm which)_

## API style

- **REST or GraphQL?**: _TODO_ — if GraphQL, record the endpoint (e.g.
  `/graphql`), operation names, and example queries/variables below.
- **Base URL(s)**: _TODO_

## Endpoints

For each: method, URL, params, required headers, scrubbed example response, and
the fields that matter. Map each to a planned MCP tool.

### Profile / handicap → `get_profile`
- **Method / URL**: _TODO_
- **Key fields**: handicap, name, player id
- **Example (scrubbed)**: _TODO_

### Sessions list → `list_sessions`
- **Method / URL**: _TODO_
- **Filters**: date range, type (practice vs round)
- **Key fields**: session id, date, type, location, summary
- **Example (scrubbed)**: _TODO_

### Session detail → `get_session`
- **Method / URL**: _TODO_
- **Key fields**: per-shot launch-monitor metrics
- **Example (scrubbed)**: _TODO_

### Course rounds / scorecards → `get_course_rounds`
- **Method / URL**: _TODO_
- **Key fields**: per-hole score, fairways/greens hit, putts
- **Example (scrubbed)**: _TODO_

### Club stats / gapping → `get_club_stats`
- **Method / URL**: _TODO_
- **Key fields**: per-club avg carry, total, ball speed, spin, dispersion
- **Example (scrubbed)**: _TODO_

### Shot data → `get_shot_data`
- **Method / URL**: _TODO_
- **Key fields**: ball speed, club speed, smash, launch angle, spin rate,
  carry, total, side/curve, landing angle
- **Example (scrubbed)**: _TODO_

## Gaps & findings

_TODO — list anything we want but found no endpoint for, and any rich endpoint
worth adding a tool for. Reconcile the planned-tool table in `CLAUDE.md`._
