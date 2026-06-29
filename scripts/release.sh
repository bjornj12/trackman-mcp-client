#!/usr/bin/env bash
#
# release.sh — cut a release across every channel with one command.
#
#   1. bump the version in pyproject.toml, server.json, and the plugin manifests
#   2. run the quality gate (ruff + mypy + pytest) so a broken release can't ship
#   3. commit, tag vX.Y.Z, and push  -> triggers the PyPI publish workflow (OIDC)
#   4. wait for the workflow; pause for your one-click approval of the `pypi`
#      environment (or auto-approve with --auto-approve)
#   5. wait until PyPI actually serves the new version
#   6. publish server.json to the MCP Registry (mcp-publisher)
#
# The Claude Code plugin needs no publish step — it tracks main and the version
# bump in plugin.json signals the new release.
#
# Usage:
#   scripts/release.sh <X.Y.Z | patch | minor | major> [--auto-approve] [--dry-run]
#
set -euo pipefail

REPO="bjornj12/trackman-mcp-client"
PKG="trackman-mcp"
WORKFLOW="publish.yml"
ENVIRONMENT="pypi"

cd "$(dirname "$0")/.."

err()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }

# --- parse args ------------------------------------------------------------
BUMP="" ; DRY_RUN=0 ; AUTO_APPROVE=0
for a in "$@"; do
  case "$a" in
    --dry-run)      DRY_RUN=1 ;;
    --auto-approve) AUTO_APPROVE=1 ;;
    -*)             err "unknown flag: $a" ;;
    *)              [ -z "$BUMP" ] || err "unexpected extra arg: $a" ; BUMP="$a" ;;
  esac
done
[ -n "$BUMP" ] || err "usage: scripts/release.sh <X.Y.Z|patch|minor|major> [--auto-approve] [--dry-run]"

# --- required tools --------------------------------------------------------
for t in git gh uv curl python3; do command -v "$t" >/dev/null || err "missing required tool: $t"; done

# --- compute versions ------------------------------------------------------
CUR=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
NEW=$(python3 - "$CUR" "$BUMP" <<'PY'
import re, sys
cur, bump = sys.argv[1], sys.argv[2]
if re.fullmatch(r"\d+\.\d+\.\d+", bump):
    print(bump); raise SystemExit
major, minor, patch = (int(x) for x in cur.split("."))
if bump == "major":   major, minor, patch = major + 1, 0, 0
elif bump == "minor": minor, patch = minor + 1, 0
elif bump == "patch": patch += 1
else: sys.exit(f"not a version or patch|minor|major: {bump!r}")
print(f"{major}.{minor}.{patch}")
PY
)
[ "$NEW" != "$CUR" ] || err "new version equals current ($CUR) — nothing to release"
info "release: $CUR -> $NEW"

# bump every version-bearing file; assert the expected number of hits so a file
# that drifts in shape fails loudly instead of silently going un-bumped.
bump_versions() {  # $1 = apply|preview
  python3 - "$CUR" "$NEW" "$1" <<'PY'
import io, re, sys
cur, new, mode = sys.argv[1], sys.argv[2], sys.argv[3]
edits = [
    ("pyproject.toml",                  re.compile(r'(?m)^version = "%s"'   % re.escape(cur)), 'version = "%s"'   % new, 1),
    ("server.json",                     re.compile(r'"version": "%s"'       % re.escape(cur)), '"version": "%s"' % new, 2),
    (".claude-plugin/plugin.json",      re.compile(r'"version": "%s"'       % re.escape(cur)), '"version": "%s"' % new, 1),
    (".claude-plugin/marketplace.json", re.compile(r'"version": "%s"'       % re.escape(cur)), '"version": "%s"' % new, 1),
]
for path, pat, repl, want in edits:
    text = io.open(path, encoding="utf-8").read()
    out, n = pat.subn(repl, text)
    if n != want:
        sys.exit(f"{path}: expected {want} version occurrence(s) of {cur}, found {n}")
    if mode == "apply":
        io.open(path, "w", encoding="utf-8").write(out)
    print(f"  {path}: {n}x  {cur} -> {new}")
PY
}

# --- dry run ---------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] version changes that WOULD be made:"
  bump_versions preview
  info "[dry-run] then: gate (ruff/mypy/pytest) -> commit -> tag v$NEW -> push"
  info "[dry-run] then: wait for PyPI publish workflow ($([ "$AUTO_APPROVE" -eq 1 ] && echo auto-approve || echo manual approval)) -> wait for PyPI -> mcp-publisher publish"
  ok "[dry-run] no changes made"
  exit 0
fi

# --- preconditions for a real release --------------------------------------
BR=$(git rev-parse --abbrev-ref HEAD)
[ "$BR" = "main" ] || err "must be on main to release (current: $BR)"
[ -z "$(git status --porcelain)" ] || err "working tree not clean — commit or stash first"
! git rev-parse "v$NEW" >/dev/null 2>&1 || err "tag v$NEW already exists locally"
[ -z "$(git ls-remote --tags origin "refs/tags/v$NEW")" ] || err "tag v$NEW already exists on origin"

# --- bump + gate -----------------------------------------------------------
info "bumping versions"; bump_versions apply
info "running quality gate (ruff + mypy + pytest)"
uv sync --extra dev >/dev/null
uv run ruff check src tests
uv run mypy
uv run pytest -q
ok "gate passed"

# --- commit, tag, push -----------------------------------------------------
info "commit + tag + push"
git add -A
git commit -m "Release v$NEW"
git tag -a "v$NEW" -m "$PKG $NEW"
git push origin main
git push origin "v$NEW"
SHA=$(git rev-parse HEAD)
ok "pushed v$NEW — PyPI publish workflow triggered"

# --- wait for the publish workflow -----------------------------------------
info "locating the publish run…"
RUN_ID=""
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list --workflow "$WORKFLOW" --json databaseId,headSha \
            -q "[.[]|select(.headSha==\"$SHA\").databaseId][0]" 2>/dev/null || true)
  [ -n "$RUN_ID" ] && [ "$RUN_ID" != "null" ] && break
  RUN_ID=""; sleep 3
done
[ -n "$RUN_ID" ] || err "couldn't find a publish run for $SHA — check the Actions tab"
RUN_URL="https://github.com/$REPO/actions/runs/$RUN_ID"
info "run: $RUN_URL"

prompted=0
for _ in $(seq 1 300); do          # ~30 min ceiling
  STATUS=$(gh run view "$RUN_ID" --json status -q .status 2>/dev/null || echo "")
  [ "$STATUS" = "completed" ] && break
  PENDING=$(gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" -q 'length' 2>/dev/null || echo 0)
  if [ "${PENDING:-0}" -gt 0 ] && [ "$prompted" -eq 0 ]; then
    if [ "$AUTO_APPROVE" -eq 1 ]; then
      info "auto-approving the '$ENVIRONMENT' deployment"
      ENV_ID=$(gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" -q '.[0].environment.id')
      gh api -X POST "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
        -F "environment_ids[]=$ENV_ID" -f state=approved -f comment="release v$NEW" >/dev/null
    else
      printf '\033[33m⏸  ACTION NEEDED: approve the "%s" deployment to publish:\n    %s\033[0m\n' "$ENVIRONMENT" "$RUN_URL"
      command -v open >/dev/null && open "$RUN_URL" >/dev/null 2>&1 || true
    fi
    prompted=1
  fi
  sleep 6
done
CONCLUSION=$(gh run view "$RUN_ID" --json conclusion -q .conclusion 2>/dev/null || echo "")
[ "$CONCLUSION" = "success" ] || err "publish workflow did not succeed (conclusion: ${CONCLUSION:-timeout}) — see $RUN_URL"
ok "PyPI publish workflow succeeded"

# --- wait for PyPI to serve the version ------------------------------------
info "waiting for $PKG $NEW to appear on PyPI…"
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://pypi.org/pypi/$PKG/$NEW/json")
  [ "$code" = "200" ] && { ok "PyPI is serving $NEW"; break; }
  sleep 6
done

# --- MCP Registry ----------------------------------------------------------
if command -v mcp-publisher >/dev/null; then
  info "publishing server.json to the MCP Registry"
  mcp-publisher publish \
    || err "mcp-publisher failed. If it's an auth error: 'mcp-publisher login github', then 'mcp-publisher publish'"
  ok "MCP Registry updated"
else
  info "mcp-publisher not installed — skipping registry. To finish:"
  echo "    brew install mcp-publisher && mcp-publisher login github && mcp-publisher publish"
fi

echo
ok "released v$NEW"
echo "    PyPI:    https://pypi.org/project/$PKG/$NEW/"
echo "    Install: uvx $PKG"
echo "    Plugin:  tracks main (plugin.json now v$NEW)"
