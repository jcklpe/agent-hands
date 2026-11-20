#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then _planner_source="${(%):-%x}"; else _planner_source="${BASH_SOURCE[0]}"; fi
PLANNER_DIR="$(cd "$(dirname "$_planner_source")/.." && pwd)"
unset _planner_source
source "$PLANNER_DIR/../setup-microsoft-services/scripts/batch.sh"
_m365_planner_python() { _m365_python "$PLANNER_DIR" "$@"; }
_m365_planner_render_helper() { _m365_planner_python "$PLANNER_DIR/scripts/render.py" "$@"; }
_m365_planner_warn() { printf 'WARN: %s\n' "$*" >&2; }
_m365_planner_audit_path() { case "${M365_PLANNER_AUDIT_LOG:-task-writes.jsonl}" in /*) printf '%s\n' "$M365_PLANNER_AUDIT_LOG" ;; *) printf '%s/%s\n' "$PLANNER_DIR" "${M365_PLANNER_AUDIT_LOG:-task-writes.jsonl}" ;; esac; }
_m365_planner_audit_append() { _m365_planner_python "$M365_AUTH_DIR/scripts/audit.py" "$(_m365_planner_audit_path)"; }

_m365_planner_max_tasks() {
    _m365_account_value "$1" '.planner.max_tasks // 500' 2>/dev/null || printf '500'
}

_m365_planner_configured_ids() {
    _m365_account_value "$1" '(.planner.plans // [])[] | .id' 2>/dev/null || true
}

_m365_planner_require_plan_allowed() {
    local alias="$1" plan_id="$2"
    if ! _m365_planner_configured_ids "$alias" | grep -qxF -- "$plan_id"; then
        _m365_error "Plan $plan_id is not in planner.plans for alias '$alias'; writes are limited to configured plans"
        _m365_say "NEXT: add {\"id\": \"$plan_id\", \"name\": \"...\"} to planner.plans in $(_m365_accounts_path)" >&2
        return 1
    fi
}

_m365_planner_require_write() {
    local alias="$1"
    if ! _m365_account_value "$alias" '(.planner.write_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _m365_error "Microsoft 365 Planner writes are not enabled for alias '$alias'"
        _m365_say "NEXT: set planner.write_enabled to true for '$alias' in $(_m365_accounts_path), (the session already requests Tasks.ReadWrite)" >&2
        return 1
    fi
}

_m365_planner_url() {
    printf '%s/%s\n' "$(_m365_graph_base "$1")" "$2"
}

# Prefer a configured tenant GUID; an already-authorized SDK identity can resolve organizations.
_m365_planner_tenant() {
    local alias="$1" tenant context
    tenant="$(_m365_account_value "$alias" '.tenant // ""')" || tenant=""
    if ! printf '%s' "$tenant" | grep -Eq '^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$'; then
        tenant=""
        if [ "$(_m365_auth_provider "$alias" 2>/dev/null)" = graph-powershell ]; then
            context="$(_m365_powershell_auth "$alias" "")" || return 1
            tenant="$(printf '%s' "$context" | jq -r '.tenant_id // empty')" || return 1
        fi
    fi
    printf '%s' "$tenant"
}

_m365_planner_my_id() {
    _m365_profile_json "$1" | jq -r '.id // empty'
}

# Resolve an assignee argument to a Graph user ID: "me", a user ID (GUID), or an email/UPN looked up exactly.
_m365_planner_resolve_user() {
    local alias="$1" who="$2" user
    case "$who" in
        me) _m365_planner_my_id "$alias"; return ;;
        *@*)
            user="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "users/$(_m365_uri_encode "$who")")" --data-urlencode '$select=id,displayName')" || { _m365_error "No user found for $who"; return 1; }
            printf '%s' "$user" | jq -r '.id'
            ;;
        *)
            if printf '%s' "$who" | grep -Eqi '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
                printf '%s\n' "$who"
            else
                _m365_error "Assignee must be 'me', an email address, or a Graph user ID (got: $who)"
                return 1
            fi
            ;;
    esac
}

_m365_planner_plans() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" json_mode=0 data
    [ -n "$alias" ] || { _m365_error "m365 planner plans requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do case "$1" in --json) json_mode=1; shift ;; *) _m365_error "Unknown m365 planner plans option: $1"; return 1 ;; esac; done
    _m365_require_enabled "$alias" planner || return 1
    data="$(mktemp "$M365_WORK/planner-plans.XXXXXX")" || return 1
    _m365_get_paginated "$alias" 200 "$data" "$(_m365_planner_url "$alias" "me/planner/plans")" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "$data"; return 0; fi
    jq -r --argjson configured "$(_m365_planner_configured_ids "$alias" | jq -R . | jq -sc .)" '
      (.value // [])[] |
      "- " + (.title // "(untitled plan)") + " | plan_id: " + (.id // "") + " | group: " + (.container.containerId // .owner // "") + (.id as $id | if ($configured | index($id)) then " | configured" else "" end)
    ' "$data"
)

_m365_planner_buckets() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" plan_id="" json_mode=0 data
    [ -n "$alias" ] || { _m365_error "m365 planner buckets requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --plan) [ -n "${2:-}" ] || { _m365_error "--plan requires ID"; return 1; }; plan_id="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 planner buckets option: $1"; return 1 ;;
        esac
    done
    [ -n "$plan_id" ] || { _m365_error "m365 planner buckets requires --plan ID"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    data="$(mktemp "$M365_WORK/planner-buckets.XXXXXX")" || return 1
    _m365_get_paginated "$alias" 200 "$data" "$(_m365_planner_url "$alias" "planner/plans/$(_m365_uri_encode "$plan_id")/buckets")" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "$data"; return 0; fi
    jq -r '(.value // []) | sort_by(.orderHint // "")[] | "- " + (.name // "(unnamed bucket)") + " | bucket_id: " + (.id // "")' "$data"
)

# Write one plan's plan, details, buckets, tasks, and task details to OUT as a single JSON object.
_m365_planner_fetch_plan() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" plan_id="$2" out="$3" dir encoded max
    dir="$(mktemp -d "$M365_WORK/planner-plan.XXXXXX")" || return 1
    encoded="$(_m365_uri_encode "$plan_id")"
    max="$(_m365_planner_max_tasks "$alias")"
    _m365_get "$alias" "$(_m365_planner_url "$alias" "planner/plans/${encoded}")" > "${dir}/plan.json" || return 1
    _m365_get "$alias" "$(_m365_planner_url "$alias" "planner/plans/${encoded}/details")" > "${dir}/details.json" || return 1
    _m365_get_paginated "$alias" 200 "${dir}/buckets.json" "$(_m365_planner_url "$alias" "planner/plans/${encoded}/buckets")" || return 1
    _m365_get_paginated "$alias" "$max" "${dir}/tasks.json" "$(_m365_planner_url "$alias" "planner/plans/${encoded}/tasks")" || return 1
    # Details (description, checklist) cost one request per task, so only tasks that have them are fetched, 20 per batch.
    jq '[(.value // [])[] | select((.hasDescription // false) or ((.checklistItemCount // 0) > 0)) | {method: "GET", url: ("/planner/tasks/" + (.id | @uri) + "/details")}]' "${dir}/tasks.json" > "${dir}/detail-requests.json" || return 1
    _m365_batch "$alias" "${dir}/detail-requests.json" "${dir}/detail-responses.json" || return 1
    jq -e 'all(.[]; .status == 200 and (.body.id | type == "string"))' "${dir}/detail-responses.json" >/dev/null || { _m365_error 'Some Planner task details could not be read; export was not published'; return 1; }
    jq -n \
        --slurpfile plan "${dir}/plan.json" \
        --slurpfile details "${dir}/details.json" \
        --slurpfile buckets "${dir}/buckets.json" \
        --slurpfile tasks "${dir}/tasks.json" \
        --slurpfile taskDetails "${dir}/detail-responses.json" \
        '{plan: $plan[0], details: $details[0], buckets: ($buckets[0].value // []), tasks: ($tasks[0].value // []),
          taskDetails: ([$taskDetails[0][] | select(.status == 200) | {key: .body.id, value: .body}] | from_entries)}' > "$out"
)

# Write {userId: {displayName, mail}} for every user named in the plans' assignments, creators, and completers.
_m365_planner_fetch_users() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" plans_file="$2" out="$3" dir
    dir="$(mktemp -d "$M365_WORK/planner-users.XXXXXX")" || return 1
    jq '[.[] | .tasks[] | ((.assignments // {}) | keys[]), (.createdBy.user.id // empty), (.completedBy.user.id // empty)] | unique | map({method: "GET", url: ("/users/" + (. | @uri) + "?$select=id,displayName,mail")})' "$plans_file" > "${dir}/requests.json" || return 1
    _m365_batch "$alias" "${dir}/requests.json" "${dir}/responses.json" || return 1
    if ! jq -e 'all(.[]; .status == 200)' "${dir}/responses.json" >/dev/null; then _m365_planner_warn 'Some user names could not be resolved; their IDs remain in the export'; fi
    jq '[.[] | select(.status == 200) | {key: .body.id, value: {displayName: .body.displayName, mail: .body.mail}}] | from_entries' "${dir}/responses.json" > "$out"
)

_m365_planner_tasks() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" plan_id="" bucket="" mine=0 open_only=0 json_mode=0 dir me
    [ -n "$alias" ] || { _m365_error "m365 planner tasks requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --plan) [ -n "${2:-}" ] || { _m365_error "--plan requires ID"; return 1; }; plan_id="$2"; shift 2 ;;
            --bucket) [ -n "${2:-}" ] || { _m365_error "--bucket requires ID"; return 1; }; bucket="$2"; shift 2 ;;
            --mine) mine=1; shift ;;
            --open) open_only=1; shift ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 planner tasks option: $1"; return 1 ;;
        esac
    done
    [ -n "$plan_id" ] || { _m365_error "m365 planner tasks requires --plan ID"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    dir="$(mktemp -d "$M365_WORK/planner-tasks.XXXXXX")" || return 1
    _m365_get_paginated "$alias" "$(_m365_planner_max_tasks "$alias")" "${dir}/tasks.json" "$(_m365_planner_url "$alias" "planner/plans/$(_m365_uri_encode "$plan_id")/tasks")" || return 1
    _m365_get_paginated "$alias" 200 "${dir}/buckets.json" "$(_m365_planner_url "$alias" "planner/plans/$(_m365_uri_encode "$plan_id")/buckets")" || return 1
    me=""
    [ "$mine" -eq 1 ] && { me="$(_m365_planner_my_id "$alias")" || return 1; }
    jq --arg bucket "$bucket" --arg me "$me" --argjson open "$open_only" '
      {value: [(.value // [])[] |
        select($bucket == "" or .bucketId == $bucket) |
        select($me == "" or ((.assignments // {}) | has($me))) |
        select($open == 0 or ((.percentComplete // 0) < 100))]}
    ' "${dir}/tasks.json" > "${dir}/filtered.json" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "${dir}/filtered.json"; return 0; fi
    if [ "$(jq '.value | length' "${dir}/filtered.json")" -eq 0 ]; then _m365_say "No matching Planner tasks."; return 0; fi
    jq -r --slurpfile b "${dir}/buckets.json" '
      ([$b[0].value[]? | {key: .id, value: .name}] | from_entries) as $names |
      .value | sort_by(.dueDateTime // "9999") [] |
      "- " + (.title // "(untitled task)") +
      " | " + (if (.percentComplete // 0) >= 100 then "done" elif (.percentComplete // 0) > 0 then "in progress" else "not started" end) +
      " | bucket: " + ($names[.bucketId] // .bucketId // "") +
      (if .dueDateTime then " | due: " + (.dueDateTime | .[0:10]) else "" end) +
      " | assignees: " + (((.assignments // {}) | keys | length) | tostring) +
      " | task_id: " + (.id // "")
    ' "${dir}/filtered.json"
)

_m365_planner_task() {
    local alias="${1:-}" task_id="" json_mode=0 task details encoded
    [ -n "$alias" ] || { _m365_error "m365 planner task requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task) [ -n "${2:-}" ] || { _m365_error "--task requires ID"; return 1; }; task_id="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 planner task option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] || { _m365_error "m365 planner task requires --task ID"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    encoded="$(_m365_uri_encode "$task_id")"
    task="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}")")" || return 1
    details="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}/details")")" || return 1
    if [ "$json_mode" -eq 1 ]; then
        jq -n --argjson task "$task" --argjson details "$details" '{task: $task, details: $details}'
        return 0
    fi
    jq -rn --argjson t "$task" --argjson d "$details" '
      "Title: " + ($t.title // ""),
      "Task ID: " + ($t.id // ""),
      "Plan ID: " + ($t.planId // ""),
      "Bucket ID: " + ($t.bucketId // ""),
      "Progress: " + (($t.percentComplete // 0) | tostring) + "%",
      "Priority: " + (($t.priority // 5) | tostring),
      "Start: " + ($t.startDateTime // ""),
      "Due: " + ($t.dueDateTime // ""),
      "Assignee IDs: " + ((($t.assignments // {}) | keys) | join(", ")),
      "Created: " + ($t.createdDateTime // ""),
      "Description:",
      ($d.description // ""),
      (if (($d.checklist // {}) | length) > 0 then "Checklist:", ($d.checklist | to_entries | sort_by(.value.orderHint // "")[] | "- [" + (if .value.isChecked then "x" else " " end) + "] " + (.value.title // "")) else empty end)
    '
}

_m365_planner_export() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" qa=0 custom_out="" out tmp dir plan_id email me refreshed limit dirout
    [ -n "$alias" ] || { _m365_error "planner export requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do case "$1" in --output) [ -n "${2:-}" ] || { _m365_error "--output requires FILE"; return 1; }; custom_out="$2"; shift 2 ;; *) _m365_error "Unknown planner export option: $1"; return 1 ;; esac; done
    _m365_require_enabled "$alias" planner || return 1
    if [ -z "$(_m365_planner_configured_ids "$alias")" ]; then
        _m365_error "No plans are configured in planner.plans for alias '$alias'"
        _m365_say "NEXT: run 'planner plans $alias' and add the plan IDs to snapshot" >&2
        return 1
    fi
    out="$custom_out"
    [ -n "$out" ] && [ -d "$(dirname "$out")" ] && [ ! -L "$out" ] || { _m365_error 'Choose --output FILE in an existing directory, not a symlink'; return 1; }
    tmp="$M365_WORK/export.md"
    dir="$M365_WORK/plans"
    mkdir "$dir" || return 1
    local n=0 files=()
    while IFS= read -r plan_id || [ -n "$plan_id" ]; do
        [ -n "$plan_id" ] || continue
        _m365_planner_fetch_plan "$alias" "$plan_id" "${dir}/plan-${n}.json" || return 1
        jq --arg id "$plan_id" --argjson cfg "$(_m365_account_value "$alias" '(.planner.plans // [])' | jq -c --arg id "$plan_id" '[.[] | select(.id == $id)][0] // {}')" '. + {config: $cfg}' "${dir}/plan-${n}.json" > "${dir}/plan-${n}.cfg.json" || return 1
        files+=("${dir}/plan-${n}.cfg.json")
        n=$((n + 1))
    done <<EOF
$(_m365_planner_configured_ids "$alias")
EOF
    jq -s '.' "${files[@]}" > "${dir}/plans.json" || return 1
    _m365_planner_fetch_users "$alias" "${dir}/plans.json" "${dir}/users.json" || return 1
    jq -n --slurpfile plans "${dir}/plans.json" --slurpfile users "${dir}/users.json" '{plans: $plans[0], users: $users[0]}' > "${dir}/render.json" || return 1
    email="$(_m365_profile_email "$alias")" || return 1
    me="$(_m365_planner_my_id "$alias")" || return 1
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    limit="$(_m365_account_value "$alias" '.planner.description_character_limit // 2000')" || limit=2000
    _m365_planner_render_helper planner --alias "$alias" --email "$email" --me "$me" --tenant "$(_m365_planner_tenant "$alias")" --refreshed "$refreshed" --description-limit "$limit" --input "${dir}/render.json" > "$tmp" || return 1
    _m365_planner_python "$M365_AUTH_DIR/scripts/publish.py" "$tmp" "$out" replace || return 1
    _m365_say "Updated $out"
)

# Planner date-only due inputs use noon UTC; the displayed day may differ in some timezones.
_m365_planner_due() {
    case "$1" in
        none) printf 'null\n' ;;
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) printf '"%sT12:00:00Z"\n' "$1" ;;
        *) _m365_error "--due must be YYYY-MM-DD or 'none' (got: $1)"; return 1 ;;
    esac
}

_m365_planner_progress() {
    case "$1" in
        not-started) printf '0\n' ;;
        in-progress) printf '50\n' ;;
        done) printf '100\n' ;;
        *) _m365_error "--progress must be not-started, in-progress, or done (got: $1)"; return 1 ;;
    esac
}

_m365_planner_audit() {
    local alias="$1" action="$2" task_id="$3" title="$4" verified="$5" changes="$6"
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --arg action "$action" --arg task "$task_id" --arg title "$title" --argjson verified "$verified" --argjson changes "$changes" \
        '{ts: $ts, service: "m365-planner", alias: $alias, action: $action, task_id: $task, title: $title, changes: $changes, verified: $verified}' | _m365_planner_audit_append || _m365_planner_warn "Could not append to the audit log: $(_m365_planner_audit_path)"
}

_m365_planner_create() {
    local alias="${1:-}" plan_id="" bucket="" title="" due="" progress="" desc="" desc_file="" execute=0 body created task_id details readback ok who uid
    local assignees=()
    [ -n "$alias" ] || { _m365_error "m365 planner create-task requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --plan) [ -n "${2:-}" ] || { _m365_error "--plan requires ID"; return 1; }; plan_id="$2"; shift 2 ;;
            --bucket) [ -n "${2:-}" ] || { _m365_error "--bucket requires ID"; return 1; }; bucket="$2"; shift 2 ;;
            --title) [ -n "${2:-}" ] || { _m365_error "--title requires TEXT"; return 1; }; title="$2"; shift 2 ;;
            --due) [ -n "${2:-}" ] || { _m365_error "--due requires YYYY-MM-DD"; return 1; }; due="$2"; shift 2 ;;
            --progress) [ -n "${2:-}" ] || { _m365_error "--progress requires a value"; return 1; }; progress="$2"; shift 2 ;;
            --assign) [ -n "${2:-}" ] || { _m365_error "--assign requires me, an email, or a user ID"; return 1; }; assignees+=("$2"); shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _m365_error "--desc requires TEXT"; return 1; }; desc="$2"; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _m365_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 planner create-task option: $1"; return 1 ;;
        esac
    done
    [ -n "$plan_id" ] && [ -n "$bucket" ] && [ -n "$title" ] || { _m365_error "create-task requires --plan, --bucket, and --title"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    _m365_planner_require_plan_allowed "$alias" "$plan_id" || return 1
    if [ -n "$desc_file" ]; then [ -f "$desc_file" ] || { _m365_error "Description file does not exist: $desc_file"; return 1; }; desc="$(cat "$desc_file")"; fi
    body="$(jq -nc --arg plan "$plan_id" --arg bucket "$bucket" --arg title "$title" '{planId: $plan, bucketId: $bucket, title: $title}')"
    if [ -n "$due" ]; then body="$(printf '%s' "$body" | jq -c --argjson due "$(_m365_planner_due "$due")" '. + {dueDateTime: $due}')" || return 1; fi
    if [ -n "$progress" ]; then body="$(printf '%s' "$body" | jq -c --argjson p "$(_m365_planner_progress "$progress")" '. + {percentComplete: $p}')" || return 1; fi
    for who in "${assignees[@]+"${assignees[@]}"}"; do
        uid="$(_m365_planner_resolve_user "$alias" "$who")" || return 1
        body="$(printf '%s' "$body" | jq -c --arg u "$uid" '.assignments = ((.assignments // {}) + {($u): {"@odata.type": "#microsoft.graph.plannerAssignment", orderHint: " !"}})')"
    done
    _m365_say "Microsoft 365 Planner create-task plan:"
    _m365_say "Account: $alias"
    printf '%s' "$body" | jq .
    [ -n "$desc" ] && { _m365_say "Description:"; printf '%s\n' "$desc"; }
    _m365_say "Note: this plan is shared; the new task is visible to everyone on it."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no task was created. Re-run with --execute to create it."; return 0; fi
    _m365_planner_require_write "$alias" || return 1
    created="$(_m365_write POST "$alias" "$(_m365_planner_url "$alias" "planner/tasks")" "$body")" || return 1
    task_id="$(printf '%s' "$created" | jq -r '.id // empty')"
    [ -n "$task_id" ] || { _m365_error "Graph did not return a task ID"; return 1; }
    if [ -n "$desc" ]; then
        details="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")/details")")" || return 1
        _m365_http PATCH "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")/details")" "$(jq -nc --arg d "$desc" '{description: $d}')" -H "If-Match: $(printf '%s' "$details" | jq -r '."@odata.etag"')" >/dev/null || { _m365_error "Task $task_id was created, but setting its description failed"; return 1; }
    fi
    readback="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")")" || return 1
    ok="$(jq -n --argjson want "$body" --argjson got "$readback" '($got.title == $want.title) and ($got.bucketId == $want.bucketId) and (($want.assignments // {}) | keys | all(. as $k | ($got.assignments // {}) | has($k)))')"
    _m365_planner_audit "$alias" create-task "$task_id" "$title" "$ok" "$body"
    [ "$ok" = true ] || { _m365_error "Created task $task_id but readback did not match the request"; return 1; }
    _m365_say "Created task (confirmed by readback): $title | task_id: $task_id"
}

_m365_planner_update() {
    local alias="${1:-}" task_id="" title="" bucket="" due="" progress="" desc="" desc_file="" set_desc=0 execute=0
    local encoded current details patch="{}" who uid ok readback after_details
    local assign=() unassign=()
    [ -n "$alias" ] || { _m365_error "m365 planner update-task requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task) [ -n "${2:-}" ] || { _m365_error "--task requires ID"; return 1; }; task_id="$2"; shift 2 ;;
            --title) [ -n "${2:-}" ] || { _m365_error "--title requires TEXT"; return 1; }; title="$2"; shift 2 ;;
            --bucket) [ -n "${2:-}" ] || { _m365_error "--bucket requires ID"; return 1; }; bucket="$2"; shift 2 ;;
            --due) [ -n "${2:-}" ] || { _m365_error "--due requires YYYY-MM-DD or none"; return 1; }; due="$2"; shift 2 ;;
            --progress) [ -n "${2:-}" ] || { _m365_error "--progress requires a value"; return 1; }; progress="$2"; shift 2 ;;
            --assign) [ -n "${2:-}" ] || { _m365_error "--assign requires me, an email, or a user ID"; return 1; }; assign+=("$2"); shift 2 ;;
            --unassign) [ -n "${2:-}" ] || { _m365_error "--unassign requires me, an email, or a user ID"; return 1; }; unassign+=("$2"); shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _m365_error "--desc requires TEXT"; return 1; }; desc="$2"; set_desc=1; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _m365_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; set_desc=1; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 planner update-task option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] || { _m365_error "update-task requires --task ID"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    if [ -n "$desc_file" ]; then [ -f "$desc_file" ] || { _m365_error "Description file does not exist: $desc_file"; return 1; }; desc="$(cat "$desc_file")"; fi
    encoded="$(_m365_uri_encode "$task_id")"
    current="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}")")" || return 1
    _m365_planner_require_plan_allowed "$alias" "$(printf '%s' "$current" | jq -r '.planId')" || return 1
    [ -n "$title" ] && patch="$(printf '%s' "$patch" | jq -c --arg v "$title" '. + {title: $v}')"
    [ -n "$bucket" ] && patch="$(printf '%s' "$patch" | jq -c --arg v "$bucket" '. + {bucketId: $v}')"
    if [ -n "$due" ]; then patch="$(printf '%s' "$patch" | jq -c --argjson v "$(_m365_planner_due "$due")" '. + {dueDateTime: $v}')" || return 1; fi
    if [ -n "$progress" ]; then patch="$(printf '%s' "$patch" | jq -c --argjson v "$(_m365_planner_progress "$progress")" '. + {percentComplete: $v}')" || return 1; fi
    for who in "${assign[@]+"${assign[@]}"}"; do
        uid="$(_m365_planner_resolve_user "$alias" "$who")" || return 1
        patch="$(printf '%s' "$patch" | jq -c --arg u "$uid" '.assignments = ((.assignments // {}) + {($u): {"@odata.type": "#microsoft.graph.plannerAssignment", orderHint: " !"}})')"
    done
    for who in "${unassign[@]+"${unassign[@]}"}"; do
        uid="$(_m365_planner_resolve_user "$alias" "$who")" || return 1
        printf '%s' "$current" | jq -e --arg u "$uid" '(.assignments // {}) | has($u)' >/dev/null || { _m365_error "User $uid is not assigned to this task"; return 1; }
        patch="$(printf '%s' "$patch" | jq -c --arg u "$uid" '.assignments = ((.assignments // {}) + {($u): null})')"
    done
    if [ "$patch" = "{}" ] && [ "$set_desc" -eq 0 ]; then _m365_error "update-task needs at least one change"; return 1; fi
    _m365_say "Microsoft 365 Planner update-task plan:"
    _m365_say "Account: $alias"
    printf '%s' "$current" | jq -r '"Task: " + (.title // "") + " | task_id: " + .id, "Now: progress " + ((.percentComplete // 0) | tostring) + "% | bucket " + (.bucketId // "") + " | due " + (.dueDateTime // "none") + " | assignees " + (((.assignments // {}) | keys) | join(", "))'
    [ "$patch" != "{}" ] && { _m365_say "Task changes:"; printf '%s' "$patch" | jq .; }
    [ "$set_desc" -eq 1 ] && { _m365_say "New description (replaces the whole description):"; printf '%s\n' "$desc"; }
    _m365_say "Note: this plan is shared; changes are visible to everyone on it."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was changed. Re-run with --execute to apply."; return 0; fi
    _m365_planner_require_write "$alias" || return 1
    # If-Match carries the etag read at the start of this run, so a task someone changed in the meantime is refused rather than overwritten.
    if [ "$patch" != "{}" ]; then
        _m365_http PATCH "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}")" "$patch" -H "If-Match: $(printf '%s' "$current" | jq -r '."@odata.etag"')" >/dev/null || { _m365_error "Update refused or failed; the task may have changed since it was read. Re-run to see its current state."; return 1; }
    fi
    if [ "$set_desc" -eq 1 ]; then
        details="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}/details")")" || return 1
        _m365_http PATCH "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}/details")" "$(jq -nc --arg d "$desc" '{description: $d}')" -H "If-Match: $(printf '%s' "$details" | jq -r '."@odata.etag"')" >/dev/null || { _m365_error "Description update refused or failed"; return 1; }
    fi
    readback="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}")")" || return 1
    after_details='{}'
    [ "$set_desc" -eq 1 ] && { after_details="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/${encoded}/details")")" || return 1; }
    ok="$(jq -n --argjson p "$patch" --argjson got "$readback" --argjson d "$after_details" --arg desc "$desc" --argjson setdesc "$set_desc" '
      (($p.title == null) or ($got.title == $p.title)) and
      (($p.bucketId == null) or ($got.bucketId == $p.bucketId)) and
      (($p | has("percentComplete") | not) or ($got.percentComplete == $p.percentComplete)) and
      (($p | has("dueDateTime") | not) or (($got.dueDateTime // null | if . then .[0:10] else null end) == ($p.dueDateTime | if . then .[0:10] else null end))) and
      ((($p.assignments // {}) | to_entries) | all(if .value == null then (($got.assignments // {}) | has(.key) | not) else (($got.assignments // {}) | has(.key)) end)) and
      ($setdesc == 0 or ($d.description == $desc))
    ')"
    _m365_planner_audit "$alias" update-task "$task_id" "$(printf '%s' "$readback" | jq -r '.title // ""')" "$ok" "$(printf '%s' "$patch" | jq -c --argjson s "$set_desc" 'if $s == 1 then . + {description: "(replaced)"} else . end')"
    [ "$ok" = true ] || { _m365_error "Update was sent but readback did not match the requested changes"; return 1; }
    _m365_say "Updated task (confirmed by readback): $(printf '%s' "$readback" | jq -r '.title') | task_id: $task_id"
}

# Experimental beta move: one conditional PATCH, never clone/delete or retry an ambiguous write.
_m365_planner_move() {
    local alias="${1:-}" task_id="" plan_id="" bucket="" execute=0 base url current details source target destination source_id etag patch changes after after_details ok
    [ -n "$alias" ] || { _m365_error "m365 planner move-task requires ALIAS"; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task|--plan|--bucket)
                [ -n "${2:-}" ] || { _m365_error "$1 requires ID"; return 1; }
                case "$1" in --task) task_id="$2" ;; --plan) plan_id="$2" ;; --bucket) bucket="$2" ;; esac
                shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 planner move-task option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] && [ -n "$plan_id" ] && [ -n "$bucket" ] || { _m365_error "move-task requires --task, --plan, and --bucket"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    _m365_planner_require_plan_allowed "$alias" "$plan_id" || return 1
    base="$(_m365_graph_base "$alias")" || return 1
    base="${base%/}"
    case "$base" in */v1.0) base="${base%/v1.0}/beta" ;; */beta) ;; *) _m365_error "Cannot derive beta Graph endpoint from graph_base"; return 1 ;; esac
    url="$base/planner/tasks/$(_m365_uri_encode "$task_id")"
    current="$(_m365_get "$alias" "$url")" || return 1
    source_id="$(printf '%s' "$current" | jq -er '.planId | select(type == "string" and length > 0)')" || return 1
    _m365_planner_require_plan_allowed "$alias" "$source_id" || return 1
    [ "$source_id" != "$plan_id" ] || { _m365_error "Task is already in the destination plan; use update-task for a bucket change"; return 1; }
    etag="$(printf '%s' "$current" | jq -er '."@odata.etag" | select(type == "string" and length > 0 and . != "*")')" || { _m365_error "Task has no usable ETag"; return 1; }
    details="$(_m365_get "$alias" "$url/details")" || return 1
    source="$(_m365_get "$alias" "$base/planner/plans/$(_m365_uri_encode "$source_id")")" || return 1
    target="$(_m365_get "$alias" "$base/planner/plans/$(_m365_uri_encode "$plan_id")")" || return 1
    destination="$(_m365_get "$alias" "$base/planner/buckets/$(_m365_uri_encode "$bucket")")" || return 1
    printf '%s' "$destination" | jq -e --arg p "$plan_id" --arg b "$bucket" '.planId == $p and .id == $b' >/dev/null || { _m365_error "Destination bucket does not belong to the destination plan"; return 1; }
    # Cross-container moves can drop assignees and group conversations; defer them until preservation is supported.
    jq -en --argjson s "$source" --argjson t "$target" '
      ($s.container.type == "group") and ($t.container.type == "group") and
      (($s.container.containerId // "") != "") and ($s.container.containerId == $t.container.containerId)
    ' >/dev/null || { _m365_error "Experimental move-task currently requires plans in the same Microsoft 365 group"; return 1; }
    printf '%s' "$current" | jq -e '
      ([((.appliedCategories // {}) | .[])] | any(. == true) | not) and
      (.recurrence == null) and (.creationSource == null)
    ' >/dev/null || { _m365_error "Move refused: labels, recurrence, or externally sourced tasks need separate review"; return 1; }
    patch="$(jq -nc --arg p "$plan_id" --arg b "$bucket" '{planId:$p,bucketId:$b}')" || return 1
    changes="$(jq -nc --argjson c "$current" --argjson p "$patch" '{from:{planId:$c.planId,bucketId:$c.bucketId},to:$p,api:"beta"}')" || return 1
    _m365_say "Microsoft 365 Planner move-task (experimental Graph beta):"
    _m365_say "Account: $alias | Task: $task_id"
    printf '%s' "$current" | jq '{title,planId,bucketId,percentComplete,dueDateTime,assignments}'
    _m365_say "Destination plan and bucket:"
    jq -n --argjson p "$target" --argjson b "$destination" '{plan:$p.title,planId:$p.id,bucket:$b.name,bucketId:$b.id}'
    _m365_say "Same-group move; description, checklist, references, dates, progress, priority, assignees, and conversation link will be checked after the PATCH. Plan-specific goals, custom columns, and linked meeting notes are not supported or verified."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was moved. Re-run with --execute to apply."; return 0; fi
    _m365_planner_require_write "$alias" || return 1
    # Audit the attempt before dispatch so transport failures and failed readbacks leave a trace.
    _m365_planner_audit "$alias" move-task-attempt "$task_id" "$(printf '%s' "$current" | jq -r '.title')" false "$changes"
    _m365_http PATCH "$alias" "$url" "$patch" -H "If-Match: $etag" >/dev/null || { _m365_error "Move failed or outcome is uncertain; inspect the task before retrying. No automatic retry was made."; return 1; }
    after="$(_m365_get "$alias" "$url")" && after_details="$(_m365_get "$alias" "$url/details")" || { _m365_error "Move was sent but readback failed; inspect the task before retrying"; return 1; }
    ok="$(jq -n --argjson before "$current" --argjson after "$after" --argjson d "$details" --argjson a "$after_details" --arg p "$plan_id" --arg b "$bucket" '
      def stable: {id,title,percentComplete,priority,startDateTime,dueDateTime,conversationThreadId,assignees:((.assignments // {}) | keys)};
      def content: {description:(.description // ""),checklist:(.checklist // {}),references:(.references // {})};
      ($after.planId == $p and $after.bucketId == $b) and
      (($before | stable) == ($after | stable)) and (($d | content) == ($a | content))
    ')" || return 1
    _m365_planner_audit "$alias" move-task "$task_id" "$(printf '%s' "$current" | jq -r '.title')" "$ok" "$changes"
    [ "$ok" = true ] || { _m365_error "Move was sent but preservation/readback checks failed; inspect the task before retrying"; return 1; }
    _m365_say "Moved task (confirmed by readback): $task_id | plan_id: $plan_id | bucket_id: $bucket"
}

##- Existing plan labels: names are resolved uniquely, never created or renamed.
_m365_planner_labels() {
    local alias="${1:-}" plan_id="" json_mode=0 details labels
    [ -n "$alias" ] || { _m365_error "m365 planner labels requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --plan) [ -n "${2:-}" ] || { _m365_error "--plan requires ID"; return 1; }; plan_id="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 planner labels option: $1"; return 1 ;;
        esac
    done
    [ -n "$plan_id" ] || { _m365_error "labels requires --plan ID"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    details="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/plans/$(_m365_uri_encode "$plan_id")/details")")" || return 1
    labels="$(printf '%s' "$details" | jq -c '[((.categoryDescriptions // {}) | to_entries[]) | select(.key | test("^category[1-9][0-9]*$")) | select(.value | type == "string" and length > 0) | {id: .key, name: .value}]')" || return 1
    if [ "$json_mode" -eq 1 ]; then printf '%s\n' "$labels"; else printf '%s' "$labels" | jq -r '.[] | "- " + .name + " | label_id: " + .id'; fi
}

_m365_planner_label() {
    local action="$1" alias="${2:-}" task_id="" label="" execute=0 current labels matches key wanted patch expected after ok
    [ -n "$alias" ] || { _m365_error "m365 planner $action requires ALIAS"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task) [ -n "${2:-}" ] || { _m365_error "--task requires ID"; return 1; }; task_id="$2"; shift 2 ;;
            --label) [ -n "${2:-}" ] || { _m365_error "--label requires NAME"; return 1; }; label="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 planner $action option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] && [ -n "$label" ] || { _m365_error "$action requires --task ID and --label NAME"; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    current="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")")" || return 1
    _m365_planner_require_plan_allowed "$alias" "$(printf '%s' "$current" | jq -r '.planId')" || return 1
    labels="$(_m365_planner_labels "$alias" --plan "$(printf '%s' "$current" | jq -r '.planId')" --json)" || return 1
    matches="$(printf '%s' "$labels" | jq -c --arg n "$label" '[.[] | select((.name | ascii_downcase) == ($n | ascii_downcase))]')" || return 1
    [ "$(printf '%s' "$matches" | jq length)" -eq 1 ] || { _m365_error "Label '$label' must match exactly one existing plan label (case-insensitive); use planner labels to inspect names"; return 1; }
    key="$(printf '%s' "$matches" | jq -r '.[0].id')"
    wanted=true
    [ "$action" = unlabel ] && wanted=false
    expected="$(printf '%s' "$current" | jq -c --arg k "$key" --argjson v "$wanted" '(.appliedCategories // {}) | with_entries(select(.key | test("^category[1-9][0-9]*$"))) | . + {($k): $v}')" || return 1
    _m365_say "Microsoft 365 Planner $action plan: $alias | task_id: $task_id | $(printf '%s' "$current" | jq -r '.title')"
    _m365_say "Label: $(printf '%s' "$matches" | jq -r '.[0].name') ($key) -> $wanted; other labels and task fields are preserved."
    _m365_say "Note: this plan is shared; changes are visible to everyone on it."
    if [ "$(printf '%s' "$current" | jq -r --arg k "$key" '.appliedCategories[$k] // false')" = "$wanted" ]; then
        _m365_say "No change: label already has the requested state."
        return 0
    fi
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was changed. Re-run with --execute to apply."; return 0; fi
    _m365_planner_require_write "$alias" || return 1
    # Recheck the name binding before the conditional task write; plan label names have a separate ETag and cannot be guarded atomically with the task.
    labels="$(_m365_planner_labels "$alias" --plan "$(printf '%s' "$current" | jq -r '.planId')" --json)" || return 1
    printf '%s' "$labels" | jq -e --arg n "$label" --arg k "$key" '[.[] | select((.name | ascii_downcase) == ($n | ascii_downcase))] | length == 1 and .[0].id == $k' >/dev/null || { _m365_error "Plan label names changed; inspect before retrying"; return 1; }
    patch="$(jq -nc --argjson c "$expected" '{appliedCategories: $c}')" || return 1
    _m365_planner_audit "$alias" "$action-attempt" "$task_id" "$(printf '%s' "$current" | jq -r '.title')" false "$patch" || return 1
    _m365_http PATCH "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")" "$patch" -H "If-Match: $(printf '%s' "$current" | jq -r '."@odata.etag"')" >/dev/null || { _m365_error "Label write refused or failed; outcome may be uncertain. Read the task before retrying; no automatic retry was made."; return 1; }
    after="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")")" || { _m365_error "Label write sent but readback failed; inspect the task before retrying"; return 1; }
    # Graph can omit false categories; compare active sets and every other task property except the server ETag.
    ok="$(jq -n --argjson e "$expected" --argjson b "$current" --argjson a "$after" 'def active: with_entries(select(.key | test("^category[1-9][0-9]*$"))) | with_entries(select(.value == true)); (($a.appliedCategories // {} | active) == ($e | active)) and (($a | del(."@odata.etag", .appliedCategories)) == ($b | del(."@odata.etag", .appliedCategories)))')" || return 1
    _m365_planner_audit "$alias" "$action" "$task_id" "$(printf '%s' "$current" | jq -r '.title')" "$ok" "$patch" || return 1
    [ "$ok" = true ] || { _m365_error "Label write sent but readback or preserved task fields did not match; inspect before retrying"; return 1; }
    _m365_say "Updated label (confirmed by readback): $label | task_id: $task_id"
}

_m365_planner_delete() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" task_id="" expected="" execute=0 verify=0 snapshot prepared receipt plan_id etag title root listing lookup request
    [ -n "$alias" ] || { _m365_error 'delete-task requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task|--expected-sha256)
                [ -n "${2:-}" ] || { _m365_error "$1 requires a value"; return 1; }
                case "$1" in --task) task_id="$2" ;; *) expected="$2" ;; esac
                shift 2 ;;
            --execute) execute=1; shift ;;
            --verify) verify=1; shift ;;
            *) _m365_error "Unknown delete-task option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] || { _m365_error 'delete-task requires --task ID'; return 1; }
    [ "$verify" -eq 0 ] || { [ "$execute" -eq 0 ] && [ -z "$expected" ]; } || { _m365_error '--verify is read-only and cannot be combined with execution options'; return 1; }
    _m365_require_enabled "$alias" planner || return 1
    root="$(dirname "$(_m365_planner_audit_path)")/planner-task-delete"
    if [ "$verify" -eq 1 ]; then
        prepared="$(_m365_planner_python "$PLANNER_DIR/scripts/task_delete.py" receipt --alias "$alias" --task "$task_id" --root "$root")" || return 1
        plan_id="$(printf '%s' "$prepared" | jq -er '.plan_id')" || return 1
        _m365_planner_require_plan_allowed "$alias" "$plan_id" || return 1
    else
        snapshot="$(_m365_planner_task "$alias" --task "$task_id" --json)" || return 1
        prepared="$(printf '%s' "$snapshot" | _m365_planner_python "$PLANNER_DIR/scripts/task_delete.py" prepare --alias "$alias" --task "$task_id")" || return 1
        plan_id="$(printf '%s' "$prepared" | jq -er '.plan_id')" || return 1
        _m365_planner_require_plan_allowed "$alias" "$plan_id" || return 1
        _m365_say "Planner task deletion preview: $alias | task_id: $task_id"
        printf '%s' "$snapshot" | jq '{task: (.task | {id,title,planId,bucketId,percentComplete,dueDateTime,assignments,appliedCategories}), details: (.details | {description,checklist,references})}'
        _m365_say 'Deletes this shared task. No undo/restore command is provided. Obtain isolated approval for this exact deletion.'
        _m365_say "Preview fingerprint: $(printf '%s' "$prepared" | jq -r '.fingerprint')"
        if [ "$execute" -ne 1 ]; then _m365_say 'DRY RUN: no task was deleted. Execution requires --expected-sha256 HASH --execute.'; return 0; fi
        _m365_planner_require_write "$alias" || return 1
        # A durable exclusive receipt is required before transport; even an uncertain failure cannot be replayed through this command.
        receipt="$(printf '%s' "$snapshot" | _m365_planner_python "$PLANNER_DIR/scripts/task_delete.py" claim --alias "$alias" --task "$task_id" --root "$root" --expected-sha256 "$expected")" || return 1
        etag="$(printf '%s' "$prepared" | jq -er '.etag')" || return 1
        title="$(printf '%s' "$prepared" | jq -r '.title')"
        _m365_planner_audit "$alias" delete-task-attempt "$task_id" "$title" false "$(printf '%s' "$prepared" | jq '{fingerprint,plan_id}')"
        _m365_http DELETE "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")" '' -H "If-Match: $etag" >/dev/null || { _m365_error "Deletion failed or is uncertain. Receipt: $receipt. Use delete-task --task $task_id --verify; do not replay the write."; return 1; }
    fi
    listing="$M365_WORK/remaining-tasks.json"
    M365_REQUIRE_COMPLETE=1 _m365_get_paginated "$alias" "$(_m365_planner_max_tasks "$alias")" "$listing" "$(_m365_planner_url "$alias" "planner/plans/$(_m365_uri_encode "$plan_id")/tasks")" || { _m365_error 'Deletion verification failed; inspect the receipt and use --verify. No write will be repeated.'; return 1; }
    request="$M365_WORK/task-lookup-request.json"; lookup="$M365_WORK/task-lookup.json"
    jq -nc --arg task "$task_id" '[{method:"GET",url:("/planner/tasks/"+($task|@uri))}]' > "$request" || return 1
    _m365_batch "$alias" "$request" "$lookup" || { _m365_error 'Exact task absence is unverified; retain the deletion receipt and do not replay.'; return 1; }
    jq -e 'length==1 and .[0].id=="0" and .[0].status==404 and (.[0].body.error|type=="object")' "$lookup" >/dev/null || { _m365_error 'The exact task still exists or its read was denied/failed; absence from the original plan does not confirm deletion.'; return 1; }
    _m365_planner_python "$PLANNER_DIR/scripts/task_delete.py" confirm --alias "$alias" --task "$task_id" --root "$root" < "$listing" >/dev/null || return 1
    title="$(printf '%s' "$prepared" | jq -r '.title')"
    _m365_planner_audit "$alias" delete-task "$task_id" "$title" true "$(printf '%s' "$prepared" | jq '{fingerprint,plan_id}')"
    _m365_say "Task deletion confirmed by complete plan readback: $task_id"
)

##- Explicit legacy group-comment reads; no legacy write path or broader OAuth scopes.
_m365_planner_legacy_access() {
    local alias="$1" context
    [ "$(_m365_auth_provider "$alias")" = graph-powershell ] || { _m365_error "Comment scope inspection currently supports graph-powershell only; no authorization was changed"; return 1; }
    context="$(_m365_powershell_auth "$alias" "")" || return 1
    printf '%s' "$context" | jq -e 'any(.effective_scopes[]?; . == "Group.Read.All" or . == "Group.ReadWrite.All" or . == "Group-Conversation.Read.All" or . == "Group-Conversation.ReadWrite.All")' >/dev/null || { _m365_error "Legacy reads need existing group-conversation read permission. No permission was requested."; return 1; }
}

_m365_planner_comment_posts() {
    local alias="$1" group="$2" thread="$3" url root page merged='{"value":[]}' count=0
    root="$(_m365_planner_url "$alias" "groups/$(_m365_uri_encode "$group")/threads/$(_m365_uri_encode "$thread")/posts")"
    url="$root"
    while [ -n "$url" ]; do
        count=$((count + 1))
        [ "$count" -le 20 ] || { _m365_error "Comment pagination exceeds 20 pages; refusing incomplete duplicate check"; return 1; }
        case "$url" in "$root"|"$root"\?*) ;; *) _m365_error "Unexpected comment pagination target"; return 1 ;; esac
        page="$(_m365_get "$alias" "$url")" || return 1
        printf '%s' "$page" | jq -e '.value | type == "array"' >/dev/null || return 1
        merged="$(jq -nc --argjson a "$merged" --argjson b "$page" '{value: ($a.value + $b.value)}')" || return 1
        [ "$(printf '%s' "$merged" | jq '.value | length')" -le 1000 ] || { _m365_error "More than 1000 comments; refusing incomplete duplicate check"; return 1; }
        url="$(printf '%s' "$page" | jq -r '."@odata.nextLink" // empty')"
    done
    printf '%s\n' "$merged"
}

# Task chat is separate from conversationThreadId / legacy group comments.
_m365_planner_chat_posts() (
    local alias="$1" task_id="$2" root url page next count=0 merged='{"value":[]}' err
    _m365_work_begin || return 1
    root="https://graph.microsoft.com/beta/planner/tasks/$(_m365_uri_encode "$task_id")/messages"
    url="$root"; err="$M365_WORK/chat-error"
    while [ -n "$url" ]; do
        count=$((count + 1))
        [ "$count" -le 20 ] || { _m365_error 'Task chat pagination exceeded 20 pages; no write is safe'; return 1; }
        case "$url" in "$root"|"$root"\?*) ;; *) _m365_error 'Unexpected Task chat pagination target'; return 1 ;; esac
        if ! page="$(_m365_get "$alias" "$url" 2>"$err")"; then
            if [ "$count" -eq 1 ] && grep -Fq "Task $task_id does not have an associated chat thread. Create a message on the task first to initialize the thread" "$err"; then
                printf '%s\n' '{"value":[]}'
                return 0
            fi
            cat "$err" >&2; return 1
        fi
        page="$(printf '%s' "$page" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" validate "$task_id")" || return 1
        merged="$(jq -nc --argjson a "$merged" --argjson b "$page" '{value:($a.value+$b.value)}')" || return 1
        [ "$(printf '%s' "$merged" | jq '.value|length')" -le 1000 ] || { _m365_error 'Task chat exceeds 1000 messages; incomplete duplicate check refused'; return 1; }
        next="$(printf '%s' "$page" | jq -r '."@odata.nextLink" // empty')"
        # Task chat also returns a polling cursor on an empty final page.
        if [ "$next" = "$url" ]; then
            [ "$(printf '%s' "$page" | jq '.value|length')" -eq 0 ] || { _m365_error 'Task chat repeated a nonempty pagination cursor'; return 1; }
            break
        fi
        url="$next"
    done
    printf '%s' "$merged" | jq 'if ([.value[].id]|length) != ([.value[].id]|unique|length) then error("Repeated Task chat message IDs") else . end'
)

_m365_planner_chat_journal() {
    _m365_planner_python "$PLANNER_DIR/scripts/chat_journal.py" "$@"
}

_m365_planner_legacy_read() {
    local alias="$1" task_id="$2" current="$3" json_mode="$4" plan group thread posts='{"value":[]}'
    _m365_planner_legacy_access "$alias" || return 1
    plan="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/plans/$(printf '%s' "$current" | jq -r '.planId|@uri')")")" || return 1
    group="$(printf '%s' "$plan" | jq -r '.container.containerId // .owner // empty')"
    [ -n "$group" ] || { _m365_error 'Legacy comments require a group-backed plan'; return 1; }
    thread="$(printf '%s' "$current" | jq -r '.conversationThreadId // empty')"
    [ -z "$thread" ] || posts="$(_m365_planner_comment_posts "$alias" "$group" "$thread")" || return 1
    if [ "$json_mode" -eq 1 ]; then
        jq -n --arg task "$task_id" --arg thread "$thread" --argjson p "$posts" '{task_id:$task,route:"legacy-group",thread_id:$thread,posts:$p.value}'
    else
        _m365_say 'Legacy group comments (not current Task chat):'
        printf '%s' "$posts" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" render
    fi
}

_m365_planner_comments() (
    local mode="$1" alias="${2:-}" task_id="" file="" format=markdown message="" expected="" execute=0 json_mode=0 legacy=0 current posts prepared matches target prior hash recovery key journal lock state saved_hash saved_id created after ok tenant link
    [ -n "$alias" ] || { _m365_error "planner $mode requires ALIAS"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --task|--file|--format|--message|--expected-sha256)
                [ -n "${2:-}" ] || { _m365_error "$1 requires a value"; return 1; }
                case "$1" in --task) task_id="$2" ;; --file) file="$2" ;; --format) format="$2" ;; --message) message="$2" ;; --expected-sha256) expected="$2" ;; esac
                shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            --json) json_mode=1; shift ;;
            --legacy) legacy=1; shift ;;
            *) _m365_error "Unknown planner $mode option: $1"; return 1 ;;
        esac
    done
    [ -n "$task_id" ] || { _m365_error "$mode requires --task ID"; return 1; }
    if [ "$mode" = comments ]; then
        [ -z "$file$message$expected" ] && [ "$execute" -eq 0 ] || { _m365_error 'comments is read-only'; return 1; }
    else
        [ "$legacy" -eq 0 ] && [ "$json_mode" -eq 0 ] || { _m365_error 'Writes support Task chat only; --legacy and --json are read-only'; return 1; }
        [ -f "$file" ] || { _m365_error "$mode requires --file PATH"; return 1; }
        if [ "$mode" = edit-comment ]; then
            [ -n "$message" ] || { _m365_error 'edit-comment requires --message ID'; return 1; }
        else
            [ -z "$message$expected" ] || { _m365_error 'Only edit-comment accepts --message and --expected-sha256'; return 1; }
        fi
        prepared="$(_m365_planner_python "$PLANNER_DIR/scripts/comments.py" prepare "$file" "$format")" || return 1
        hash="$(printf '%s' "$prepared" | jq -r '.sha256')"
    fi
    _m365_require_enabled "$alias" planner || return 1
    current="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")")" || return 1
    printf '%s' "$current" | jq -e --arg t "$task_id" '.id==$t and (.planId|type=="string")' >/dev/null || { _m365_error 'Task identity mismatch'; return 1; }
    _m365_planner_require_plan_allowed "$alias" "$(printf '%s' "$current" | jq -r '.planId')" || return 1
    if [ "$legacy" -eq 1 ]; then _m365_planner_legacy_read "$alias" "$task_id" "$current" "$json_mode"; return; fi
    tenant="$(_m365_planner_tenant "$alias")" || return 1
    link="$(printf '%s' "$current" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" task-url "$tenant")" || return 1
    posts="$(_m365_planner_chat_posts "$alias" "$task_id")" || return 1
    if [ "$mode" = comments ]; then
        if [ "$json_mode" -eq 1 ]; then jq -n --arg task "$task_id" --arg url "$link" --argjson p "$posts" '{task_id:$task,task_url:$url,route:"task-chat",messages:$p.value}'; else _m365_say "Task chat: $link"; printf '%s' "$posts" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" render; fi
        return
    fi
    if [ "$mode" = edit-comment ]; then
        target="$(printf '%s' "$posts" | jq --arg id "$message" '{value:[.value[]|select(.id==$id and (.deletedTime//.deletedDateTime//null)==null)]}')"
        [ "$(printf '%s' "$target" | jq '.value|length')" -eq 1 ] || { _m365_error 'Exact live message not found on this task'; return 1; }
        [ "$(printf '%s' "$target" | jq -r '.value[0].createdBy.user.id')" = "$(_m365_planner_my_id "$alias")" ] || { _m365_error 'Only messages authored by the current account can be edited'; return 1; }
        [ "$(printf '%s' "$target" | jq '.value[0].mentions // [] | length')" -eq 0 ] || { _m365_error 'Editing messages with mentions is not supported; preserve them and review separately'; return 1; }
        prior="$(printf '%s' "$target" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" hash "$message")" || return 1
    else target="$posts"; prior=""; fi
    matches="$(printf '%s' "$target" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" match "$file" "$format")" || return 1
    umask 077
    recovery="$(dirname "$(_m365_planner_audit_path)")/planner-task-chat"
    [ ! -L "$recovery" ] || { _m365_error "Task chat recovery directory cannot be a symlink"; return 1; }
    mkdir -p "$recovery" || return 1
    key="$(printf '%s' "$alias/$task_id" | _m365_planner_python -c 'import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
    lock="$recovery/$key.lock"
    mkdir "$lock" 2>/dev/null || { _m365_error "Task chat operation locked: $lock"; return 1; }
    trap 'rmdir "$lock"' EXIT
    trap 'exit 130' HUP INT TERM
    trap 'exit 141' PIPE
    # The initial preview was read before taking the shared task lock; do not dispatch from that stale view.
    local fresh_posts
    fresh_posts="$(_m365_planner_chat_posts "$alias" "$task_id")" || return 1
    [ "$(printf '%s' "$fresh_posts" | jq -Sc '.value|sort_by(.id)')" = "$(printf '%s' "$posts" | jq -Sc '.value|sort_by(.id)')" ] || { _m365_error 'Task chat changed while acquiring the lock; prepare a fresh preview. No write was sent.'; return 1; }
    journal="$recovery/$key.json"
    if [ "$mode" = edit-comment ]; then journal="$recovery/$key-edit-$(printf '%s' "$message" | _m365_planner_python -c 'import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())').json"; fi
    state=""; saved_hash=""; saved_id=""
    [ ! -L "$journal" ] || { _m365_error "Task chat recovery file cannot be a symlink"; return 1; }
    if [ -f "$journal" ]; then
        state="$(jq -r '.state' "$journal")"; saved_hash="$(jq -r '.hash' "$journal")"; saved_id="$(jq -r '.message_id // empty' "$journal")"
        if [ "$state" != verified ]; then
            [ "$saved_hash" = "$hash" ] || { _m365_error "Unresolved Task chat write: $journal; no different write sent"; return 1; }
            [ "$(printf '%s' "$matches" | jq length)" -gt 0 ] || { _m365_error "Prior Task chat outcome remains uncertain: $journal; no retry sent"; return 1; }
            if [ -z "$saved_id" ]; then
                [ "$(printf '%s' "$matches" | jq length)" -eq 1 ] || { _m365_error 'Ambiguous matching messages after uncertain create; inspect without reposting'; return 1; }
                printf '%s' "$posts" | jq -e --arg id "$(printf '%s' "$matches" | jq -r '.[0]')" --arg me "$(_m365_planner_my_id "$alias")" 'any(.value[]; .id==$id and .createdBy.user.id==$me)' >/dev/null || { _m365_error 'A matching message by another author cannot resolve this uncertain write'; return 1; }
            fi
            if [ -n "$saved_id" ]; then printf '%s' "$matches" | jq -e --arg id "$saved_id" 'index($id)!=null' >/dev/null || { _m365_error 'Pending message ID differs from content match'; return 1; }; fi
        elif [ "$saved_hash" = "$hash" ] && [ "$(printf '%s' "$matches" | jq length)" -eq 0 ]; then
            _m365_error 'Previously verified content is now missing or edited; inspect before repeating'; return 1
        fi
    fi
    if [ "$(printf '%s' "$matches" | jq length)" -gt 0 ]; then
        [ "$execute" -eq 0 ] || _m365_planner_chat_journal "$journal" verified "$mode" "$hash" "$(printf '%s' "$matches" | jq -r '.[0]')" || return 1
        _m365_say "No change: matching content and links already exist in actual Task chat | message_ids: $matches | $link"
        return 0
    fi
    _m365_say "Planner Task chat $mode plan: $alias | $link"
    if [ "$mode" = edit-comment ]; then _m365_say "Edit message: $message | current fingerprint: $prior"; fi
    _m365_say 'Exact sanitized HTML (link labels and destinations are part of verification):'
    printf '%s' "$prepared" | jq -r '.content'
    if [ "$execute" -ne 1 ]; then _m365_say 'DRY RUN: no Task chat message was written.'; return 0; fi
    _m365_planner_require_write "$alias" || return 1
    if [ "$mode" = edit-comment ]; then
        [ -n "$expected" ] && [ "$expected" = "$prior" ] || { _m365_error 'Edit requires --expected-sha256 from the current preview; message has changed or approval target is missing'; return 1; }
    fi
    _m365_planner_chat_journal "$journal" pending "$mode" "$hash" "$message" || return 1
    _m365_planner_audit "$alias" "task-chat-$mode-attempt" "$task_id" "$(printf '%s' "$current" | jq -r '.title')" false "$(jq -nc --arg h "$hash" --arg m "$message" '{content_sha256:$h,message_id:$m}')"
    if [ "$mode" = comment ]; then
        created="$(_m365_write POST "$alias" "https://graph.microsoft.com/beta/planner/tasks/$(_m365_uri_encode "$task_id")/messages" "$(printf '%s' "$prepared" | jq '{content}')")" || { _m365_error "Task chat create failed or is uncertain: $journal; inspect before retrying"; return 1; }
    else
        created="$(_m365_write PATCH "$alias" "https://graph.microsoft.com/beta/planner/tasks/$(_m365_uri_encode "$task_id")/messages/$(_m365_uri_encode "$message")" "$(printf '%s' "$prepared" | jq '{content}')")" || { _m365_error "Task chat edit failed or is uncertain: $journal; inspect before retrying"; return 1; }
    fi
    saved_id="$(printf '%s' "$created" | jq -r '.id // empty')"
    [ -n "$saved_id" ] && printf '%s' "$created" | jq -e --arg t "$task_id" '.parentEntityId==$t' >/dev/null || { _m365_error "Task chat response identity mismatch; inspect $journal"; return 1; }
    [ "$mode" != edit-comment ] || [ "$saved_id" = "$message" ] || { _m365_error 'Edit returned another message ID'; return 1; }
    _m365_planner_chat_journal "$journal" pending "$mode" "$hash" "$saved_id" || return 1
    posts="$(_m365_planner_chat_posts "$alias" "$task_id")" || { _m365_error "Write sent but actual Task chat readback failed: $journal"; return 1; }
    target="$(printf '%s' "$posts" | jq --arg id "$saved_id" '{value:[.value[]|select(.id==$id)]}')"
    matches="$(printf '%s' "$target" | _m365_planner_python "$PLANNER_DIR/scripts/comments.py" match "$file" "$format")" || return 1
    [ "$(printf '%s' "$matches" | jq length)" -eq 1 ] || { _m365_error "Task chat content or inline links failed readback: $journal"; return 1; }
    after="$(_m365_get "$alias" "$(_m365_planner_url "$alias" "planner/tasks/$(_m365_uri_encode "$task_id")")")" || return 1
    ok="$(jq -n --argjson a "$after" --argjson b "$current" '($a|del(."@odata.etag"))==($b|del(."@odata.etag"))')"
    [ "$ok" = true ] || { _m365_error 'Message exists but task fields changed during operation; inspect before claiming preservation'; return 1; }
    _m365_planner_chat_journal "$journal" verified "$mode" "$hash" "$saved_id" || return 1
    _m365_planner_audit "$alias" "task-chat-$mode" "$task_id" "$(printf '%s' "$current" | jq -r '.title')" true "$(jq -nc --arg h "$hash" --arg m "$saved_id" '{content_sha256:$h,message_id:$m}')"
    _m365_say "Actual Task chat message confirmed by API readback | message_id: $saved_id | $link"
    _m365_say 'Browser rendering has not been visually verified.'
)

_m365_planner_dispatch() {
    case "${1:-}" in
        plans) shift; _m365_planner_plans "$@" ;;
        comments|comment|edit-comment) _m365_planner_comments "$@" ;;
        labels) shift; _m365_planner_labels "$@" ;;
        label|unlabel) _m365_planner_label "$@" ;;
        buckets) shift; _m365_planner_buckets "$@" ;;
        tasks) shift; _m365_planner_tasks "$@" ;;
        task) shift; _m365_planner_task "$@" ;;
        export) shift; _m365_planner_export "$@" ;;
        create-task) shift; _m365_planner_create "$@" ;;
        update-task) shift; _m365_planner_update "$@" ;;
        delete-task) shift; _m365_planner_delete "$@" ;;
        move-task) shift; _m365_planner_move "$@" ;;
        *) _m365_error "Unknown m365 planner command: ${1:-}"; return 1 ;;
    esac
}
