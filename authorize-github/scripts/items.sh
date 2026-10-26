#!/usr/bin/env bash
##- Shared bounded issue/PR response collection; only these two domains use this shape.
_github_sync_items() {
    local owner="$1" repo="$2" kind="$3" dest="$4"
    local index_name detail_dir list_json numbers n item_json

    if [ "$kind" = "pr" ]; then
        index_name="pull-requests.md"; detail_dir="pull-requests"
    else
        index_name="issues.md"; detail_dir="issues"
    fi

    list_json="$(gh "$kind" list --repo "$owner/$repo" --state open --limit 300 \
        --json number,title,labels,assignees,updatedAt,createdAt,body 2>/dev/null)" || {
        _github_warn "Could not list ${kind}s for $owner/$repo (feature may be disabled)"; return 1; }

    jq -e 'type == "array" and all(.[]; .number | type == "number" and . > 0 and floor == .)' <<< "$list_json" >/dev/null || return 1
    [ "$(printf '%s' "$list_json" | jq length)" -lt 300 ] || { _github_error 'Issue/PR read reached its 300-item cap; export not replaced'; return 1; }
    # An empty index is snapshot noise; skip the file entirely and clear any stale copy.
    if [ "$(printf '%s' "$list_json" | jq 'length')" -eq 0 ]; then
        rm -f "$dest/$index_name"
        rm -rf "$dest/$detail_dir"
        _github_say "  ${index_name%.md}: 0 (skipped)" >&2
        return 0
    fi

    printf '{"items":%s}' "$list_json" | _github_render_items issue-index \
        --owner "$owner" --repo "$repo" --kind "$kind" --detail-dir "$detail_dir" \
        > "$dest/$index_name" || return 1

    # Detail files carry full body + comment threads. Rebuild the directory each
    # time so closed items do not linger as stale files.
    rm -rf "$dest/$detail_dir"
    mkdir -p "$dest/$detail_dir" || return 1
    numbers="$(printf '%s' "$list_json" | jq -r '.[].number')"
    for n in $numbers; do
        item_json="$(gh "$kind" view "$n" --repo "$owner/$repo" \
            --json number,title,state,body,author,assignees,labels,createdAt,updatedAt,url,comments 2>/dev/null)" || return 1
        printf '%s' "$item_json" | _github_render_items item-detail \
            --owner "$owner" --repo "$repo" --kind "$kind" > "$dest/$detail_dir/$n.md" || return 1
    done
    _github_say "  ${index_name%.md}: $(printf '%s' "$numbers" | grep -c . | tr -d ' ')" >&2
}

_github_export_items() (
    set -o pipefail
    local repo_arg="$1" kind="$2" destination="$3" repo index details
    _github_ready || return 1
    repo="$(_github_resolve_repo "$repo_arg")" || return 1
    _github_export_begin "$destination" || return 1
    _github_sync_items "${repo%/*}" "${repo#*/}" "$kind" "$GITHUB_EXPORT_WORK/new" || return 1
    if [ "$kind" = pr ]; then index=pull-requests.md; details=pull-requests; else index=issues.md; details=issues; fi
    _github_publish_export "$destination" "$index" "$details"
)
