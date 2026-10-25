#!/usr/bin/env bash
##- Synthetic gh responses; no remote or credential store is accessed.
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_AUTH_DIR="$ROOT/skills/authorize-github"
GITHUB_PYTHON="${GITHUB_TEST_PYTHON:-python3}"
. "$GITHUB_AUTH_DIR/scripts/client.sh"
for domain in issues pull-requests discussions projects; do . "$ROOT/skills/use-github-$domain/scripts/operations.sh"; done
work="$(mktemp -d "${TMPDIR:-/tmp}/github-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT
GITHUB_CONFIG_DIR="$work"
cp "$GITHUB_AUTH_DIR/github-repos.example.json" "$work/github-repos.json"
mode=success
FIXTURE="$ROOT/tests/fixtures"
gh() {
    case "$1 $2" in
        'auth status') return 0 ;;
        'repo view') printf 'example-owner/example-project' ;;
        'issue list'|'pr list')
            [ "$mode" != list-failure ] || return 1
            if [ "$mode" = capped ]; then jq -n '[range(1;301)|{number:.,title:"Example"}]'
            elif [ "$mode" = empty ]; then printf '[]'
            else jq '.items' "$FIXTURE/github-issues.json"; fi ;;
        'issue view'|'pr view')
            [ "$mode" != detail-failure ] || return 1
            if [ "$mode" = project ]; then printf 'ISSUE_NODE'; else cat "$FIXTURE/github-issue-detail.json"; fi ;;
        'issue create')
            shift 2
            printf '%s\n' "$@" > "$work/write-args"
            printf 'https://github.com/example-owner/example-project/issues/1' ;;
        'project item-list') printf '{"totalCount":1,"items":[{"title":"Example","status":"Ready"}]}' ;;
        'api user') printf 'example-user' ;;
        'api graphql')
            case "$*" in
                *'updateProjectV2ItemFieldValue'*) printf 'mutation' >> "$work/mutations"; printf '{}' ;;
                *'organization(login:'*) printf '{"data":{"organization":{"projectV2":{"id":"PROJECT_NODE","field":{"id":"FIELD_NODE","options":[{"id":"OPTION_NODE","name":"Ready"}]}}}}}' ;;
                *'node(id: $project)'*) printf '{"id":"ITEM_NODE","fieldValueByName":{"optionId":"OLD_OPTION","name":"Waiting"}}' ;;
                *) cat "$FIXTURE/github-discussion-detail.json" | jq '[.]' ;;
            esac ;;
        *) printf 'Unexpected gh invocation\n' >&2; return 1 ;;
    esac
}
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
_github_export_items example-owner/example-project pr "$work/output" > /dev/null
grep -q 'Open Pull Requests' "$work/output/pull-requests.md"
_github_export_discussions example-owner/example-project "$work/output" > /dev/null
grep -q 'Bounded view' "$work/output/discussions.md"
_github_export_projects example "$work/output" > /dev/null
[ -f "$work/output/board-example-board.md" ]
mode=empty
_github_export_items example issue "$work/output" > /dev/null
[ ! -e "$work/output/issues.md" ] && [ ! -e "$work/output/issues" ]
mode=success
rm "$work/github-repos.json"
_github_create_issue --repo example-owner/example-project --title 'Example' --body 'Literal $() and `text`' > "$work/out"
grep -q 'DRY RUN' "$work/out"
[ ! -e "$work/write-args" ]
_github_create_issue --repo example-owner/example-project --title 'Example' --body 'Literal $() and `text`' --label 'literal\nlabel' --execute > /dev/null
grep -Fxq 'Literal $() and `text`' "$work/write-args"
grep -Fxq 'literal\nlabel' "$work/write-args"
cp "$GITHUB_AUTH_DIR/github-repos.example.json" "$work/github-repos.json"
mode=project
_github_move_card --repo example --issue 1 --status Ready > "$work/out"
grep -q 'DRY RUN' "$work/out"
[ ! -e "$work/mutations" ]
_github_move_card --repo example --issue 1 --status Ready --execute > /dev/null
[ "$(cat "$work/mutations")" = mutation ]
jq '.repos[0].projects[0].name="../outside"' "$work/github-repos.json" > "$work/invalid.json"
GITHUB_REPOS_PATH=invalid.json
if _github_config_ready >/dev/null 2>&1; then echo 'FAIL: unsafe export name accepted'; exit 1; fi
unset GITHUB_REPOS_PATH
GITHUB_ENV_FILE="$work/.env"
printf '%s\n' 'GH_TOKEN="$(touch must-not-exist)"' 'GITHUB_REPOS_PATH=github-repos.json' > "$GITHUB_ENV_FILE"
(cd "$work"; unset GH_TOKEN; _github_load_env; [ "$GH_TOKEN" = '$(touch must-not-exist)' ]; [ ! -e must-not-exist ])
printf 'ok: GitHub write gates, literal inputs, failure preservation, and explicit repository selection\n'

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
