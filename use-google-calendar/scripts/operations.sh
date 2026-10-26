#!/usr/bin/env bash
##- Google-only calendar operations; shared authorization is the only skill dependency.
GOOGLE_CALENDAR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_calendar_urlencode() { jq -rn --arg value "$1" '$value | @uri'; }
_calendar_work_begin() {
    CALENDAR_WORK="$(mktemp -d "${TMPDIR:-/tmp}/google-calendar.XXXXXX")" || return 1
    trap 'rm -rf "$CALENDAR_WORK"' EXIT
    trap 'exit 130' HUP INT TERM
}
_calendar_token_ready() {
    _google_account_exists "$GOOGLE_CALENDAR_ALIAS" || return 1
    _google_account_value "$GOOGLE_CALENDAR_ALIAS" '.calendar.enabled == true' | grep -qx true || { _google_error 'Calendar is not enabled for this account'; return 1; }
}
_calendar_ids() { _google_account_value "$GOOGLE_CALENDAR_ALIAS" '(.calendar.read_ids // ["primary"]) | join(",")'; }
_calendar_writable_ids() { _google_account_value "$GOOGLE_CALENDAR_ALIAS" '(.calendar.writable_ids // []) | join(",")'; }
_calendar_max_pages() { _google_account_value "$GOOGLE_CALENDAR_ALIAS" '.calendar.max_pages // 40'; }
_calendar_get() {
    local endpoint="$1"; shift
    _google_get_url "$GOOGLE_CALENDAR_ALIAS" "https://www.googleapis.com/calendar/v3${endpoint}" "$@"
}
_calendar_write() {
    local method="$1" endpoint="$2" body="$3" token; shift 3
    _google_account_value "$GOOGLE_CALENDAR_ALIAS" '.calendar.write_enabled == true' | grep -qx true || { _google_error 'Calendar writes are disabled for this account'; return 1; }
    token="$(_google_access_token "$GOOGLE_CALENDAR_ALIAS")" || return 1
    curl -fsS -X "$method" "https://www.googleapis.com/calendar/v3${endpoint}" -H "Authorization: Bearer ${token}" -H 'Content-Type: application/json; charset=utf-8' --data-binary "$body" "$@"
}
_calendar_write_helper() { _google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_CALENDAR_DIR/scripts/write.py" "$@"; }
_calendar_render_helper() {
    local omitted
    omitted="$(_google_account_value "$GOOGLE_CALENDAR_ALIAS" '(.calendar.no_description // []) | join(",")')" || return 1
    GOOGLE_CALENDAR_NO_DESCRIPTION="$omitted" _google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_CALENDAR_DIR/scripts/render.py" "$@"
}
_calendar_window() {
    _google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_CALENDAR_DIR/scripts/window.py" "$(_google_account_value "$GOOGLE_CALENDAR_ALIAS" '.calendar.days_back // 14')" "$(_google_account_value "$GOOGLE_CALENDAR_ALIAS" '.calendar.days_ahead // 30')"
}
_calendar_resolve_attendees() {
    local email
    _RESOLVED_EMAILS=(); _RESOLVED_DISPLAY=()
    for email in "$@"; do
        case "$email" in *[[:space:]]*|*@*@*|@*|*@|*[![:print:]]*) _google_error 'Attendees must be explicit email addresses'; return 1 ;; *@*) ;; *) _google_error 'Resolve attendee names separately, then pass an explicit email'; return 1 ;; esac
        _RESOLVED_EMAILS+=("$email"); _RESOLVED_DISPLAY+=("$email")
    done
}

_calendar_is_writable() {
    local target="$1" id
    for id in $(printf '%s' "$(_calendar_writable_ids)" | tr ',' ' '); do
        id="$(_google_trim "$id")"
        [ -n "$id" ] || continue
        [ "$id" = "$target" ] && return 0
    done
    return 1
}

_calendar_system_tz() {
    local target
    if [ -f /etc/timezone ]; then
        _google_trim "$(cat /etc/timezone)"
        return 0
    fi
    if [ -L /etc/localtime ]; then
        target="$(readlink /etc/localtime)"
        # Strip everything up to and including the zoneinfo dir, leaving e.g. America/Chicago.
        case "$target" in
            */zoneinfo/*) printf '%s' "${target##*/zoneinfo/}"; return 0 ;;
        esac
    fi
    if [ -n "${TZ:-}" ]; then
        printf '%s' "$TZ"
        return 0
    fi
    return 1
}

_calendar_default_tz() {
    local calendar_id="$1" encoded tz hint
    encoded="$(_calendar_urlencode "$calendar_id")" || return 1
    tz="$(_calendar_get "/users/me/calendarList/${encoded}" --data-urlencode "fields=timeZone" 2>/dev/null | jq -r '.timeZone // empty')"
    if [ -n "$tz" ]; then
        printf '%s' "$tz"
        return 0
    fi
    hint="$(_calendar_system_tz 2>/dev/null)" || hint=""
    _google_error "could not read the time zone for calendar '${calendar_id}'."
    _google_error "Refusing to guess: a wrong zone writes the event at the wrong hour and looks normal afterward."
    if [ -n "$hint" ]; then
        _google_error "Re-run with an explicit zone, e.g. --tz ${hint} (this machine's zone), or whichever zone the event belongs in."
    else
        _google_error "Re-run with an explicit zone, e.g. --tz America/Chicago (an IANA name, never an abbreviation like CDT)."
    fi
    _google_error "If this keeps happening, the calendar metadata read may be failing: check 'calendar list-calendars ALIAS' and the token scope."
    return 1
}

_calendar_list_calendars() (
    set -o pipefail
    _calendar_work_begin || return 1
    _calendar_token_ready || return 1
    _calendar_list_fetch "$CALENDAR_WORK/list.json" || return 1
    jq -r '(.items // [])[] | "- " + (.summary // "Untitled calendar") + " | id: " + (.id // "") + " | primary: " + ((.primary // false) | tostring) + " | selected: " + ((.selected // false) | tostring) + " | access: " + (.accessRole // "unknown")' "$CALENDAR_WORK/list.json"
)

_calendar_find_human() {
    jq -r '
      (.items // [])[] |
      [
        ("- " + (.summary // "Untitled event")),
        ("calendar: " + (._calendar_summary // ._calendar_id // "")),
        ("calendar_id: " + (._calendar_id // "")),
        ("event_id: " + (.id // "")),
        (if .recurringEventId then "series_id: " + .recurringEventId else empty end),
        ("start: " + (.start.dateTime // .start.date // "")),
        ("end: " + (.end.dateTime // .end.date // "")),
        (if (.location // "") != "" then "location: " + .location else empty end),
        (if (.htmlLink // "") != "" then .htmlLink else empty end)
      ] | join(" | ")
    '
}

_calendar_find() (
    set -o pipefail
    _calendar_work_begin || return 1
    local query="" calendar_ids="" calendar_id encoded_id calendar_file calendar_list_file events_file combined_file
    local window time_min time_max from="" to="" json=0 calendar_name

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --calendar)
                [ -n "${2:-}" ] || { _google_error "--calendar requires CALENDAR_ID"; return 1; }
                calendar_ids="$2"
                shift 2
                ;;
            --from)
                [ -n "${2:-}" ] || { _google_error "--from requires YYYY-MM-DD"; return 1; }
                from="$2"
                shift 2
                ;;
            --to)
                [ -n "${2:-}" ] || { _google_error "--to requires YYYY-MM-DD"; return 1; }
                to="$2"
                shift 2
                ;;
            --json)
                json=1
                shift
                ;;
            -*)
                _google_error "Unknown calendar find option: $1"
                return 1
                ;;
            *)
                if [ -z "$query" ]; then
                    query="$1"
                    shift
                else
                    _google_error "Unexpected calendar find argument: $1"
                    return 1
                fi
                ;;
        esac
    done

    [ -n "$query" ] || { _google_error "calendar find requires QUERY"; return 1; }
    _calendar_token_ready || return 1

    if [ -n "$from" ]; then
        time_min="${from}T00:00:00Z"
    else
        window="$(_calendar_window)" || return 1
        time_min="$(printf '%s\n' "$window" | sed -n '1p')"
    fi
    if [ -n "$to" ]; then
        time_max="${to}T23:59:59Z"
    else
        if [ -z "${window:-}" ]; then
            window="$(_calendar_window)" || return 1
        fi
        time_max="$(printf '%s\n' "$window" | sed -n '2p')"
    fi
    if [ -z "$calendar_ids" ]; then
        calendar_ids="$(printf '%s' "$(_calendar_ids)" | tr ',' ' ')"
    fi

    calendar_list_file="$(mktemp "$CALENDAR_WORK/calendar-find-list.XXXXXX")" || return 1
    combined_file="$(mktemp "$CALENDAR_WORK/calendar-find.XXXXXX")" || return 1
    jq -n '{items: []}' > "$combined_file"

    _calendar_list_fetch "$calendar_list_file" || return 1

    for calendar_id in $calendar_ids; do
        calendar_id="$(_google_trim "$calendar_id")"
        [ -n "$calendar_id" ] || continue
        encoded_id="$(_calendar_urlencode "$calendar_id")" || return 1
        calendar_file="$(mktemp "$CALENDAR_WORK/calendar-find-meta.XXXXXX")" || return 1
        events_file="$(mktemp "$CALENDAR_WORK/calendar-find-events.XXXXXX")" || return 1
        _calendar_write_metadata "$calendar_list_file" "$calendar_id" "$calendar_file"
        calendar_name="$(jq -r '.summary // .id // "Calendar"' "$calendar_file")"
        _google_say "Finding events in calendar: ${calendar_name}" >&2

        _calendar_get "/calendars/${encoded_id}/events" \
            --data-urlencode "singleEvents=true" \
            --data-urlencode "orderBy=startTime" \
            --data-urlencode "showDeleted=false" \
            --data-urlencode "timeMin=${time_min}" \
            --data-urlencode "timeMax=${time_max}" \
            --data-urlencode "q=${query}" \
            --data-urlencode "maxResults=50" \
            --data-urlencode "fields=items(id,recurringEventId,status,summary,description,location,htmlLink,start,end),nextPageToken" > "$events_file" || return 1

        jq -e 'type == "object" and .error == null and ((.items // []) | type == "array")' "$events_file" >/dev/null || return 1
        if jq -e '.nextPageToken != null' "$events_file" >/dev/null; then printf 'WARN: More matching events exist beyond the 50-event bound for this calendar
' >&2; fi

        jq -s --slurpfile meta "$calendar_file" '
          .[0] as $existing |
          .[1] as $incoming |
          $existing + {
            items: (
              ($existing.items // []) +
              (($incoming.items // []) | map(. + {
                _calendar_id: ($meta[0].id // ""),
                _calendar_summary: ($meta[0].summary // "")
              }))
            )
          }
        ' "$combined_file" "$events_file" > "${combined_file}.next" || return 1
        mv "${combined_file}.next" "$combined_file"
    done

    if [ "$json" -eq 1 ]; then
        cat "$combined_file"
    else
        if [ "$(jq '(.items // []) | length' "$combined_file")" -eq 0 ]; then
            _google_say "No matching events found."
            return 0
        fi
        _calendar_find_human < "$combined_file"
    fi
)

_calendar_render_events() {
    _calendar_render_helper "$@"
}

_calendar_write_metadata() {
    local calendar_list_file="$1"
    local requested_id="$2"
    local out="$3"

    if ! jq -e --arg id "$requested_id" '
      if $id == "primary" then
        ((.items // []) | map(select(.primary == true)) | .[0])
      else
        ((.items // []) | map(select(.id == $id)) | .[0])
      end |
      select(. != null) |
      {
        id: (if $id == "primary" then "primary" else .id end),
        actualId: (.id // ""),
        summary: (.summary // $id),
        timeZone: (.timeZone // ""),
        primary: (.primary // false),
        selected: (.selected // false),
        accessRole: (.accessRole // "")
      }
    ' "$calendar_list_file" > "$out"; then
        jq -n --arg id "$requested_id" '{id: $id, actualId: $id, summary: $id}' > "$out"
    fi
}

_calendar_fetch_events() (
    set -o pipefail
    _calendar_work_begin || return 1
    local encoded_id="$1" from="$2" to="$3" out="$4" fields="$5" page_token="" page=0 dir page_file
    local max_pages="$(_calendar_max_pages)"
    case "$max_pages" in ''|*[!0-9]*) _google_error 'calendar.max_pages must be a positive integer'; return 1 ;; esac
    [ "$max_pages" -gt 0 ] || return 1
    dir="$(mktemp -d "$CALENDAR_WORK/events-pages.XXXXXX")" || return 1
    while :; do
        page=$((page + 1))
        if [ "$page" -gt "$max_pages" ]; then
            _google_error "Calendar fetch exceeded ${max_pages} pages for one calendar; refusing to write a truncated agenda. Narrow the window or raise calendar.max_pages."
            return 1
        fi
        page_file="${dir}/page-${page}.json"
        if [ -n "$page_token" ]; then
            _calendar_get "/calendars/${encoded_id}/events" \
                --data-urlencode "singleEvents=true" --data-urlencode "orderBy=startTime" --data-urlencode "showDeleted=false" \
                --data-urlencode "timeMin=${from}" --data-urlencode "timeMax=${to}" --data-urlencode "maxResults=2500" \
                --data-urlencode "fields=${fields}" --data-urlencode "pageToken=${page_token}" > "$page_file" || return 1
        else
            _calendar_get "/calendars/${encoded_id}/events" \
                --data-urlencode "singleEvents=true" --data-urlencode "orderBy=startTime" --data-urlencode "showDeleted=false" \
                --data-urlencode "timeMin=${from}" --data-urlencode "timeMax=${to}" --data-urlencode "maxResults=2500" \
                --data-urlencode "fields=${fields}" > "$page_file" || return 1
        fi
        jq -e 'type == "object" and .error == null and ((.items // []) | type == "array")' "$page_file" >/dev/null || { _google_error 'Invalid calendar events response'; return 1; }
        page_token="$(jq -r '.nextPageToken // empty' "$page_file")"
        [ -n "$page_token" ] || break
    done
    jq -s '{items: (map(.items // []) | add)}' "$dir"/page-*.json > "$out"
)

_calendar_verify_event_settings() {
    local calendar_encoded="$1" event_id="$2" expected="$3" event_encoded readback
    event_encoded="$(_calendar_urlencode "$event_id")" || return 1
    readback="$(_calendar_get "/calendars/${calendar_encoded}/events/${event_encoded}")" || return 1
    printf '%s' "$readback" | jq -e --arg id "$event_id" '.id == $id' >/dev/null || { _google_error "Settings readback returned a different or missing event ID"; return 1; }
    jq -n --argjson expected "$expected" --argjson event "$readback" '{expected: $expected, event: $event}' | _calendar_write_helper verify-settings
}

_calendar_create_event() {
    local calendar_id="primary" title="" start="" end="" tz="" location="" desc="" desc_file=""
    local notify=0 execute=0 encoded body send_updates created created_id
    local transparency="" popup_minutes=""
    local attendees_raw=() build_args=() recurrence_rules=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --title) [ -n "${2:-}" ] || { _google_error "--title requires TEXT"; return 1; }; title="$2"; shift 2 ;;
            --calendar) [ -n "${2:-}" ] || { _google_error "--calendar requires CALENDAR_ID"; return 1; }; calendar_id="$2"; shift 2 ;;
            --start) [ -n "${2:-}" ] || { _google_error "--start requires DATE or DATETIME"; return 1; }; start="$2"; shift 2 ;;
            --end) [ -n "${2:-}" ] || { _google_error "--end requires DATE or DATETIME"; return 1; }; end="$2"; shift 2 ;;
            --tz) [ -n "${2:-}" ] || { _google_error "--tz requires ZONE"; return 1; }; tz="$2"; shift 2 ;;
            --location) [ -n "${2+x}" ] || { _google_error "--location requires TEXT"; return 1; }; location="$2"; shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _google_error "--desc requires TEXT"; return 1; }; desc="$2"; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _google_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; shift 2 ;;
            --attendee) [ -n "${2:-}" ] || { _google_error "--attendee requires NAME or EMAIL"; return 1; }; attendees_raw+=("$2"); shift 2 ;;
            --recurrence) [ -n "${2:-}" ] || { _google_error "--recurrence requires an RRULE line"; return 1; }; recurrence_rules+=("$2"); shift 2 ;;
            --transparency) [ -n "${2:-}" ] || { _google_error "--transparency requires transparent (Free) or opaque (Busy)"; return 1; }; transparency="$2"; shift 2 ;;
            --popup-minutes) [ -n "${2:-}" ] || { _google_error "--popup-minutes requires 0..40320"; return 1; }; popup_minutes="$2"; shift 2 ;;
            --notify) notify=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _google_error "Unknown calendar create-event option: $1"; return 1 ;;
        esac
    done

    _calendar_token_ready || return 1
    [ -n "$title" ] || { _google_error "create-event requires --title"; return 1; }
    [ -n "$start" ] || { _google_error "create-event requires --start"; return 1; }
    if ! _calendar_is_writable "$calendar_id"; then
        _google_error "Calendar '$calendar_id' is not writable. Allowed: $(_calendar_writable_ids)"
        _google_say "NEXT: add it to calendar.writable_ids in the selected account config if you intend to write there."
        return 1
    fi
    if [ -n "$desc_file" ]; then
        [ -f "$desc_file" ] || { _google_error "Description file does not exist: $desc_file"; return 1; }
        desc="$(cat "$desc_file")"
    fi

    # Timed events (start contains a time component) need a time zone.
    case "$start" in
        *T*) [ -n "$tz" ] || tz="$(_calendar_default_tz "$calendar_id")" || return 1 ;;
    esac

    if [ "${#attendees_raw[@]}" -gt 0 ]; then
        _calendar_resolve_attendees ${attendees_raw[@]+"${attendees_raw[@]}"} || return 1
    else
        _RESOLVED_EMAILS=()
        _RESOLVED_DISPLAY=()
    fi

    build_args=(build-event --title "$title" --start "$start")
    [ -n "$end" ] && build_args+=(--end "$end")
    [ -n "$tz" ] && build_args+=(--tz "$tz")
    [ -n "$location" ] && build_args+=(--location "$location")
    [ -n "$desc" ] && build_args+=(--description "$desc")
    [ -n "$transparency" ] && build_args+=(--transparency "$transparency")
    [ -n "$popup_minutes" ] && build_args+=(--popup-minutes "$popup_minutes")
    local email rule
    for email in ${_RESOLVED_EMAILS[@]+"${_RESOLVED_EMAILS[@]}"}; do
        build_args+=(--attendee "$email")
    done
    for rule in ${recurrence_rules[@]+"${recurrence_rules[@]}"}; do
        build_args+=(--recurrence "$rule")
    done

    body="$(_calendar_write_helper "${build_args[@]}")" || return 1

    if [ "$notify" -eq 1 ]; then send_updates="all"; else send_updates="none"; fi

    _google_say "Calendar event create plan:"
    _google_say "Calendar: $calendar_id"
    _google_say "Title: $title"
    _google_say "Start: $start"
    _google_say "End: ${end:-<default>}"
    [ -n "$tz" ] && _google_say "Time zone: $tz"
    _google_say "Location: ${location:-<none>}"
    _google_say "Transparency: ${transparency:-<default: opaque/Busy>}"
    if [ -n "$popup_minutes" ]; then
        _google_say "Popup reminder: $popup_minutes minutes before start (replaces event reminders)"
    else
        _google_say "Popup reminder: <calendar defaults>"
    fi
    if [ "${#recurrence_rules[@]}" -gt 0 ]; then
        _google_say "Recurrence: ${recurrence_rules[*]}"
    fi
    if [ "${#_RESOLVED_DISPLAY[@]}" -gt 0 ]; then
        _google_say "Attendees: ${_RESOLVED_DISPLAY[*]}"
    else
        _google_say "Attendees: <none>"
    fi
    _google_say "Notify attendees: $([ "$notify" -eq 1 ] && echo "YES (email invites)" || echo "no")"

    if [ "$execute" -ne 1 ]; then
        _google_say "DRY RUN: no event was created. Re-run with --execute to create it."
        return 0
    fi

    encoded="$(_calendar_urlencode "$calendar_id")" || return 1
    created="$(_calendar_write POST "/calendars/${encoded}/events?sendUpdates=${send_updates}" "$body")" || return 1
    created_id="$(printf '%s' "$created" | jq -r '.id // empty')"
    [ -n "$created_id" ] || { _google_error 'PARTIAL: create response did not identify an event; inspect the calendar before retrying'; return 1; }
    _google_say "Created event: $(printf '%s' "$created" | jq -r '.htmlLink // .id // "(unknown)"')"
    if [ -n "$transparency" ] || [ -n "$popup_minutes" ]; then
        if [ -z "$created_id" ] || ! _calendar_verify_event_settings "$encoded" "$created_id" "$body"; then
            _google_error "PARTIAL: create accepted but requested settings were not verified (calendar $calendar_id, event ${created_id:-unknown}). Inspect the event before retrying; do not create it again automatically."
            return 1
        fi
    fi
}

_calendar_update_event() {
    local calendar_id="primary" event_id="" title="" start="" end="" tz="" location="" desc="" desc_file=""
    local transparency="" popup_minutes=""
    local notify=0 execute=0 replace_attendees=0 set_title=0 set_location=0 set_desc=0 scope_series=0
    local encoded event_encoded target_id target_encoded body send_updates current scope_label updated
    local attendees_raw=() build_args=() final_emails=() recurrence_rules=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --event) [ -n "${2:-}" ] || { _google_error "--event requires EVENT_ID"; return 1; }; event_id="$2"; shift 2 ;;
            --calendar) [ -n "${2:-}" ] || { _google_error "--calendar requires CALENDAR_ID"; return 1; }; calendar_id="$2"; shift 2 ;;
            --title) [ -n "${2:-}" ] || { _google_error "--title requires TEXT"; return 1; }; title="$2"; set_title=1; shift 2 ;;
            --start) [ -n "${2:-}" ] || { _google_error "--start requires DATE or DATETIME"; return 1; }; start="$2"; shift 2 ;;
            --end) [ -n "${2:-}" ] || { _google_error "--end requires DATE or DATETIME"; return 1; }; end="$2"; shift 2 ;;
            --tz) [ -n "${2:-}" ] || { _google_error "--tz requires ZONE"; return 1; }; tz="$2"; shift 2 ;;
            --location) [ -n "${2+x}" ] || { _google_error "--location requires TEXT"; return 1; }; location="$2"; set_location=1; shift 2 ;;
            --desc) [ -n "${2+x}" ] || { _google_error "--desc requires TEXT"; return 1; }; desc="$2"; set_desc=1; shift 2 ;;
            --desc-file) [ -n "${2:-}" ] || { _google_error "--desc-file requires FILE"; return 1; }; desc_file="$2"; set_desc=1; shift 2 ;;
            --attendee) [ -n "${2:-}" ] || { _google_error "--attendee requires NAME or EMAIL"; return 1; }; attendees_raw+=("$2"); shift 2 ;;
            --recurrence) [ -n "${2:-}" ] || { _google_error "--recurrence requires an RRULE line"; return 1; }; recurrence_rules+=("$2"); shift 2 ;;
            --replace-attendees) replace_attendees=1; shift ;;
            --series) scope_series=1; shift ;;
            --instance) scope_series=0; shift ;;
            --transparency) [ -n "${2:-}" ] || { _google_error "--transparency requires transparent (Free) or opaque (Busy)"; return 1; }; transparency="$2"; shift 2 ;;
            --popup-minutes) [ -n "${2:-}" ] || { _google_error "--popup-minutes requires 0..40320"; return 1; }; popup_minutes="$2"; shift 2 ;;
            --notify) notify=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _google_error "Unknown calendar update-event option: $1"; return 1 ;;
        esac
    done

    _calendar_token_ready || return 1
    [ -n "$event_id" ] || { _google_error "update-event requires --event"; return 1; }
    if ! _calendar_is_writable "$calendar_id"; then
        _google_error "Calendar '$calendar_id' is not writable. Allowed: $(_calendar_writable_ids)"
        return 1
    fi
    if [ "${#recurrence_rules[@]}" -gt 0 ] && [ "$scope_series" -ne 1 ]; then
        _google_error "--recurrence changes the recurrence rule, which only applies to the series. Re-run with --series."
        return 1
    fi
    if [ -n "$desc_file" ]; then
        [ -f "$desc_file" ] || { _google_error "Description file does not exist: $desc_file"; return 1; }
        desc="$(cat "$desc_file")"
    fi

    encoded="$(_calendar_urlencode "$calendar_id")" || return 1
    event_encoded="$(_calendar_urlencode "$event_id")" || return 1
    current="$(_calendar_get "/calendars/${encoded}/events/${event_encoded}")" || {
        _google_error "Could not fetch event '$event_id' on calendar '$calendar_id'."
        return 1
    }

    # Default target is the event ID as passed (a single instance for recurring events). --series retargets the parent series master so the edit applies to every occurrence; re-fetch it so the plan and attendee merge use its state.
    if [ "$scope_series" -eq 1 ]; then
        target_id="$(printf '%s' "$current" | jq -r '.recurringEventId // .id')"
        target_encoded="$(_calendar_urlencode "$target_id")" || return 1
        if [ "$target_id" != "$event_id" ]; then
            current="$(_calendar_get "/calendars/${encoded}/events/${target_encoded}")" || {
                _google_error "Could not fetch series master '$target_id'."
                return 1
            }
        fi
        scope_label="entire series ($target_id)"
    else
        target_id="$event_id"
        target_encoded="$event_encoded"
        if printf '%s' "$current" | jq -e '.recurringEventId' >/dev/null 2>&1; then
            scope_label="single occurrence (pass --series to edit all)"
        else
            scope_label="single event"
        fi
    fi

    case "$start" in
        *T*) [ -n "$tz" ] || tz="$(_calendar_default_tz "$calendar_id")" || return 1 ;;
    esac

    # Attendee handling: PATCH replaces the whole attendees array, so to ADD we merge the existing list with the new one unless --replace-attendees is set.
    if [ "${#attendees_raw[@]}" -gt 0 ] || [ "$replace_attendees" -eq 1 ]; then
        if [ "${#attendees_raw[@]}" -gt 0 ]; then
            _calendar_resolve_attendees ${attendees_raw[@]+"${attendees_raw[@]}"} || return 1
        else
            _RESOLVED_EMAILS=()
            _RESOLVED_DISPLAY=()
        fi
        if [ "$replace_attendees" -eq 1 ]; then
            final_emails=(${_RESOLVED_EMAILS[@]+"${_RESOLVED_EMAILS[@]}"})
        else
            local existing
            while IFS= read -r existing || [ -n "$existing" ]; do
                [ -n "$existing" ] || continue
                final_emails+=("$existing")
            done <<EOF
$(printf '%s' "$current" | jq -r '(.attendees // [])[] | .email // empty')
EOF
            final_emails+=(${_RESOLVED_EMAILS[@]+"${_RESOLVED_EMAILS[@]}"})
        fi
    fi

    build_args=(build-event)
    [ "$set_title" -eq 1 ] && build_args+=(--title "$title")
    [ -n "$start" ] && build_args+=(--start "$start")
    [ -n "$end" ] && build_args+=(--end "$end")
    [ -n "$tz" ] && build_args+=(--tz "$tz")
    [ "$set_location" -eq 1 ] && build_args+=(--location "$location")
    [ "$set_desc" -eq 1 ] && build_args+=(--description "$desc")
    [ -n "$transparency" ] && build_args+=(--transparency "$transparency")
    [ -n "$popup_minutes" ] && build_args+=(--popup-minutes "$popup_minutes")
    local email rule
    for email in ${final_emails[@]+"${final_emails[@]}"}; do
        build_args+=(--attendee "$email")
    done
    for rule in ${recurrence_rules[@]+"${recurrence_rules[@]}"}; do
        build_args+=(--recurrence "$rule")
    done

    if [ "$replace_attendees" -eq 1 ] && [ "${#final_emails[@]}" -eq 0 ]; then
        if [ "${#build_args[@]}" -gt 1 ]; then body="$(_calendar_write_helper "${build_args[@]}")" || return 1
        else body='{}'
        fi
        body="$(printf '%s' "$body" | jq '.attendees = []')" || return 1
    else
        body="$(_calendar_write_helper "${build_args[@]}")" || return 1
    fi

    if [ "$notify" -eq 1 ]; then send_updates="all"; else send_updates="none"; fi

    _google_say "Calendar event update plan:"
    _google_say "Calendar: $calendar_id"
    _google_say "Event: $event_id"
    _google_say "Scope: $scope_label"
    _google_say "Current title: $(printf '%s' "$current" | jq -r '.summary // "(none)"')"
    _google_say "Changes:"
    printf '%s' "$body" | jq .
    if [ "${#final_emails[@]}" -gt 0 ]; then
        _google_say "Final attendees: ${final_emails[*]}"
    fi
    _google_say "Notify attendees: $([ "$notify" -eq 1 ] && echo "YES (email invites)" || echo "no")"

    if [ "$execute" -ne 1 ]; then
        _google_say "DRY RUN: no event was updated. Re-run with --execute to apply."
        return 0
    fi

    updated="$(_calendar_write PATCH "/calendars/${encoded}/events/${target_encoded}?sendUpdates=${send_updates}" "$body")" || return 1
    _google_say "Updated event: $(printf '%s' "$updated" | jq -r '.htmlLink // .id // "(unknown)"')"
    if [ -n "$transparency" ] || [ -n "$popup_minutes" ]; then
        if ! _calendar_verify_event_settings "$encoded" "$target_id" "$body"; then
            _google_error "PARTIAL: update accepted but requested settings were not verified (calendar $calendar_id, event $target_id). Inspect the event before retrying; do not repeat the write automatically."
            return 1
        fi
    fi
}

_calendar_list_fetch() (
    set -o pipefail
    _calendar_work_begin || return 1
    local out="$1" token="" page=0 cap args=()
    cap="$(_calendar_max_pages)" || return 1
    case "$cap" in ''|*[!0-9]*) _google_error 'calendar.max_pages must be a positive integer'; return 1 ;; esac
    while :; do
        page=$((page + 1))
        [ "$page" -le "$cap" ] || { _google_error 'Calendar list exceeded page cap'; return 1; }
        args=(--data-urlencode 'fields=items(id,summary,primary,selected,hidden,accessRole,timeZone),nextPageToken')
        [ -z "$token" ] || args+=(--data-urlencode "pageToken=$token")
        _calendar_get /users/me/calendarList "${args[@]}" > "$CALENDAR_WORK/page-$page.json" || return 1
        jq -e 'type == "object" and .error == null and ((.items // []) | type == "array")' "$CALENDAR_WORK/page-$page.json" >/dev/null || { _google_error 'Invalid calendar list response'; return 1; }
        token="$(jq -r '.nextPageToken // empty' "$CALENDAR_WORK/page-$page.json")" || return 1
        [ -n "$token" ] || break
    done
    jq -s '{items: (map(.items // []) | add)}' "$CALENDAR_WORK"/page-*.json > "$out"
)

_calendar_export() (
    set -o pipefail
    _calendar_work_begin || return 1
    local data=0 out="" from="" to="" ids="" compact=0 tz="" boundary="" window lower upper id encoded number=0
    local render_args=()
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output|--from|--to|--calendar|--tz|--start-at)
                [ -n "${2:-}" ] || { _google_error 'Missing calendar export option value'; return 1; }
                case "$1" in --output) out="$2" ;; --from) from="$2" ;; --to) to="$2" ;; --calendar) ids="$2" ;; --tz) tz="$2" ;; --start-at) boundary="$2" ;; esac
                shift 2 ;;
            --compact) compact=1; shift ;;
            --data) data=1; shift ;;
            *) _google_error 'Unknown calendar export option'; return 1 ;;
        esac
    done
    [ -n "$out" ] || { _google_error 'export requires --output FILE'; return 1; }
    [ "$data" -eq 0 ] || { [ -n "$from" ] && [ -n "$to" ] && [ "$compact" -eq 0 ] || { _google_error 'export-data requires explicit instant bounds and no compact mode'; return 1; }; }
    _calendar_token_ready || return 1
    if [ -n "$from$to" ]; then
        [ -n "$from" ] && [ -n "$to" ] || { _google_error 'Supply both --from and --to'; return 1; }
        local bounds_mode=bounds
        [ "$data" -eq 0 ] || bounds_mode=instant-bounds
        window="$(_google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_CALENDAR_DIR/scripts/window.py" "$bounds_mode" "$from" "$to")" || return 1
    else window="$(_calendar_window)" || return 1
    fi
    lower="$(printf '%s\n' "$window" | sed -n '1p')"; upper="$(printf '%s\n' "$window" | sed -n '2p')"
    if [ "$compact" -eq 1 ]; then
        [ -n "$boundary" ] && [ -n "$tz" ] || { _google_error 'Compact export requires --start-at INSTANT and --tz'; return 1; }
    fi
    [ -n "$ids" ] || ids="$(_calendar_ids)"
    _calendar_list_fetch "$CALENDAR_WORK/calendars.json" || return 1
    for id in $(printf '%s' "$ids" | tr ',' ' '); do
        id="$(_google_trim "$id")"; [ -n "$id" ] || continue
        encoded="$(_calendar_urlencode "$id")" || return 1
        _calendar_write_metadata "$CALENDAR_WORK/calendars.json" "$id" "$CALENDAR_WORK/calendar-$number.json" || return 1
        _calendar_fetch_events "$encoded" "$lower" "$upper" "$CALENDAR_WORK/events-$number.json" 'items(id,iCalUID,recurringEventId,status,summary,description,location,htmlLink,hangoutLink,conferenceData(entryPoints(entryPointType,label,uri)),start,end),nextPageToken' || return 1
        render_args+=("$CALENDAR_WORK/calendar-$number.json" "$CALENDAR_WORK/events-$number.json")
        number=$((number + 1))
    done
    [ "$number" -gt 0 ] || { _google_error 'No calendar IDs selected'; return 1; }
    if [ "$data" -eq 1 ]; then
        local members=() member index=0
        while [ "$index" -lt "$number" ]; do
            member="$CALENDAR_WORK/member-$index.json"
            jq -n --slurpfile calendar "$CALENDAR_WORK/calendar-$index.json" --slurpfile events "$CALENDAR_WORK/events-$index.json" '{calendar: $calendar[0], events: $events[0]}' > "$member" || return 1
            members+=("$member"); index=$((index + 1))
        done
        jq -s --arg source "$GOOGLE_CALENDAR_ALIAS" --arg start "$lower" --arg end "$upper" '{schema_version: 1, provider: "google", source: $source, start: $start, end: $end, complete: true, calendars: .}' "${members[@]}" > "$CALENDAR_WORK/export.json" || return 1
        _google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_AUTH_DIR/scripts/publish.py" "$CALENDAR_WORK/export.json" "$out" replace || return 1
        _google_say "Exported $out"
        return 0
    fi
    {
        printf '# Google Calendar\n\nWindow: %s to %s\n\n' "$lower" "$upper"
        if [ "$compact" -eq 1 ]; then _calendar_render_helper --compact --start-at "$boundary" --tz "$tz" "${render_args[@]}"
        else _calendar_render_helper "${render_args[@]}"
        fi
    } > "$CALENDAR_WORK/rendered.md" || return 1
    mkdir -p "$(dirname "$out")" || return 1
    _google_python "$GOOGLE_CALENDAR_DIR" "$GOOGLE_AUTH_DIR/scripts/publish.py" "$CALENDAR_WORK/rendered.md" "$out" replace || return 1
    _google_say "Updated $out"
)
