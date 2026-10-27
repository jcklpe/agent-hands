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

_github_move_card() {
    local repo_arg="" issue="" status="" execute=0
    local owner repo entry proj_owner proj_number proj_id field_id option_id
    local issue_node item_id current current_name pages items options result

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --repo) [ -n "${2:-}" ] || { _github_error "--repo requires ALIAS"; return 1; }; repo_arg="$2"; shift 2 ;;
            --issue) [ -n "${2:-}" ] || { _github_error "--issue requires NUMBER"; return 1; }; issue="$2"; shift 2 ;;
            --status) [ -n "${2:-}" ] || { _github_error "--status requires NAME"; return 1; }; status="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _github_error "Unknown move-card option: $1"; return 1 ;;
        esac
    done

    _github_ready || return 1
    [ -n "$repo_arg" ] || { _github_error "--repo is required (a configured alias)"; return 1; }
    [ -n "$issue" ] || { _github_error "--issue NUMBER is required"; return 1; }
    [ -n "$status" ] || { _github_error "--status NAME is required (e.g. Done, Backlog)"; return 1; }

    entry="$(_github_repo_entry "$repo_arg")" || return 1
    owner="$(printf '%s' "$entry" | jq -r '.owner')"
    repo="$(printf '%s' "$entry" | jq -r '.repo')"
    [ "$(printf '%s' "$entry" | jq '(.projects // []) | length')" -gt 0 ] || {
        _github_error "No project board configured for alias: $repo_arg"; return 1; }
    proj_number="$(printf '%s' "$entry" | jq -r '.projects[0].number')"
    proj_owner="$(printf '%s' "$entry" | jq -r --arg d "$owner" '.project_owner // $d')"

    # Resolve project node id, the Status field, and the target option in one query.
    local meta
    meta="$(gh api graphql -f owner="$proj_owner" -F number="$proj_number" -f query='
      query($owner:String!, $number:Int!) {
        organization(login:$owner) {
          projectV2(number:$number) {
            id
            field(name:"Status") {
              ... on ProjectV2SingleSelectField { id options { id name } }
            }
          }
        }
      }' 2>/dev/null)" || { _github_error "Could not read project #$proj_number for $proj_owner"; return 1; }

    # Validate the envelope before interpreting absent fields as ordinary state.
    meta="$(printf '%s' "$meta" | jq -cse '
        def id: type == "string" and test("^[A-Za-z0-9_+/=-]+$") and . != "null";
        if length == 1 and (.[0].errors == null or .[0].errors == []) then
            .[0].data.organization.projectV2
        else error("invalid project response") end |
        select((.id | id) and (.field.id | id) and
            (.field.options | type == "array") and
            all(.field.options[]; (.id | id) and (.name | type == "string" and length > 0)))
    ' 2>/dev/null)" || { _github_error "Invalid project metadata; no move planned"; return 1; }
    proj_id="$(printf '%s' "$meta" | jq -r '.id')"
    field_id="$(printf '%s' "$meta" | jq -r '.field.id')"
    options="$(printf '%s' "$meta" | jq -c '.field.options')"
    option_id="$(printf '%s' "$options" | jq -er --arg s "$status" '
        [.[] | select(.name == $s)] | select(length == 1) | .[0].id')" || {
        _github_error "Status must identify exactly one option: $status"; return 1; }

    issue_node="$(gh issue view "$issue" --repo "$owner/$repo" --json id --jq .id 2>/dev/null)" || {
        _github_error "Could not read issue #$issue in $owner/$repo"; return 1; }
    printf '%s' "$issue_node" | jq -Rse 'test("^[A-Za-z0-9_+/=-]+$") and . != "null"' >/dev/null || {
        _github_error "Invalid issue identifier; no move planned"; return 1; }

    # Keep full envelopes so GraphQL errors and incomplete pagination cannot be
    # mistaken for an item. gh emits one JSON response per page.
    items="$(gh api graphql --paginate -f project="$proj_id" -f query='
      query($project: ID!, $endCursor: String) {
        node(id: $project) { ... on ProjectV2 {
          id
          items(first:100, after:$endCursor) {
            pageInfo { hasNextPage endCursor }
            nodes { id content { ... on Issue { id } }
                    fieldValueByName(name:"Status") { ... on ProjectV2ItemFieldSingleSelectValue { optionId name } } }
          }
        } }
      }' 2>/dev/null)" || { _github_error "Could not read project items; no move planned"; return 1; }
    pages="$(printf '%s' "$items" | jq -cse --arg project "$proj_id" '
        select(length > 0 and all(.[];
            (.errors == null or .errors == []) and .data.node.id == $project and
            (.data.node.items.nodes | type == "array") and
            all(.data.node.items.nodes[]; type == "object") and
            (.data.node.items.pageInfo.hasNextPage | type == "boolean")) and
            .[-1].data.node.items.pageInfo.hasNextPage == false and
            all(.[0:-1][]; .data.node.items.pageInfo.hasNextPage == true and
                (.data.node.items.pageInfo.endCursor | type == "string" and length > 0)) and
            ([.[0:-1][].data.node.items.pageInfo.endCursor] | length == (unique | length)))
    ' 2>/dev/null)" || { _github_error "Invalid or incomplete project items; no move planned"; return 1; }
    item_id="$(printf '%s' "$pages" | jq -ce --arg issue "$issue_node" --argjson options "$options" '
        def id: type == "string" and test("^[A-Za-z0-9_+/=-]+$") and . != "null";
        [.[] | .data.node.items.nodes[] | select(.content.id == $issue)] |
        select(length == 1) | .[0] |
        select((.id | id) and has("fieldValueByName")) |
        .fieldValueByName as $state |
        select($state == null or (($state.optionId | id) and
            ($state.name | type == "string" and length > 0) and
            ([$options[] | select(.id == $state.optionId and .name == $state.name)] | length == 1)))
    ' 2>/dev/null)" || { _github_error "Issue #$issue is missing, ambiguous or invalid on the board; no move planned"; return 1; }
    current="$(printf '%s' "$item_id" | jq -r '.fieldValueByName.optionId // ""')"
    current_name="$(printf '%s' "$item_id" | jq -r '.fieldValueByName.name // "No Status"')"
    item_id="$(printf '%s' "$item_id" | jq -r '.id')"

    _github_say "GitHub board move plan:"
    _github_say "Repo: $owner/$repo"
    _github_say "Issue: #$issue"
    _github_say "Board: $proj_owner project #$proj_number"
    _github_say "Status: $current_name -> $status"

    if [ "$current" = "$option_id" ]; then
        _github_say "Already in $status — nothing to do."
        return 0
    fi
    if [ "$execute" -ne 1 ]; then
        _github_say "DRY RUN: no change made. Re-run with --execute after approval."
        return 0
    fi

    result="$(gh api graphql -f project="$proj_id" -f item="$item_id" -f field="$field_id" -f option="$option_id" -f query='
      mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
        updateProjectV2ItemFieldValue(input:{
          projectId:$project, itemId:$item, fieldId:$field,
          value:{ singleSelectOptionId:$option }}) { projectV2Item { id } }
      }' 2>/dev/null)" || { _github_error "Board move outcome is uncertain; inspect the card before retrying"; return 1; }
    printf '%s' "$result" | jq -se --arg item "$item_id" '
        length == 1 and (.[0].errors == null or .[0].errors == []) and
        .[0].data.updateProjectV2ItemFieldValue.projectV2Item.id == $item
    ' >/dev/null 2>&1 || { _github_error "Board move outcome is uncertain; inspect the card before retrying"; return 1; }
    _github_say "Moved #$issue to $status."
    _github_warn "Any board automation is configured by its owner; this command does not promise an issue-state transition."
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
