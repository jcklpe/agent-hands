#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-microsoft/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
M365_PYTHON="${M365_PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
refute() { if "$@"; then printf 'Expected failure\n' >&2; exit 1; fi; }
_m365_graph_base() { printf https://graph.microsoft.com/v1.0; }
# Out-of-order replies are normalized; missing or duplicate replies fail before replacing output.
jq -n '[range(21) | {method:"GET",url:("/tasks/" + tostring)}]' > "$WORK/requests"
MODE=good
_m365_write() {
    printf '%s' "$4" | jq --arg mode "$MODE" '{responses: ([.requests[] | {id:.id,status:200,body:{id:("task-" + .id)}}] | reverse | if $mode == "missing" then .[1:] elif $mode == "duplicate" then . + [.[0]] else . end)}'
}
_m365_batch example "$WORK/requests" "$WORK/replies"
jq -e 'length == 21 and .[0].id == "0" and .[20].id == "20"' "$WORK/replies" >/dev/null
for MODE in missing duplicate; do
    printf previous > "$WORK/replies"
    refute _m365_batch example "$WORK/requests" "$WORK/replies" >/dev/null 2>&1
    [ "$(cat "$WORK/replies")" = previous ]
done
MODE=good
# Preserve old exports on a requested task-detail failure, not a fresh-looking partial snapshot.
_m365_require_enabled() { :; }
_m365_planner_configured_ids() { printf 'plan-1\n'; }
_m365_account_value() {
    case "$2" in
        *max_tasks*) printf 500 ;;
        *description_character_limit*) printf 2000 ;;
        *plans*) printf '[{"id":"plan-1","name":"Example"}]' ;;
        *) return 1 ;;
    esac
}
_m365_get() {
    case "$2" in
        */plans/plan-1) printf '{"id":"plan-1","title":"Example"}' ;;
        */plans/plan-1/details) printf '{"categoryDescriptions":{}}' ;;
        *) return 1 ;;
    esac
}
_m365_get_paginated() {
    case "$4" in
        */tasks) printf '{"value":[{"id":"task-1","title":"Example task","hasDescription":true,"assignments":{}}]}' > "$3" ;;
        */buckets) printf '{"value":[]}' > "$3" ;;
        *) return 1 ;;
    esac
}
DETAIL_STATUS=403
_m365_write() {
    printf '%s' "$4" | jq --argjson status "$DETAIL_STATUS" '{responses:[.requests[] | {id:.id,status:$status,body:{id:"task-1",description:"Example description"}}]}'
}
_m365_profile_email() { printf person@example.com; }
_m365_planner_my_id() { printf user-example; }
printf previous > "$WORK/export.md"
refute _m365_planner_export example --output "$WORK/export.md" >/dev/null 2>&1
[ "$(cat "$WORK/export.md")" = previous ]
DETAIL_STATUS=200
_m365_planner_export example --output "$WORK/export.md" >/dev/null
grep -F 'Example description' "$WORK/export.md" >/dev/null
ln -s "$WORK/export.md" "$WORK/link.md"
refute _m365_planner_export example --output "$WORK/link.md" >/dev/null 2>&1
printf 'Planner export and batch checks passed\n'
