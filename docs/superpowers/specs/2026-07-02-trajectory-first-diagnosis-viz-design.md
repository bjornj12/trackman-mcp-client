# Trajectory-First Diagnosis Visualization — Design

*2026-07-02*

## Problem

The previous direction — animated stick-figure drill comparisons for the at-home
routine (`worktree-multi-angle-drill-viz`) — failed in practice. The branch's own
history shows the fight: several rounds of legibility fixes (elbow joints, facing
markers, damping), then a mid-branch retreat that replaced the animated character
with plain data bars. Hand-authored body kinematics never became readable. That
branch is **abandoned unmerged**.

The pivot: stop animating an imaginary body, and instead animate **what the
golfer's ball is actually doing** — the real, measured Trackman flight — then
explain the fault it shows and link straight to the exercises (range *and*
at-home) that fix it.

Two concrete gaps in what ships today:

1. `build_visualization`'s page (`src/trackman_mcp/visualize.py`) only draws a
   **top-down** flight tracer whose height dimension is invented (a flat bezier).
   The richest flight data the API returns — `maxHeight`, `landingAngle`,
   `hangTime`, per-shot `launchAngle` — is never rendered, and per-shot shape is
   collapsed to one averaged curve plus landing dots.
2. The "practice plan" section is a flat list, one optional link per block, with
   no home-vs-range distinction — while the actual ask is *multiple* vetted
   links per fix, split by where the golfer is practicing.

A server-side gap feeds gap 1: only `RangePracticeActivity` strokes fetch
`maxHeight`/`hangTime` in `GET_SESSION` (`queries.py`); the six other session
kinds omit them (and several omit `launchDirection`) even though the API exposes
them (`docs/trackman-api.md` lines 124/142).

## Goals

- Animate the **real measured flight** per shot: a new side-view (height
  profile) hero panel reconstructed from `launchAngle` / `maxHeight` /
  `landingAngle` / `carry` / `hangTime`, plus the existing top-down shape view
  upgraded to show every shot's curved path, both views animated in sync.
- Keep the explanation layer: deterministic physics captions ("path −5.2°
  out-to-in, face 4° open to path → starts left, curves right") computed from
  the same numbers, with the coaching `diagnosis` text still supplied by skills.
- Replace the flat plan list with a **Fix it** section: each block tagged
  `where: "range" | "home"`, each carrying **multiple** links, rendered as two
  groups ("At the range" / "At home — no ball").
- Fetch the trajectory fields for **all** session kinds in `GET_SESSION`.
- Rewire the four skills that currently point at freehand/stick-figure
  animation (`trackman-visualizer`, `golf-practice-at-home`, `golf-coaching`,
  `drill-library`) — SKILL.md **and** PROMPT.md in lockstep (Desktop only sees
  PROMPT.md via `prompts.py`).

## Non-goals

- No stick figures, no body kinematics, no `drill`/fragment mode — the
  abandoned branch's approach is explicitly dropped, not ported.
- No 3D/isometric scene, no external rendering libraries — stays one
  self-contained HTML file, pure canvas/JS, zero dependencies.
- No fabricated numbers: a shot missing `maxHeight` gets no apex label, and a
  shot missing height data entirely falls back gracefully (below) rather than
  inventing a value.
- The at-home routine itself stays (`golf-practice-at-home`) — only its
  per-drill animation requirement is removed; drills are presented with feel
  cues and multiple video links instead.

## Approaches considered

- **A — trajectory-first upgrade of the existing page (chosen).** Add the
  side-view hero, upgrade the top-down panel to per-shot tracers, group the fix
  links. Builds on a renderer that already works, keeps the deterministic/
  testable/no-deps properties, additive schema.
- **B — pseudo-3D isometric scene.** One "range camera" view with height and
  curve in a single projection. More spectacular, but depth cues on a flat
  canvas are exactly the kind of hand-tuned rendering that just failed on the
  drill branch; harder to test, harder to read small angle differences.
- **C — links-only minimal change.** Just add the grouped multi-link section.
  Cheapest, but ignores the core ask (animate what's actually happening).

## Page layout (one full-width artifact, dark theme, existing visual language)

```
┌───────────── FLIGHT — side view (hero, full width, animated) ─────────────┐
│ faint arcs: every shot · bright animated arc + ball: representative shot  │
│ ground line, distance grid; carry point + dotted roll to total            │
│ labels (only where measured): launch 12.3° · apex 28 m · land 38° · 5.9 s │
├──────── SHAPE — top-down (animated) ────────┬──── SWING PATH — why ───────┤
│ faint curved tracers: every shot            │ (existing panel, unchanged) │
│ animated representative ball, synced w/hero │                             │
├──────────────────── TARGETS — bars vs plan (existing) ────────────────────┤
├─ FIX IT ─ At the range: block ▸ links… · At home — no ball: block ▸ links…┤
└──────────────────────────── [ ↻ Replay ] ─────────────────────────────────┘
```

- **Side view (new hero).** X = downrange meters, Y = height meters. Each
  shot's arc is a piecewise cubic Bézier passing **exactly** through (0, 0),
  the apex (x_apex, `maxHeight`), and (`carry`, 0); end tangents match
  `launchAngle` (up) and `landingAngle` (down); apex tangent horizontal.
  x_apex = carry · tan(landing) / (tan(launch) + tan(landing)), clamped to
  [0.4, 0.75]·carry (real flights peak past midpoint; the clamp guards odd
  data). If `total` > `carry`, a dotted ground segment marks the roll. All
  shots draw as faint static arcs; the representative shot (per-field mean,
  as today) animates with a ball + trail.
- **Top-down (upgraded).** Every shot gets its own faint curved tracer (from
  its `launchDirection`/`totalSide`/`curve`), not just a landing dot; the
  representative shot animates. Existing handedness convention (`sx`) is kept.
- **Sync.** One clock drives both views: the ball is at the same flight
  fraction t in each. Animation duration scales with the representative
  `hangTime` (missing → fixed default), so a wedge floats and a driver flies.
  The single Replay button restarts everything (existing pattern).
- **Captions.** The existing deterministic "why it curves" text stays and gains
  the vertical story where measured: e.g. "apex 28 m and landing at 38° —
  carry ends steeply" — measurement-speak computed from numbers, no coaching
  verdicts (those arrive via `diagnosis`, authored by the skill).

### Graceful degradation (no invented numbers)

- `maxHeight` missing, `launchAngle` present → arc shape drawn from launch/
  landing tangents and carry alone (apex falls where the tangents put it), **no
  apex label**.
- No height fields at all → side-view hero hidden; page renders as today.
- `hangTime` missing → default duration, no seconds label.
- `landingAngle` missing → descent mirrors launch tangent, no land label.

## Data schema (additive; all existing fields unchanged)

```jsonc
{
  // shots gain optional vertical fields (renderer uses them when present):
  "shots": [{ "launchDirection": deg, "launchAngle": deg, "carry": m,
              "total": m, "totalSide": m, "curve": m, "maxHeight": m,
              "landingAngle": deg, "hangTime": s, "club": str }],
  // blocks gain a location tag and multiple links:
  "blocks": [{ "name": str, "detail": str, "goal": str,
               "where": "range" | "home",          // omitted → "range"
               "links": [{ "label": str, "url": str }],  // 1..n
               "link": str }]                       // legacy, still honored
}
```

Validation follows repo convention (fail loudly): a `links` entry that is not
`{label, url}` is a clear tool error, not a silently skipped item. Every URL
passes the existing `safeHref` gate (http/https only); all text lands via
`textContent` (existing injection-safety pattern, extended tests below).

## Server-side query fix

`GET_SESSION` (`queries.py`): add `launchDirection maxHeight hangTime` to the
measurement selection of every session kind that omits them
(FindMyDistance, MapMyBag, ShotAnalysis, Simulator, VirtualRange, generic
Session; CoursePlay hole shots gain `landingAngle maxHeight` where the API
allows). Confirm each addition against the live schema during implementation —
any field a kind doesn't support is dropped for that kind, not guessed.
`SESSION_MEASUREMENTS` (used by `training_plan verify`) is untouched.

## Skill rewiring (SKILL.md + PROMPT.md together, every time)

- **`trackman-visualizer`** — becomes the trajectory-page skill: gather the
  session's real shots (all fields above), pass the skill-authored `diagnosis`,
  targets, and `blocks` with `where` + multiple `links`, call
  `build_visualization`, emit the returned HTML as an artifact. All "use the
  client's own HTML/SVG artifact capability", "switch camera (top-down /
  face-on / side)", and per-drill freehand-animation instructions are removed.
- **`golf-coaching`** — Prescribe step now builds `blocks` in both flavors
  (range + home) with 2–3 vetted links each, sourced from `drill-library`
  (plus its live-search procedure for fresh videos). "Never give text-only
  coaching" now means: always ship the trajectory page.
- **`drill-library`** — each curated drill row gains a `where` tag
  (`range`/`home`) and keeps/extends its vetted links so a fix can cite
  multiple videos. The "best shown animated one drill at a time" pointer is
  replaced with a pointer at the Fix-it section of the trajectory page.
- **`golf-practice-at-home`** — step 4's per-drill animation requirement is
  dropped; each drill in the routine is presented as feel cue + reps + its
  multiple links. Everything else (routine building, plan saving) unchanged.

## Testing & verification

Extends `tests/test_visualize.py` (existing 5 tests keep passing):

- Side-view hero renders when height fields are present; absent when none are.
- No-fabrication tests: missing `maxHeight`/`hangTime`/`landingAngle` produce
  no corresponding label text in the HTML.
- Per-shot tracers: the embedded page JSON carries all N shots with their
  vertical fields intact (canvas output itself isn't inspectable from pytest;
  the headless render check below covers pixels).
- Injection safety for the new `links` arrays (hostile label/url) and the
  legacy single `link` fallback; `where` grouping renders both group headers
  only when both kinds exist.
- Handedness regression for the upgraded top-down tracers.
- Malformed `links` entry → clear error from `build_visualization`.
- `scripts/check-visualization.py --demo` updated so the demo payload exercises
  the new fields; headless render check stays green.
- Manual Desktop pass (same gate as the previous design): the
  `trackman-golf-dev` entry in Claude Desktop's config points at this checkout;
  confirm the artifact renders and the updated prompts read correctly there.

## Error handling

Repo convention, fail loudly: malformed `blocks`/`links` → tool error naming
the offending entry; unknown `where` value → tool error listing valid values;
missing optional measurement fields → degrade per the table above, never
invent a number.
