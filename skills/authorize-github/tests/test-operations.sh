#!/usr/bin/env bash
# Offline synthetic requests; no remote or credential store.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SKILL_DIR/tests/operations-fixture.sh"
. "$SKILL_DIR/scripts/items.sh"
GITHUB_USE_DIR="$SKILL_DIR"
_github_config_ready
mkdir -p "$work/output/issues"
printf 'previous-index' > "$work/output/issues.md"
printf 'previous-detail' > "$work/output/issues/previous.md"
for mode in list-failure detail-failure capped; do
    if _github_export_items example issue "$work/output" > "$work/out" 2> "$work/error"; then echo "FAIL: $mode reported success"; exit 1; fi
    [ "$(cat "$work/output/issues.md")" = previous-index ]
    [ "$(cat "$work/output/issues/previous.md")" = previous-detail ]
done
mode=success
_github_export_items example issue "$work/output" > /dev/null
[ -f "$work/output/issues/42.md" ] && [ ! -e "$work/output/issues/previous.md" ]
mode=empty
_github_export_items example issue "$work/output" > /dev/null
[ ! -e "$work/output/issues.md" ] && [ ! -e "$work/output/issues" ]
mode=success
jq '.repos[0].projects[0].name="../outside"' "$work/github-repos.json" > "$work/invalid.json"
GITHUB_REPOS_PATH=invalid.json
if _github_config_ready >/dev/null 2>&1; then echo 'FAIL: unsafe export name accepted'; exit 1; fi
unset GITHUB_REPOS_PATH
GITHUB_ENV_FILE="$work/.env"
printf '%s\n' 'GH_TOKEN="$(touch must-not-exist)"' 'GITHUB_REPOS_PATH=github-repos.json' > "$GITHUB_ENV_FILE"
(cd "$work"; unset GH_TOKEN; _github_load_env; [ "$GH_TOKEN" = '$(touch must-not-exist)' ]; [ ! -e must-not-exist ])
# If publication stops after moving an old artifact aside, the EXIT cleanup restores it.
mkdir -p "$work/interrupted"
printf 'keep-me' > "$work/interrupted/issues.md"
if (
    _github_export_begin "$work/interrupted"
    GITHUB_EXPORT_PENDING=issues.md
    mv "$work/interrupted/issues.md" "$GITHUB_EXPORT_WORK/previous/issues.md"
    exit 1
); then echo 'FAIL: interrupted publication returned success'; exit 1; fi
[ "$(cat "$work/interrupted/issues.md")" = keep-me ]
printf 'ok: interrupted publication restores its pending artifact\n'
