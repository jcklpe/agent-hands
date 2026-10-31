#!/usr/bin/env bash
##- Portable GitHub projects operations.

_github_sync_projects() {
    local entry="$1" default_owner="$2" dest="$3"
    local count i number name proj_owner items

    count="$(printf '%s' "$entry" | jq '(.projects // []) | length')"
    [ "$count" -gt 0 ] 2>/dev/null || return 0
    proj_owner="$(printf '%s' "$entry" | jq -r --arg d "$default_owner" '.project_owner // $d')"

    i=0
    while [ "$i" -lt "$count" ]; do
        number="$(printf '%s' "$entry" | jq -r --argjson i "$i" '.projects[$i].number')"
        name="$(printf '%s' "$entry" | jq -r --argjson i "$i" '.projects[$i].name // "project-\(.projects[$i].number)"')"
        items="$(gh project item-list "$number" --owner "$proj_owner" --format json --limit 500 2>/dev/null)" || {
            _github_warn "Could not read project #$number for $proj_owner"; return 1; }
        jq -e '(.items | type == "array") and ((.items | length) < 500) and ((.totalCount // (.items | length)) <= (.items | length))' <<< "$items" >/dev/null || { _github_error "Incomplete or invalid project export (500-item cap)"; return 1; }
        printf '%s' "$items" | jq '{items: (.items // [])}' | _github_render_projects board \
            --project-number "$number" --project-name "$name" > "$dest/board-$name.md" || return 1
        _github_say "  board-$name: $(printf '%s' "$items" | jq '(.items // []) | length')" >&2
        i=$((i + 1))
    done
}

_github_render_projects() { _github_render_file "${GITHUB_AUTH_DIR}/../use-github-projects/scripts/render.py" "$@"; }

_github_export_projects() (
    set -o pipefail
    local alias="$1" destination="$2" entry owner name
    local artifacts=()
    _github_ready || return 1
    entry="$(_github_repo_entry "$alias")" || return 1
    owner="$(printf '%s' "$entry" | jq -r '.owner')" || return 1
    _github_export_begin "$destination" || return 1
    _github_sync_projects "$entry" "$owner" "$GITHUB_EXPORT_WORK/new" || return 1
    while IFS= read -r name; do [ -z "$name" ] || artifacts+=("board-$name.md"); done <<EOF_NAMES
$(printf '%s' "$entry" | jq -r '(.projects // [])[] | .name // "project-\(.number)"')
EOF_NAMES
    _github_publish_export "$destination" ${artifacts[@]+"${artifacts[@]}"}
)
