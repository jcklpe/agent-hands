#!/usr/bin/env bash
OUTLOOK_CONTACTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_m365_contacts_write_helper() { _m365_python "$OUTLOOK_CONTACTS_DIR" "$OUTLOOK_CONTACTS_DIR/scripts/write.py" "$@"; }
_m365_contacts_render_helper() { _m365_python "$OUTLOOK_CONTACTS_DIR" "$OUTLOOK_CONTACTS_DIR/scripts/render.py" "$@"; }

_m365_contacts_max() {
    local alias="$1"
    _m365_account_value "$alias" '.contacts.max_results // 500' 2>/dev/null || printf '500'
}

_m365_contacts_fetch() {
    local alias="$1" out="$2" max
    max="$(_m365_contacts_max "$alias")"
    _m365_get_paginated "$alias" "$max" "$out" "$(_m365_graph_base "$alias")/me/contacts" \
        --data-urlencode "\$top=${max}" \
        --data-urlencode "\$orderby=displayName" \
        --data-urlencode "\$select=id,displayName,givenName,surname,emailAddresses,businessPhones,mobilePhone,companyName,jobTitle,personalNotes,parentFolderId"
}

_m365_contacts_human() {
    jq -r '
      (.value // [])[] |
      [
        ("- " + (.displayName // .givenName // "Unnamed contact")),
        ("contact_id: " + (.id // "")),
        ("email: " + (((.emailAddresses // []) | map(.address // "") | map(select(. != ""))) | join(", "))),
        (if ((.companyName // "") != "") then "company: " + .companyName else empty end),
        (if ((.jobTitle // "") != "") then "title: " + .jobTitle else empty end)
      ] | join(" | ")
    '
}

_m365_contacts_list() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" json_mode=0 data
    [ -n "$alias" ] || { _m365_error "m365 contacts list requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do case "$1" in --json) json_mode=1; shift ;; *) _m365_error "Unknown m365 contacts list option: $1"; return 1 ;; esac; done
    _m365_require_enabled "$alias" contacts || return 1
    data="$(mktemp "$M365_WORK/contacts.XXXXXX")" || return 1
    _m365_contacts_fetch "$alias" "$data" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "$data"; else _m365_contacts_human < "$data"; fi
)

_m365_contacts_find() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" query="" json_mode=0 data results
    [ -n "$alias" ] || { _m365_error "m365 contacts find requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json_mode=1; shift ;;
            -*) _m365_error "Unknown m365 contacts find option: $1"; return 1 ;;
            *) if [ -z "$query" ]; then query="$1"; shift; else _m365_error "Unexpected argument: $1"; return 1; fi ;;
        esac
    done
    [ -n "$query" ] || { _m365_error "m365 contacts find requires QUERY"; return 1; }
    _m365_require_enabled "$alias" contacts || return 1
    data="$(mktemp "$M365_WORK/contacts-find.XXXXXX")" || return 1
    results="$(mktemp "$M365_WORK/contacts-results.XXXXXX")" || return 1
    _m365_contacts_fetch "$alias" "$data" || return 1
    jq --arg q "$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')" '{value: [(.value // [])[] | select((((.displayName // "") + " " + (.givenName // "") + " " + (.surname // "") + " " + (.companyName // "") + " " + (.jobTitle // "") + " " + (((.emailAddresses // []) | map(.address // "")) | join(" "))) | ascii_downcase | contains($q)))]}' "$data" > "$results" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "$results"; elif [ "$(jq '(.value // []) | length' "$results")" -eq 0 ]; then _m365_say "No matching Outlook contacts found."; else _m365_contacts_human < "$results"; fi
)

_m365_contacts_create() {
    local alias="${1:-}" display_name="" given_name="" surname="" mobile="" company="" job_title="" notes="" notes_file="" execute=0 body created
    local set_display=0 set_given=0 set_surname=0 set_mobile=0 set_company=0 set_job=0 set_notes=0 emails=() phones=() args=()
    [ -n "$alias" ] || { _m365_error "m365 contacts create requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --display-name) [ -n "${2+x}" ] || { _m365_error "--display-name requires TEXT"; return 1; }; display_name="$2"; set_display=1; shift 2 ;;
            --given-name) [ -n "${2+x}" ] || { _m365_error "--given-name requires TEXT"; return 1; }; given_name="$2"; set_given=1; shift 2 ;;
            --surname) [ -n "${2+x}" ] || { _m365_error "--surname requires TEXT"; return 1; }; surname="$2"; set_surname=1; shift 2 ;;
            --email) [ -n "${2:-}" ] || { _m365_error "--email requires ADDRESS"; return 1; }; emails+=("$2"); shift 2 ;;
            --phone) [ -n "${2:-}" ] || { _m365_error "--phone requires NUMBER"; return 1; }; phones+=("$2"); shift 2 ;;
            --mobile) [ -n "${2+x}" ] || { _m365_error "--mobile requires NUMBER"; return 1; }; mobile="$2"; set_mobile=1; shift 2 ;;
            --company) [ -n "${2+x}" ] || { _m365_error "--company requires TEXT"; return 1; }; company="$2"; set_company=1; shift 2 ;;
            --job-title) [ -n "${2+x}" ] || { _m365_error "--job-title requires TEXT"; return 1; }; job_title="$2"; set_job=1; shift 2 ;;
            --notes) [ -n "${2+x}" ] || { _m365_error "--notes requires TEXT"; return 1; }; notes="$2"; set_notes=1; shift 2 ;;
            --notes-file) [ -n "${2:-}" ] || { _m365_error "--notes-file requires FILE"; return 1; }; notes_file="$2"; set_notes=1; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 contacts create option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" contacts || return 1
    if [ -n "$notes_file" ]; then [ -f "$notes_file" ] || { _m365_error "Notes file does not exist: $notes_file"; return 1; }; notes="$(cat "$notes_file")"; fi
    args=(contact)
    [ "$set_display" -eq 1 ] && args+=(--display-name "$display_name")
    [ "$set_given" -eq 1 ] && args+=(--given-name "$given_name")
    [ "$set_surname" -eq 1 ] && args+=(--surname "$surname")
    local value
    for value in ${emails[@]+"${emails[@]}"}; do args+=(--email "$value"); done
    for value in ${phones[@]+"${phones[@]}"}; do args+=(--phone "$value"); done
    [ "$set_mobile" -eq 1 ] && args+=(--mobile "$mobile")
    [ "$set_company" -eq 1 ] && args+=(--company "$company")
    [ "$set_job" -eq 1 ] && args+=(--job-title "$job_title")
    [ "$set_notes" -eq 1 ] && args+=(--notes "$notes")
    body="$(_m365_contacts_write_helper "${args[@]}")" || return 1
    _m365_say "Outlook contact create plan:"
    _m365_say "Account: $alias"
    printf '%s' "$body" | jq .
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no contact was created. Re-run with --execute to create it."; return 0; fi
    created="$(_m365_write POST "$alias" "$(_m365_graph_base "$alias")/me/contacts" "$body")" || return 1
    _m365_say "Created contact: $(printf '%s' "$created" | jq -r '(.displayName // "Contact") + " | id: " + (.id // "")')"
}

_m365_contacts_update() {
    local alias="${1:-}" contact_id="" display_name="" given_name="" surname="" mobile="" company="" job_title="" notes="" notes_file="" execute=0 body current updated encoded
    local set_display=0 set_given=0 set_surname=0 set_mobile=0 set_company=0 set_job=0 set_notes=0 emails=() phones=() args=()
    [ -n "$alias" ] || { _m365_error "m365 contacts update requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --contact) [ -n "${2:-}" ] || { _m365_error "--contact requires ID"; return 1; }; contact_id="$2"; shift 2 ;;
            --display-name) [ -n "${2+x}" ] || { _m365_error "--display-name requires TEXT"; return 1; }; display_name="$2"; set_display=1; shift 2 ;;
            --given-name) [ -n "${2+x}" ] || { _m365_error "--given-name requires TEXT"; return 1; }; given_name="$2"; set_given=1; shift 2 ;;
            --surname) [ -n "${2+x}" ] || { _m365_error "--surname requires TEXT"; return 1; }; surname="$2"; set_surname=1; shift 2 ;;
            --email) [ -n "${2:-}" ] || { _m365_error "--email requires ADDRESS"; return 1; }; emails+=("$2"); shift 2 ;;
            --phone) [ -n "${2:-}" ] || { _m365_error "--phone requires NUMBER"; return 1; }; phones+=("$2"); shift 2 ;;
            --mobile) [ -n "${2+x}" ] || { _m365_error "--mobile requires NUMBER"; return 1; }; mobile="$2"; set_mobile=1; shift 2 ;;
            --company) [ -n "${2+x}" ] || { _m365_error "--company requires TEXT"; return 1; }; company="$2"; set_company=1; shift 2 ;;
            --job-title) [ -n "${2+x}" ] || { _m365_error "--job-title requires TEXT"; return 1; }; job_title="$2"; set_job=1; shift 2 ;;
            --notes) [ -n "${2+x}" ] || { _m365_error "--notes requires TEXT"; return 1; }; notes="$2"; set_notes=1; shift 2 ;;
            --notes-file) [ -n "${2:-}" ] || { _m365_error "--notes-file requires FILE"; return 1; }; notes_file="$2"; set_notes=1; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 contacts update option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" contacts || return 1
    [ -n "$contact_id" ] || { _m365_error "contacts update requires --contact"; return 1; }
    if [ -n "$notes_file" ]; then [ -f "$notes_file" ] || { _m365_error "Notes file does not exist: $notes_file"; return 1; }; notes="$(cat "$notes_file")"; fi
    encoded="$(_m365_uri_encode "$contact_id")" || return 1
    current="$(_m365_get "$alias" "$(_m365_graph_base "$alias")/me/contacts/${encoded}")" || return 1
    args=(contact)
    [ "$set_display" -eq 1 ] && args+=(--display-name "$display_name")
    [ "$set_given" -eq 1 ] && args+=(--given-name "$given_name")
    [ "$set_surname" -eq 1 ] && args+=(--surname "$surname")
    local value
    for value in ${emails[@]+"${emails[@]}"}; do args+=(--email "$value"); done
    for value in ${phones[@]+"${phones[@]}"}; do args+=(--phone "$value"); done
    [ "$set_mobile" -eq 1 ] && args+=(--mobile "$mobile")
    [ "$set_company" -eq 1 ] && args+=(--company "$company")
    [ "$set_job" -eq 1 ] && args+=(--job-title "$job_title")
    [ "$set_notes" -eq 1 ] && args+=(--notes "$notes")
    body="$(_m365_contacts_write_helper "${args[@]}")" || return 1
    _m365_say "Outlook contact update plan:"
    _m365_say "Account: $alias"
    _m365_say "Contact: $contact_id"
    _m365_say "Current name: $(printf '%s' "$current" | jq -r '.displayName // "(unnamed)"')"
    _m365_say "Changes:"
    printf '%s' "$body" | jq .
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no contact was updated. Re-run with --execute to apply."; return 0; fi
    updated="$(_m365_write PATCH "$alias" "$(_m365_graph_base "$alias")/me/contacts/${encoded}" "$body")" || return 1
    _m365_say "Updated contact: $(printf '%s' "$updated" | jq -r '(.displayName // "Contact") + " | id: " + (.id // "")')"
}

_m365_contacts_export() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" out="" notes_limit max email refreshed
    [ -n "$alias" ] || { _m365_error 'contacts export requires ALIAS --output PATH'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in --output) [ -n "${2:-}" ] || return 1; out="$2"; shift 2 ;; *) _m365_error "Unknown contacts export option: $1"; return 1 ;; esac
    done
    [ -n "$out" ] && [ -d "$(dirname "$out")" ] && [ ! -L "$out" ] || { _m365_error 'Choose an output file in an existing directory, not a symlink'; return 1; }
    _m365_require_enabled "$alias" contacts || return 1
    _m365_contacts_fetch "$alias" "$M365_WORK/contacts.json" || return 1
    email="$(_m365_profile_email "$alias")" || return 1
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    max="$(_m365_contacts_max "$alias")"
    notes_limit="$(_m365_account_value "$alias" '.contacts.notes_character_limit // 4000')" || notes_limit=4000
    case "$notes_limit" in ''|*[!0-9]*) _m365_error 'notes_character_limit must be a nonnegative integer'; return 1 ;; esac
    _m365_contacts_render_helper contacts --alias "$alias" --email "$email" --refreshed "$refreshed" --max-results "$max" --notes-limit "$notes_limit" --input "$M365_WORK/contacts.json" > "$M365_WORK/export.md" || return 1
    _m365_python "$OUTLOOK_CONTACTS_DIR" "$M365_AUTH_DIR/scripts/publish.py" "$M365_WORK/export.md" "$out" replace || return 1
    _m365_say "Updated $out"
)
