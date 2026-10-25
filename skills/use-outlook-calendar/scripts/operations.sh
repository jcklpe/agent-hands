#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then _calendar_source="${(%):-%x}"; else _calendar_source="${BASH_SOURCE[0]}"; fi
OUTLOOK_CALENDAR_DIR="$(cd "$(dirname "$_calendar_source")/.." && pwd)"
unset _calendar_source
_m365_calendar_write_helper() { _m365_python "$OUTLOOK_CALENDAR_DIR" "$OUTLOOK_CALENDAR_DIR/scripts/write.py" "$@"; }
_m365_calendar_render_helper() { _m365_python "$OUTLOOK_CALENDAR_DIR" "$OUTLOOK_CALENDAR_DIR/scripts/render.py" "$@"; }
_m365_calendar_timezone() { _m365_account_value "$1" '.calendar.timezone // "UTC"'; }
_m365_calendar_window() {
    local back ahead
    back="$(_m365_account_value "$1" '.calendar.days_back // 14')" || return 1
    ahead="$(_m365_account_value "$1" '.calendar.days_ahead // 30')" || return 1
    _m365_python "$OUTLOOK_CALENDAR_DIR" "$OUTLOOK_CALENDAR_DIR/scripts/window.py" "$back" "$ahead"
}
_m365_resolve_attendees() {
    local email
    _RESOLVED_EMAILS=(); _RESOLVED_DISPLAY=()
    for email in "$@"; do
        case "$email" in *@?*.?*) ;; *) _m365_error 'Pass a full attendee email; private nickname resolution belongs to the caller'; return 1 ;; esac
        _RESOLVED_EMAILS+=("$email"); _RESOLVED_DISPLAY+=("$email")
    done
}

_m365_calendar_ids() {
    local alias="$1"
    jq -r --arg alias "$alias" '.accounts[] | select(.alias == $alias) | (.calendar.calendar_ids // ["primary"])[]' "$(_m365_accounts_path)"
}

_m365_calendar_writable_ids() {
    local alias="$1"
    jq -r --arg alias "$alias" '.accounts[] | select(.alias == $alias) | (.calendar.writable_calendar_ids // ["primary"])[]' "$(_m365_accounts_path)"
}

_m365_calendar_is_writable() {
    local alias="$1" requested="$2" value
    while IFS= read -r value || [ -n "$value" ]; do
        [ "$value" = "$requested" ] && return 0
    done <<EOF
$(_m365_calendar_writable_ids "$alias")
EOF
    return 1
}

_m365_calendar_list() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" json
    [ -n "$alias" ] || { _m365_error "m365 calendar list-calendars requires ALIAS"; return 1; }
    _m365_require_enabled "$alias" calendar || return 1
    json="$(mktemp "$M365_WORK/calendars.XXXXXX")" || return 1
    _m365_get_paginated "$alias" 500 "$json" "$(_m365_graph_base "$alias")/me/calendars" \
        --data-urlencode "\$top=500" \
        --data-urlencode "\$select=id,name,isDefaultCalendar,canEdit,canShare,owner" || return 1
    jq -r '
      (.value // [])[] |
      "- " + (.name // "Untitled calendar") +
      " | id: " + (.id // "") +
      " | default: " + ((.isDefaultCalendar // false) | tostring) +
      " | editable: " + ((.canEdit // false) | tostring)
    ' "$json"
)

_m365_calendar_path() {
    local alias="$1" calendar_id="$2" suffix="$3" encoded
    if [ "$calendar_id" = "primary" ]; then
        printf '%s/me/calendar/%s\n' "$(_m365_graph_base "$alias")" "$suffix"
    else
        encoded="$(_m365_uri_encode "$calendar_id")" || return 1
        printf '%s/me/calendars/%s/%s\n' "$(_m365_graph_base "$alias")" "$encoded" "$suffix"
    fi
}

_m365_calendar_fetch() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" from="$2" to="$3" calendar_ids="$4" out="$5" timezone calendar_id meta events item dir endpoint encoded
    local items=()
    # Optional sixth argument selects the response timezone for an explicit caller conversion.
    timezone="${6:-$(_m365_calendar_timezone "$alias")}"
    dir="$(mktemp -d "$M365_WORK/calendar.XXXXXX")" || return 1
    while IFS= read -r calendar_id || [ -n "$calendar_id" ]; do
        calendar_id="$(_m365_trim "$calendar_id")"
        [ -n "$calendar_id" ] || continue
        meta="${dir}/${#items[@]}-meta.json"
        events="${dir}/${#items[@]}-events.json"
        item="${dir}/${#items[@]}-item.json"
        if [ "$calendar_id" = "primary" ]; then
            _m365_get "$alias" "$(_m365_graph_base "$alias")/me/calendar" \
                --data-urlencode "\$select=id,name,isDefaultCalendar,canEdit,owner" > "$meta" || return 1
        else
            encoded="$(_m365_uri_encode "$calendar_id")" || return 1
            _m365_get "$alias" "$(_m365_graph_base "$alias")/me/calendars/${encoded}" \
                --data-urlencode "\$select=id,name,isDefaultCalendar,canEdit,owner" > "$meta" || return 1
        fi
        endpoint="$(_m365_calendar_path "$alias" "$calendar_id" 'calendarView')" || return 1
        _m365_say "Syncing Microsoft 365 calendar: $(jq -r '.name // .id // "Calendar"' "$meta")" >&2
        _m365_get_paginated "$alias" 1000 "$events" "$endpoint" \
            --data-urlencode "startDateTime=${from}" \
            --data-urlencode "endDateTime=${to}" \
            --data-urlencode "\$top=1000" \
            --data-urlencode "\$select=id,iCalUId,subject,body,bodyPreview,start,end,isAllDay,isCancelled,isOnlineMeeting,onlineMeeting,location,organizer,attendees,webLink,type,seriesMasterId" \
            -H "Prefer: outlook.timezone=\"${timezone}\"" \
            -H 'Prefer: outlook.body-content-type="text"' || return 1
        jq -n --arg requested "$calendar_id" --slurpfile meta "$meta" --slurpfile events "$events" '{id: $requested, graphId: ($meta[0].id // ""), name: ($meta[0].name // $requested), events: ($events[0].value // [])}' > "$item" || return 1
        items+=("$item")
    done <<EOF
$(printf '%s\n' "$calendar_ids" | tr ' ' '\n')
EOF
    if [ "${#items[@]}" -eq 0 ]; then
        jq -n '{calendars: []}' > "$out"
    else
        jq -s '{calendars: .}' "${items[@]}" > "$out"
    fi
)

_m365_calendar_find_human() {
    jq -r '
      (.items // [])[] |
      [
        ("- " + (.subject // "Untitled event")),
        ("calendar: " + (._calendar_name // ._calendar_id // "")),
        ("calendar_id: " + (._calendar_id // "")),
        ("event_id: " + (.id // "")),
        ("start: " + (.start.dateTime // "")),
        ("end: " + (.end.dateTime // "")),
        (if ((.location.displayName // "") != "") then "location: " + .location.displayName else empty end),
        (if ((.webLink // "") != "") then .webLink else empty end)
      ] | join(" | ")
    '
}

_m365_calendar_find() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" query="" from="" to="" calendar_id="" json_mode=0 window ids data results
    [ -n "$alias" ] || { _m365_error "m365 calendar find requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --from) [ -n "${2:-}" ] || { _m365_error "--from requires YYYY-MM-DD"; return 1; }; from="${2}T00:00:00Z"; shift 2 ;;
            --to) [ -n "${2:-}" ] || { _m365_error "--to requires YYYY-MM-DD"; return 1; }; to="${2}T23:59:59Z"; shift 2 ;;
            --calendar) [ -n "${2:-}" ] || { _m365_error "--calendar requires ID"; return 1; }; calendar_id="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            -*) _m365_error "Unknown m365 calendar find option: $1"; return 1 ;;
            *) if [ -z "$query" ]; then query="$1"; shift; else _m365_error "Unexpected argument: $1"; return 1; fi ;;
        esac
    done
    [ -n "$query" ] || { _m365_error "m365 calendar find requires QUERY"; return 1; }
    _m365_require_enabled "$alias" calendar || return 1
    window="$(_m365_calendar_window "$alias")" || return 1
    [ -n "$from" ] || from="$(printf '%s\n' "$window" | sed -n '1p')"
    [ -n "$to" ] || to="$(printf '%s\n' "$window" | sed -n '2p')"
    if [ -n "$calendar_id" ]; then ids="$calendar_id"; else ids="$(printf '%s\n' "$(_m365_calendar_ids "$alias")" | tr '\n' ' ')"; fi
    data="$(mktemp "$M365_WORK/calendar-find.XXXXXX")" || return 1
    results="$(mktemp "$M365_WORK/calendar-results.XXXXXX")" || return 1
    _m365_calendar_fetch "$alias" "$from" "$to" "$ids" "$data" || return 1
    jq --arg q "$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')" '{items: [(.calendars // [])[] as $calendar | ($calendar.events // [])[] | select((((.subject // "") + " " + (.bodyPreview // "") + " " + (.location.displayName // "")) | ascii_downcase | contains($q))) | . + {_calendar_id: $calendar.id, _calendar_name: $calendar.name}]}' "$data" > "$results" || return 1
    if [ "$json_mode" -eq 1 ]; then
        cat "$results"
    elif [ "$(jq '(.items // []) | length' "$results")" -eq 0 ]; then
        _m365_say "No matching Microsoft 365 events found."
    else
        _m365_calendar_find_human < "$results"
    fi
)

_m365_calendar_event_url() {
    local alias="$1" calendar_id="$2" event_id="${3:-}" encoded event_encoded base
    base="$(_m365_graph_base "$alias")"
    if [ "$calendar_id" = "primary" ]; then
        if [ -n "$event_id" ]; then event_encoded="$(_m365_uri_encode "$event_id")" || return 1; printf '%s/me/events/%s\n' "$base" "$event_encoded"; else printf '%s/me/calendar/events\n' "$base"; fi
    else
        encoded="$(_m365_uri_encode "$calendar_id")" || return 1
        if [ -n "$event_id" ]; then event_encoded="$(_m365_uri_encode "$event_id")" || return 1; printf '%s/me/calendars/%s/events/%s\n' "$base" "$encoded" "$event_encoded"; else printf '%s/me/calendars/%s/events\n' "$base" "$encoded"; fi
    fi
}

_m365_calendar_create() {
    local alias="${1:-}" calendar_id="primary" title="" start="" end="" tz="" location="" desc="" desc_file="" notify=0 execute=0 body created
    local attendees_raw=() build_args=()
    [ -n "$alias" ] || { _m365_error "m365 calendar create-event requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --calendar) [ -n "${2:-}" ] || { _m365_error "--calendar requires ID"; return 1; }; calendar_id="$2"; shift 2 ;;
            --title) [ -n "${2:-}" ] || { _m365_error "--title requires TEXT"; return 1; }; title="$2"; shift 2 ;;
            --start) [ -n "${2:-}" ] || { _m365_error "--start requires DATE or DATETIME"; return 1; }; start="$2"; shift 2 ;;
            --end) [ -n "${2:-}" ] || { _m365_error "--end requires DATE or DATETIME"; return 1; }; end="$2"; shift 2 ;;
            --tz) [ -n "${2:-}" ] || { _m365_error "--tz requires ZONE"; return 1; }; tz="$2"; shift 2 ;;
            --location) [ -n "${2+x}" ] || { _m365_error "--location requires TEXT"; return 1; }; location="$2"; shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _m365_error "--desc requires TEXT"; return 1; }; desc="$2"; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _m365_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; shift 2 ;;
            --attendee) [ -n "${2:-}" ] || { _m365_error "--attendee requires NAME or EMAIL"; return 1; }; attendees_raw+=("$2"); shift 2 ;;
            --notify) notify=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 calendar create-event option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" calendar || return 1
    [ -n "$title" ] || { _m365_error "create-event requires --title"; return 1; }
    [ -n "$start" ] || { _m365_error "create-event requires --start"; return 1; }
    _m365_calendar_is_writable "$alias" "$calendar_id" || { _m365_error "Calendar '$calendar_id' is not writable for alias '$alias'"; return 1; }
    if [ "${#attendees_raw[@]}" -gt 0 ] && [ "$notify" -ne 1 ]; then
        _m365_error "Microsoft may email invitations when an event has attendees. Re-run with --notify to acknowledge that blast radius."
        return 1
    fi
    if [ -n "$desc_file" ]; then [ -f "$desc_file" ] || { _m365_error "Description file does not exist: $desc_file"; return 1; }; desc="$(cat "$desc_file")"; fi
    [ -n "$tz" ] || tz="$(_m365_calendar_timezone "$alias")"
    if [ "${#attendees_raw[@]}" -gt 0 ]; then _m365_resolve_attendees "${attendees_raw[@]}" || return 1; else _RESOLVED_EMAILS=(); _RESOLVED_DISPLAY=(); fi
    build_args=(event --title "$title" --start "$start")
    [ -n "$end" ] && build_args+=(--end "$end")
    [ -n "$tz" ] && build_args+=(--tz "$tz")
    [ -n "$location" ] && build_args+=(--location "$location")
    [ -n "$desc" ] && build_args+=(--description "$desc")
    local email
    for email in ${_RESOLVED_EMAILS[@]+"${_RESOLVED_EMAILS[@]}"}; do build_args+=(--attendee "$email"); done
    body="$(_m365_calendar_write_helper "${build_args[@]}")" || return 1
    _m365_say "Microsoft 365 event create plan:"
    _m365_say "Account: $alias"
    _m365_say "Calendar: $calendar_id"
    _m365_say "Title: $title"
    _m365_say "Start: $start"
    _m365_say "End: ${end:-<default>}"
    [ -n "$tz" ] && _m365_say "Time zone: $tz"
    _m365_say "Location: ${location:-<none>}"
    if [ "${#_RESOLVED_DISPLAY[@]}" -gt 0 ]; then _m365_say "Attendees: ${_RESOLVED_DISPLAY[*]}"; else _m365_say "Attendees: <none>"; fi
    _m365_say "Microsoft invitation/update email acknowledged: $([ "$notify" -eq 1 ] && echo yes || echo no)"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no event was created. Re-run with --execute to create it."; return 0; fi
    created="$(_m365_write POST "$alias" "$(_m365_calendar_event_url "$alias" "$calendar_id")" "$body")" || return 1
    _m365_say "Created event: $(printf '%s' "$created" | jq -r '.webLink // .id // "(unknown)"')"
}

_m365_calendar_update() {
    local alias="${1:-}" calendar_id="primary" event_id="" title="" start="" end="" tz="" location="" desc="" desc_file=""
    local set_title=0 set_location=0 set_desc=0 notify=0 execute=0 replace_attendees=0 body current updated attendee_count
    local attendees_raw=() final_emails=() build_args=()
    [ -n "$alias" ] || { _m365_error "m365 calendar update-event requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --calendar) [ -n "${2:-}" ] || { _m365_error "--calendar requires ID"; return 1; }; calendar_id="$2"; shift 2 ;;
            --event) [ -n "${2:-}" ] || { _m365_error "--event requires ID"; return 1; }; event_id="$2"; shift 2 ;;
            --title) [ -n "${2+x}" ] || { _m365_error "--title requires TEXT"; return 1; }; title="$2"; set_title=1; shift 2 ;;
            --start) [ -n "${2:-}" ] || { _m365_error "--start requires DATE or DATETIME"; return 1; }; start="$2"; shift 2 ;;
            --end) [ -n "${2:-}" ] || { _m365_error "--end requires DATE or DATETIME"; return 1; }; end="$2"; shift 2 ;;
            --tz) [ -n "${2:-}" ] || { _m365_error "--tz requires ZONE"; return 1; }; tz="$2"; shift 2 ;;
            --location) [ -n "${2+x}" ] || { _m365_error "--location requires TEXT"; return 1; }; location="$2"; set_location=1; shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _m365_error "--desc requires TEXT"; return 1; }; desc="$2"; set_desc=1; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _m365_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; set_desc=1; shift 2 ;;
            --attendee) [ -n "${2:-}" ] || { _m365_error "--attendee requires NAME or EMAIL"; return 1; }; attendees_raw+=("$2"); shift 2 ;;
            --replace-attendees) replace_attendees=1; shift ;;
            --notify) notify=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 calendar update-event option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" calendar || return 1
    [ -n "$event_id" ] || { _m365_error "update-event requires --event"; return 1; }
    _m365_calendar_is_writable "$alias" "$calendar_id" || { _m365_error "Calendar '$calendar_id' is not writable for alias '$alias'"; return 1; }
    if [ -n "$desc_file" ]; then [ -f "$desc_file" ] || { _m365_error "Description file does not exist: $desc_file"; return 1; }; desc="$(cat "$desc_file")"; fi
    current="$(_m365_get "$alias" "$(_m365_calendar_event_url "$alias" "$calendar_id" "$event_id")" -H 'Prefer: outlook.body-content-type="text"')" || return 1
    attendee_count="$(printf '%s' "$current" | jq '(.attendees // []) | length')"
    if { [ "$attendee_count" -gt 0 ] || [ "${#attendees_raw[@]}" -gt 0 ]; } && [ "$notify" -ne 1 ]; then
        _m365_error "This meeting has or will have attendees, and Microsoft may send an update. Re-run with --notify to acknowledge that blast radius."
        return 1
    fi
    if [ "$set_desc" -eq 1 ] && printf '%s' "$current" | jq -e '.isOnlineMeeting == true' >/dev/null 2>&1; then
        _m365_error "Description updates are blocked for online meetings because replacing the body can remove the Teams meeting blob."
        return 1
    fi
    if [ -n "$start" ]; then [ -n "$tz" ] || tz="$(_m365_calendar_timezone "$alias")"; fi
    if [ "${#attendees_raw[@]}" -gt 0 ] || [ "$replace_attendees" -eq 1 ]; then
        if [ "${#attendees_raw[@]}" -gt 0 ]; then _m365_resolve_attendees "${attendees_raw[@]}" || return 1; else _RESOLVED_EMAILS=(); fi
        if [ "$replace_attendees" -ne 1 ]; then
            local existing
            while IFS= read -r existing || [ -n "$existing" ]; do [ -n "$existing" ] && final_emails+=("$existing"); done <<EOF
$(printf '%s' "$current" | jq -r '(.attendees // [])[] | .emailAddress.address // empty')
EOF
        fi
        final_emails+=(${_RESOLVED_EMAILS[@]+"${_RESOLVED_EMAILS[@]}"})
    fi
    build_args=(event)
    [ "$set_title" -eq 1 ] && build_args+=(--title "$title")
    [ -n "$start" ] && build_args+=(--start "$start")
    [ -n "$end" ] && build_args+=(--end "$end")
    [ -n "$tz" ] && build_args+=(--tz "$tz")
    [ "$set_location" -eq 1 ] && build_args+=(--location "$location")
    [ "$set_desc" -eq 1 ] && build_args+=(--description "$desc")
    local email
    for email in ${final_emails[@]+"${final_emails[@]}"}; do build_args+=(--attendee "$email"); done
    if [ "$replace_attendees" -eq 1 ] && [ "${#final_emails[@]}" -eq 0 ]; then build_args+=(--clear-attendees); fi
    body="$(_m365_calendar_write_helper "${build_args[@]}")" || return 1
    if printf '%s' "$body" | jq -e '.attendees' >/dev/null 2>&1; then body="$(printf '%s' "$body" | jq -c '.attendees |= unique_by(.emailAddress.address | ascii_downcase)')"; fi
    _m365_say "Microsoft 365 event update plan:"
    _m365_say "Account: $alias"
    _m365_say "Calendar: $calendar_id"
    _m365_say "Event: $event_id"
    _m365_say "Current title: $(printf '%s' "$current" | jq -r '.subject // "(none)"')"
    _m365_say "Changes:"
    printf '%s' "$body" | jq .
    _m365_say "Microsoft invitation/update email acknowledged: $([ "$notify" -eq 1 ] && echo yes || echo no)"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no event was updated. Re-run with --execute to apply."; return 0; fi
    updated="$(_m365_write PATCH "$alias" "$(_m365_calendar_event_url "$alias" "$calendar_id" "$event_id")" "$body")" || return 1
    _m365_say "Updated event: $(printf '%s' "$updated" | jq -r '.webLink // .id // "(unknown)"')"
}

_m365_calendar_export() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" out="" window from to ids email refreshed zone limit
    [ -n "$alias" ] || { _m365_error 'calendar export requires ALIAS --output PATH'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in --output) [ -n "${2:-}" ] || return 1; out="$2"; shift 2 ;; *) _m365_error "Unknown calendar export option: $1"; return 1 ;; esac
    done
    [ -n "$out" ] && [ -d "$(dirname "$out")" ] && [ ! -L "$out" ] || { _m365_error 'Choose an output file in an existing directory, not a symlink'; return 1; }
    _m365_require_enabled "$alias" calendar || return 1
    window="$(_m365_calendar_window "$alias")" || return 1
    from="$(printf '%s\n' "$window" | sed -n '1p')"; to="$(printf '%s\n' "$window" | sed -n '2p')"
    ids="$(_m365_calendar_ids "$alias")" || return 1
    _m365_calendar_fetch "$alias" "$from" "$to" "$ids" "$M365_WORK/events.json" || return 1
    email="$(_m365_profile_email "$alias")" || return 1
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    zone="$(_m365_calendar_timezone "$alias")" || return 1
    limit="$(_m365_account_value "$alias" '.calendar.description_character_limit // 8000')" || return 1
    case "$limit" in ''|*[!0-9]*) _m365_error 'description_character_limit must be nonnegative'; return 1 ;; esac
    _m365_calendar_render_helper calendar --alias "$alias" --email "$email" --refreshed "$refreshed" --start "$from" --end "$to" --timezone "$zone" --description-limit "$limit" --input "$M365_WORK/events.json" > "$M365_WORK/export.md" || return 1
    _m365_python "$OUTLOOK_CALENDAR_DIR" "$M365_AUTH_DIR/scripts/publish.py" "$M365_WORK/export.md" "$out" replace || return 1
    _m365_say "Updated $out"
)
