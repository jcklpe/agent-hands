#!/usr/bin/env bash
##- Portable GitHub issues operations.
. "${GITHUB_AUTH_DIR}/scripts/items.sh"

_github_create_issue() {
    local repo_arg="" repo="" title="" body="" body_file="" execute=0 assign_me=0
    local labels=() assignees=()
    local cmd_out label assignee label_count=0 assignee_count=0

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --repo) [ -n "${2:-}" ] || { _github_error "--repo requires ALIAS or OWNER/REPO"; return 1; }; repo_arg="$2"; shift 2 ;;
            --title) [ -n "${2:-}" ] || { _github_error "--title requires TEXT"; return 1; }; title="$2"; shift 2 ;;
            --body) [ -n "${2:-}" ] || { _github_error "--body requires TEXT"; return 1; }; body="$2"; shift 2 ;;
            --body-file) [ -n "${2:-}" ] || { _github_error "--body-file requires FILE"; return 1; }; body_file="$2"; shift 2 ;;
            --label) [ -n "${2:-}" ] || { _github_error "--label requires NAME"; return 1; }; labels+=("$2"); label_count=$((label_count + 1)); shift 2 ;;
            --assignee) [ -n "${2:-}" ] || { _github_error "--assignee requires LOGIN"; return 1; }; assignees+=("$2"); assignee_count=$((assignee_count + 1)); shift 2 ;;
            --assign-me) assign_me=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _github_error "Unknown create-issue option: $1"; return 1 ;;
        esac
    done

    _github_ready || return 1
    [ -n "$title" ] || { _github_error "--title is required"; return 1; }
    [ -n "$repo_arg" ] || { _github_error "--repo is required (alias or OWNER/REPO)"; return 1; }
    [ -z "$body_file" ] || [ -f "$body_file" ] || { _github_error "Body file does not exist: $body_file"; return 1; }
    [ -z "$body_file" ] || [ -z "$body" ] || { _github_error "Use --body or --body-file, not both"; return 1; }
    repo="$(_github_resolve_repo "$repo_arg")" || return 1

    if [ "$assign_me" -eq 1 ]; then
        assignee_count=$((assignee_count + 1))
        if [ "$execute" -eq 1 ]; then
            assignee="$(gh api user --jq .login)" || return 1
            assignees+=("$assignee")
        else
            assignees+=("@me")
        fi
    fi

    _github_say "GitHub issue create plan:"
    _github_say "Repo: $repo"
    _github_say "Title: $title"
    if [ -n "$body_file" ]; then
        _github_say "Body file: $body_file"
        _github_say "--- body preview ---"
        cat "$body_file"
        _github_say "--- end body preview ---"
    elif [ -n "$body" ]; then
        _github_say "Body:"
        printf '%s\n' "$body"
    else
        _github_say "Body: <empty>"
    fi
    _github_say "Labels: $label_count"
    for label in ${labels[@]+"${labels[@]}"}; do printf '  %s\n' "$label"; done
    _github_say "Assignees: $assignee_count"
    for assignee in ${assignees[@]+"${assignees[@]}"}; do printf '  %s\n' "$assignee"; done

    if [ "$execute" -ne 1 ]; then
        _github_say "DRY RUN: no GitHub issue was created. Re-run with --execute after approval."
        return 0
    fi

    gh repo view "$repo" --json nameWithOwner --jq .nameWithOwner >/dev/null || {
        _github_error "Cannot reach repo: $repo"; return 1; }

    set -- gh issue create --repo "$repo" --title "$title"
    if [ -n "$body_file" ]; then set -- "$@" --body-file "$body_file"; else set -- "$@" --body "$body"; fi
    for label in ${labels[@]+"${labels[@]}"}; do set -- "$@" --label "$label"; done
    for assignee in ${assignees[@]+"${assignees[@]}"}; do set -- "$@" --assignee "$assignee"; done

    cmd_out="$("$@")" || { _github_error "Issue creation failed"; return 1; }
    _github_say "Created issue: $cmd_out"
}
