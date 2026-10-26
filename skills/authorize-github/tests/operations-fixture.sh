#!/usr/bin/env bash
##- Synthetic gh responses; no remote or credential store is accessed.
set -eu
GITHUB_AUTH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_PYTHON="${GITHUB_TEST_PYTHON:-python3}"
. "$GITHUB_AUTH_DIR/scripts/client.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/github-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT
GITHUB_CONFIG_DIR="$work"
cp "$GITHUB_AUTH_DIR/github-repos.example.json" "$work/github-repos.json"
mode=success
FIXTURE="$GITHUB_AUTH_DIR/tests/fixtures"
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
                *) cat "${DISCUSSION_FIXTURE:?discussion fixture must be selected by its owning test}" | jq '[.]' ;;
            esac ;;
        *) printf 'Unexpected gh invocation\n' >&2; return 1 ;;
    esac
}
