# Multi-Angle Drill Visualization — Design

*2026-06-30*

## Problem

The per-drill diagram shown during an at-home no-ball routine (e.g. "Pump-and-drop")
is a single vertical line on a top-down schematic, labeled "over the top" / "inside
path". An amateur golfer has no idea what they're looking at — there's no body, no
club, no sense of which way is "up" or "behind," and no motion to follow.

Investigation found two compounding causes:

1. **`build_visualization`'s actual rendering** (`src/trackman_mcp/visualize.py`) only
   ever draws a top-down ball-flight panel and a top-down swing-path panel (a single
   line representing `clubPath`/`faceAngle` at impact). No face-on or down-the-line
   view exists in code, despite being mentioned as a future option in skill prompts.
2. **The per-drill card shown in practice** (title, progress dots, feel-cue quote,
   reps/club/order, Watch-the-drill link, the diagram itself) is *not* produced by
   `build_visualization` at all. `trackman-visualizer/PROMPT.md` instructs the model
   to use "the client's own HTML/SVG artifact capability for a richer per-drill
   animation" — i.e. freehand-author the whole thing each conversation, with no
   concrete spec for what the diagram should contain. That's why the result is
   inconsistent and, in this case, illegible.

A further wrinkle: **"pump-and-drop" is a transition/sequencing drill** — it's about
how the hands and trail elbow move during the downswing. There is no number in the
existing data schema (`clubPath`, `faceAngle` are impact-moment-only) that can
represent that motion. A single line, from any camera angle, can never show it.

## Goals

- Replace the single top-down line with an animated **multi-angle stick-figure**
  view (down-the-line + face-on) that shows a current ("your move," red) vs target
  ("target move," green) comparison, for any drill in `drill-library`'s
  `at-home-no-ball` set — including sequencing drills with no numeric equivalent.
- Make the diagram **deterministic and testable**, matching the rest of
  `visualize.py`, instead of freehand-authored per conversation.
- Leave the existing ball-flight / swing-path / target-bar page, and the existing
  per-drill card chrome (title, progress, feel cue, reps, links, prev/next),
  untouched.

## Non-goals

- Photorealistic body rendering, 3D, or any external rendering library — stays
  inline SVG + CSS, zero dependencies, consistent with the rest of the file.
- Per-customer/AI-improvised body kinematics — fault shapes are a small, hand-
  authored, reviewed library, not invented at generation time.
- Changing the ball-flight or target-bar panels.

## Architecture

A new module, `src/trackman_mcp/swing_archetypes.py`, holds the fault-pose library
as pure data plus small geometry/projection helpers. `visualize.py` is otherwise
unchanged: when the caller's `data` includes a `drill` key, the renderer takes a new
code path that emits a **fragment** instead of the existing full-page document.

`build_visualization`'s tool contract:

- No `drill` key → today's behavior, byte-for-byte (full standalone page: ball
  flight + swing path + target bars). Existing callers and tests are unaffected.
- `drill` key present → returns a fragment (`<div>` containing inline `<svg>` +
  scoped `<style>` + a small inline `<script>` for the shared Replay control and
  phase animation), sized to drop into the caller's own card markup — not a full
  `<html>` document. The tool's `render_as` field distinguishes the two
  (`"text/html artifact"` vs `"text/html fragment"`).

This keeps the deterministic/local/no-network properties intact and reuses the
existing injection-safety pattern (`_json_for_script`, `safeHref`, textContent-only
DOM writes) for any new string fields.

## Fault archetype library

Each of the 7 `at-home-no-ball` drills in `drill-library` maps to one named
archetype. An archetype is a pair of pose tracks — `current` (red, the fault) and
`target` (green, correct) — each a list of 5 keyframes (address, top, transition,
impact, finish). A keyframe is a small set of normalized parameters, not pixel
coordinates:

```python
{
  "shoulder_turn": 0.0-1.0,      # rotation progress
  "hip_turn": 0.0-1.0,
  "arm_plane": deg,              # angle of the arm line off the spine
  "club_plane": deg,             # angle of the club line off the arm
  "wrist_hinge": 0.0-1.0,
  "trail_elbow": "connected" | "disconnected",  # drives a visible elbow-to-hip gap
}
```

The renderer projects these same parameters into both camera angles (down-the-line,
face-on) via two small trig functions. One archetype definition drives both views —
geometry is never hand-authored twice per fault.

| Archetype id | Fault (current) | Target | Drills it serves |
|---|---|---|---|
| `over_the_top` | steep out-to-in, arm-led | shallow, in-to-out | Wall/fence |
| `early_transition` | hands/arms fire first from the top, trail elbow flies away | lower body leads, elbow stays tucked, club drops "into the slot" | **Pump-and-drop**, Towel/headcover |
| `disconnected_sequencing` | arms detached from torso through transition | lead-foot step initiates, arms stay passive | Step-through |
| `open_face` | face open relative to path at impact | face square to path | Split-hands release, Mirror face check |
| `inside_closing` | path too far in-to-out with a closing face | neutral path, square face | Trail-arm-only throws |

Where real numeric data exists (`swing.clubPath` / `swing.faceAngle` from an actual
session), it overrides the archetype's hardcoded impact-keyframe angles for
`current` — so a personalized diagnosis (e.g. "your path is -6.2°") still renders
the real number, while the rest of the motion (backswing/transition/finish shape)
comes from the matched archetype. When no real numbers are passed (the at-home
no-ball case — address-only rehearsal, no shots), the archetype's own canned
current/target angles are used as-is, and no fabricated degree label is shown for
phases that have no numeric equivalent (e.g. the pump-and-drop transition).

## Rendering & layout

Each camera angle is one `<svg>` containing a fixed reference frame (ground line, a
faint target-line tick, a simple body silhouette in neutral address pose for
orientation) plus two animated stick figures overlaid — current (red strokes) and
target (green strokes) — both driven by the same 5-keyframe timeline via CSS
`@keyframes` (one keyframe per phase; the browser interpolates between).

Down-the-line and face-on are stacked as two rows, each row split into
current | target columns (2×2 grid total). A single shared Replay button restarts
all four animations in lockstep — matching the existing single-Replay-button
pattern used by the ball-flight/swing-path page.

```
┌─────────────── DOWN-THE-LINE ───────────────┐
│   current (red)        target (green)        │
│   [stick figure]        [stick figure]        │
├─────────────────  FACE-ON  ──────────────────┤
│   current (red)        target (green)        │
│   [stick figure]        [stick figure]        │
└───────────────────────────────────────────────┘
            [ ↻ Replay ]   (shared control)
```

Down-the-line projects `arm_plane` / `club_plane` as their actual angle off
vertical — this is the angle that makes "steep vs shallow" and "over the top"
visible. Face-on projects the same parameters flattened to lateral position only —
this is what makes path direction and the elbow-connection gap visible. Both views
read off the *same* keyframe parameters; there is no per-angle authoring.

Labels keep the existing visual language: red = "your current move," green =
"target move," with degree annotations only where real numbers exist.

## Data schema & tool contract

New optional top-level `drill` key on the existing `build_visualization(data)`
input; all existing fields (`title`, `subtitle`, `diagnosis`, `handedness`, `shots`,
`swing`, `targets`, `blocks`) are unchanged and ignored in fragment mode (ball
flight / target bars don't apply to a single-drill view):

```jsonc
{
  "drill": {
    "archetype": "early_transition",   // required, one of the 5 known ids
    "name": "Pump-and-drop"            // optional, label only
  }
}
```

Validation: an unknown `archetype` id is a clear tool error
(`"unknown archetype 'x', expected one of: ..."`), not a silent blank render —
consistent with this repo's "fail loudly" convention (see `CLAUDE.md`).

## Skill wiring

This is what actually fixes the illegible card shown in practice today. Both
`trackman-visualizer/SKILL.md` (Claude Code) **and** `trackman-visualizer/PROMPT.md`
(served as an MCP prompt to every other client, including Claude Desktop — see
below) currently point at "the client's own HTML/SVG artifact capability" /
"switch camera (top-down / face-on / side)" for the "one drill at a time" case.
Both get the same edit: call `build_visualization({..., drill: {archetype, name}})`
and embed the returned fragment inside the existing per-drill card markup (title,
progress dots, feel-cue quote, reps/club/order, Watch-the-drill link, Prev/Next —
all untouched), instead of freehand-authoring the diagram. `golf-practice-at-home`'s
`SKILL.md` and `PROMPT.md` (step 4) get the same pointer. `drill-library`'s curated
table (in both files) gains one new column, `archetype`, so the mapping from drill →
archetype id is explicit data rather than inferred by the model each time.

## Desktop compatibility & verification

This project ships to Claude Desktop as a `.mcpb` extension (`mcpb/manifest.json`),
and skill content reaches Desktop **only** through `prompts.py`
(`register_skill_prompts` → `load_skills()`), which reads each skill's `PROMPT.md`
— never `SKILL.md` and never the `skills/` directory directly. Desktop has no
skill-dispatch/subagent system; a user invokes the MCP prompt (e.g.
`trackman-visualizer`) from the prompt picker and the model follows that body
directly. So:

- Editing only `SKILL.md` would silently not reach Desktop users — both files must
  change together (covered above).
- `swing_archetypes.py` is a plain module under `src/trackman_mcp/`; no manifest or
  packaging change is needed (the wheel's existing `force-include` of `skills/`
  already covers the updated `PROMPT.md` files).
- The released `.mcpb` extension installs `trackman-mcp` **from PyPI at runtime**
  (`mcpb/pyproject.toml`: `trackman-mcp[login]>=0.3.1`) — it does not bundle local
  source. Rebuilding/reinstalling the `.mcpb` locally would therefore still test
  the last published release, not this change. It is not a valid verification path
  until a real release is cut, and is out of scope here.
- **Verification gate before this is considered done:** a `trackman-golf-dev` entry
  now exists in `~/Library/Application Support/Claude/claude_desktop_config.json`,
  pointing at this checkout (`uv run --directory <repo> trackman-mcp` — confirmed
  importable). The closing step of the implementation plan is: restart Claude
  Desktop and manually confirm:
  1. `build_visualization` called with a `drill` payload returns valid fragment
     HTML and renders as an interactive artifact in a Desktop chat (not just in
     Claude Code).
  2. The `trackman-visualizer` and `golf-practice-at-home` prompts appear in
     Desktop's prompt picker and, when invoked, produce a per-drill card using the
     new diagram exactly as in Claude Code.
  This is a manual check (Desktop is a native GUI app outside automated reach) and
  is not something `pytest` alone can confirm.

## Testing & error handling

Extends the existing `tests/test_visualize.py` pattern (currently 5 tests covering
injection-safety, self-containment, handedness):

- One test per archetype id confirming the fragment renders, contains both
  `current`/`target` SVGs, and is self-contained (no external URLs) — same
  injection-safety bar as today.
- A test for the unknown-archetype error path.
- A test confirming `drill`-less calls produce byte-identical output to today
  (regression guard for the existing ball-flight/swing-path/target-bar page).
- A handedness regression test for the new archetype renderer, mirroring the
  existing RH/LH test for the swing-path panel.
- `scripts/check-visualization.py` (the Playwright headless render check) gains a
  `--demo-drill <archetype>` mode to visually spot-check a rendered fragment, same
  as the existing `--demo` page does today.

Error handling follows the repo convention: unknown archetype id → clear tool
error, not a blank/guessed render. Missing `swing` numbers in drill mode →
archetype's own canned numbers render with no degree label, rather than inventing
one.
