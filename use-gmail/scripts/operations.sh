#!/usr/bin/env bash
##- Portable Gmail operations; provider support is the only runtime skill dependency.
GOOGLE_GMAIL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_gmail_retry_cap() { printf '%s' "${GOOGLE_GMAIL_MAX_RETRIES:-5}"; }
_gmail_warn() { printf 'WARN: %s\n' "$*" >&2; }
_gmail_urlencode() { jq -rn --arg value "$1" '$value | @uri'; }
_gmail_work_begin() {
    GMAIL_WORK="$(mktemp -d "${TMPDIR:-/tmp}/google-gmail.XXXXXX")" || return 1
    trap 'rm -rf "$GMAIL_WORK"' EXIT
    trap 'exit 130' HUP INT TERM
}
_gmail_read_ids_file() {
    local file="$1" line
    [ -f "$file" ] || { _google_error 'IDs file does not exist'; return 1; }
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_google_trim "$line")"
        case "$line" in ''|\#*) continue ;; esac
        printf '%s\n' "$line"
    done < "$file"
}
_gmail_audit_log_path() {
    case "${GOOGLE_GMAIL_AUDIT_LOG:-mail-writes.jsonl}" in
        /*) printf '%s\n' "$GOOGLE_GMAIL_AUDIT_LOG" ;;
        *) printf '%s/%s\n' "$GOOGLE_GMAIL_DIR" "${GOOGLE_GMAIL_AUDIT_LOG:-mail-writes.jsonl}" ;;
    esac
}
_gmail_audit_append() { _google_python "$GOOGLE_GMAIL_DIR" "$GOOGLE_GMAIL_DIR/scripts/audit.py" "$(_gmail_audit_log_path)"; }
_gmail_export() {
    local alias="${1:-}" out="" query="" maximum=""
    [ -n "$alias" ] || { _google_error 'export requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output|--query|--max-results)
                [ -n "${2:-}" ] || { _google_error 'Missing export option value'; return 1; }
                case "$1" in --output) out="$2" ;; --query) query="$2" ;; --max-results) maximum="$2" ;; esac
                shift 2 ;;
            *) _google_error 'Unknown Gmail export option'; return 1 ;;
        esac
    done
    [ -n "$out" ] || { _google_error 'export requires --output FILE'; return 1; }
    _gmail_export_alias "$alias" "$out" "$query" "$maximum"
}

_gmail_query() {
    _google_account_value "$1" '.gmail.query' 2>/dev/null || { _google_error 'Supply --query or configure gmail.query for an export'; return 1; }
}

_gmail_max_results() {
    local alias="$1"
    _google_account_value "$alias" '.gmail.max_results // 150' 2>/dev/null || printf '150'
}

_gmail_body_limit() {
    local alias="$1"
    _google_account_value "$alias" '.gmail.body_character_limit // 8000' 2>/dev/null || printf '8000'
}

_gmail_render_helper() {
    _google_python "$GOOGLE_GMAIL_DIR" "$GOOGLE_GMAIL_DIR/scripts/render.py" "$@"
}

# GET a Gmail API URL, surfacing Google's error message and backing off on rate limits. Gmail enforces a per-user query-cost quota per minute, and a full-format sync of a busy inbox can exceed it.
_gmail_get() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="$1" url="$2" token response http_code reason message attempt=0 delay=2
    shift 2
    response="$(mktemp "$GMAIL_WORK/gmail-get.XXXXXX")" || return 1
    while :; do
        token="$(_google_access_token "$alias")" || { rm -f "$response"; return 1; }
        http_code="$(curl -sS -o "$response" -w '%{http_code}' --get "$url" -H "Authorization: Bearer ${token}" "$@")" || { rm -f "$response"; _google_error "Gmail request failed before receiving a response"; return 1; }
        case "$http_code" in
            2??) cat "$response"; rm -f "$response"; return 0 ;;
        esac
        reason="$(jq -r '.error.errors[0].reason // .error.status // empty' "$response" 2>/dev/null)"
        message="$(jq -r '.error.message // empty' "$response" 2>/dev/null)"
        case "$http_code:$reason" in
            429:*|403:rateLimitExceeded|403:userRateLimitExceeded)
                attempt=$((attempt + 1))
                if [ "$attempt" -le "$(_gmail_retry_cap)" ]; then
                    _gmail_warn "Gmail rate limit for '$alias' (HTTP $http_code); retrying in ${delay}s (attempt $attempt)"
                    sleep "$delay"
                    delay=$((delay * 2))
                    continue
                fi
                ;;
        esac
        rm -f "$response"
        _google_error "Gmail returned HTTP ${http_code} for '$alias'${reason:+ ($reason)}: ${message:-request failed}"
        case "$reason" in
            rateLimitExceeded|userRateLimitExceeded) _google_say "NEXT: wait a minute and retry, or narrow the sync with --query or --max-results" >&2 ;;
            insufficientPermissions|ACCESS_TOKEN_SCOPE_INSUFFICIENT) _google_say "NEXT: run 'setup-google-services/scripts/authorize auth $alias' to refresh the granted scopes" >&2 ;;
        esac
        return 1
    done
)

_gmail_export_alias() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="$1"
    local out="$2"
    local query_override="${3:-}" max_override="${4:-}"
    local query max_results body_limit email_address refreshed
    local list_file msg_dir messages_file message_id message_file count

    _gmail_require_enabled "$alias" || return 1
    query="${query_override:-$(_gmail_query "$alias")}" || return 1
    max_results="${max_override:-$(_gmail_max_results "$alias")}"
    body_limit="$(_gmail_body_limit "$alias")"
    email_address="$(_google_account_email "$alias")"
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"

    case "$max_results" in ''|*[!0-9]*) _google_error 'max-results must be an integer'; return 1 ;; esac
    [ "$max_results" -ge 1 ] && [ "$max_results" -le 500 ] || { _google_error 'max-results must be between 1 and 500'; return 1; }
    case "$body_limit" in ''|*[!0-9]*) _google_error 'body_character_limit must be a nonnegative integer'; return 1 ;; esac
    mkdir -p "$(dirname "$out")" || return 1
    list_file="$(mktemp "$GMAIL_WORK/gmail-list.XXXXXX")" || return 1
    msg_dir="$(mktemp -d "$GMAIL_WORK/gmail-messages.XXXXXX")" || return 1
    messages_file="$(mktemp "$GMAIL_WORK/gmail-render.XXXXXX")" || return 1

    _google_say "Exporting Gmail: ${alias}" >&2
    _gmail_get "$alias" "https://gmail.googleapis.com/gmail/v1/users/me/messages" \
        --data-urlencode "q=${query}" \
        --data-urlencode "maxResults=${max_results}" > "$list_file" || return 1

    jq -e '(.error == null) and ((.messages // []) | type == "array")' "$list_file" >/dev/null || { _google_error 'Invalid Gmail list response'; return 1; }
    if jq -e '.nextPageToken != null' "$list_file" >/dev/null; then _gmail_warn 'Additional messages exist beyond this export bound'; fi
    count=0
    for message_id in $(jq -r '.messages[]?.id' "$list_file"); do
        message_file="${msg_dir}/$(printf '%05d' "$count").json"
        _gmail_get "$alias" "https://gmail.googleapis.com/gmail/v1/users/me/messages/$(_gmail_urlencode "$message_id")" \
            --data-urlencode "format=full" > "$message_file" || return 1
        jq -e --arg id "$message_id" 'type == "object" and .error == null and .id == $id and (.payload | type == "object")' "$message_file" >/dev/null || { _google_error 'Invalid Gmail message response'; return 1; }
        count=$((count + 1))
    done

    if [ "$count" -eq 0 ]; then
        jq -n '{messages: []}' > "$messages_file"
    else
        jq -s '{messages: .}' "${msg_dir}"/*.json > "$messages_file"
    fi

    _gmail_render_helper "$alias" "$email_address" "$query" "$max_results" "$body_limit" "$refreshed" "$messages_file" > "$GMAIL_WORK/rendered.md" || return 1
    _google_python "$GOOGLE_GMAIL_DIR" "$GOOGLE_AUTH_DIR/scripts/publish.py" "$GMAIL_WORK/rendered.md" "$out" replace || return 1
    _google_say "Updated $out"
)

##- Gmail labels and archiving. Reads (labels, list) use the read-only scope; executed changes also need gmail.write_enabled, which adds gmail.modify at the next 'setup-google-services/scripts/authorize auth ALIAS'.
##- The only label changes are removing or restoring INBOX (archive and unarchive), adding or removing user labels, and moving mail out of Spam (not-spam). There is no trash, delete, report-spam, send, or mark-read command, and messages in Trash, or in Spam outside not-spam, are refused.
_GMAIL_API='https://gmail.googleapis.com/gmail/v1/users/me'

_gmail_require_enabled() {
    local alias="$1"
    _google_account_exists "$alias" || { _google_error "Unknown Google account alias: $alias"; return 1; }
    if ! _google_account_value "$alias" '(.gmail.enabled // false) == true' 2>/dev/null | grep -qx true; then
        _google_error "Gmail is not enabled for alias '$alias'"
        return 1
    fi
}

_gmail_require_write() {
    local alias="$1"
    if ! _google_account_value "$alias" '(.gmail.write_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _google_error "Gmail label changes are not enabled for alias '$alias'"
        _google_say "NEXT: set gmail.write_enabled to true for '$alias' in $(_google_accounts_path), then run 'setup-google-services/scripts/authorize auth $alias' to grant gmail.modify" >&2
        return 1
    fi
}

_gmail_change_cap() {
    _google_account_value "$1" '.gmail.max_changes_per_call // 50' 2>/dev/null || printf '50'
}

# _gmail_send METHOD ALIAS URL BODY: a Gmail write that surfaces Google's error message instead of curl's bare status.
_gmail_send() (
    set -o pipefail
    _gmail_work_begin || return 1
    local method="$1" alias="$2" url="$3" body="$4" token response http_code message
    token="$(_google_access_token "$alias")" || return 1
    response="$(mktemp "$GMAIL_WORK/gmail-response.XXXXXX")" || return 1
    http_code="$(curl -sS -o "$response" -w '%{http_code}' -X "$method" "$url" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json; charset=utf-8" \
        --data-binary "$body")" || { _google_error "Gmail request failed before receiving a response"; return 1; }
    case "$http_code" in
        2??) cat "$response" ;;
        *)
            message="$(jq -r '.error.message // empty' "$response" 2>/dev/null)"
            _google_error "Gmail returned HTTP ${http_code}: ${message:-request failed}"
            if [ "$http_code" = "403" ]; then
                _google_say "NEXT: if the token predates gmail.write_enabled, run 'setup-google-services/scripts/authorize auth $alias' to grant gmail.modify" >&2
            fi
            return 1
            ;;
    esac
)

_gmail_labels_fetch() {
    _google_get_url "$1" "${_GMAIL_API}/labels"
}

_gmail_labels() {
    local alias="${1:-}" json_mode=0 labels
    [ -n "$alias" ] || { _google_error "gmail labels requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json_mode=1; shift ;;
            *) _google_error "Unknown gmail labels option: $1"; return 1 ;;
        esac
    done
    _gmail_require_enabled "$alias" || return 1
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    if [ "$json_mode" -eq 1 ]; then
        printf '%s\n' "$labels"
    else
        printf '%s' "$labels" | jq -r '(.labels // []) | sort_by([.type != "user", (.name | ascii_downcase)]) | .[] | "- " + .name + " | id: " + .id + " | type: " + .type'
    fi
}

# Resolve SPEC (an exact label ID or a case-insensitive label name) to a user label and print it as JSON. System labels are refused; INBOX is changed only by archive and unarchive.
_gmail_resolve_user_label() {
    local labels="$1" spec="$2" match
    match="$(printf '%s' "$labels" | jq -c --arg s "$spec" '[(.labels // [])[] | select(.id == $s or ((.name | ascii_downcase) == ($s | ascii_downcase)))] | first // empty')"
    if [ -z "$match" ]; then
        _google_error "No Gmail label matches '$spec'. Run 'gmail labels ALIAS' to see labels, or 'gmail create-label' to make one."
        return 1
    fi
    if [ "$(printf '%s' "$match" | jq -r '.type')" != "user" ]; then
        _google_error "'$spec' is a Gmail system label; only user labels can be applied or removed (use gmail archive or unarchive for INBOX)"
        return 1
    fi
    printf '%s\n' "$match"
}

_gmail_list() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" label_spec="" query="" limit=25 json_mode=0 labels label list dir id n=0 args=()
    [ -n "$alias" ] || { _google_error "gmail list requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --label) [ -n "${2:-}" ] || { _google_error "--label requires NAME or ID"; return 1; }; label_spec="$2"; shift 2 ;;
            --query) [ -n "${2:-}" ] || { _google_error "--query requires a Gmail search"; return 1; }; query="$2"; shift 2 ;;
            --limit) [ -n "${2:-}" ] || { _google_error "--limit requires N"; return 1; }; limit="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _google_error "Unknown gmail list option: $1"; return 1 ;;
        esac
    done
    [ -n "$label_spec" ] || [ -n "$query" ] || { _google_error "gmail list requires --label or --query"; return 1; }
    case "$limit" in ''|*[!0-9]*) _google_error "--limit must be a positive integer"; return 1 ;; esac
    [ "$limit" -ge 1 ] && [ "$limit" -le 100 ] || { _google_error "--limit must be between 1 and 100"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    args=(--data-urlencode "maxResults=${limit}")
    if [ -n "$label_spec" ]; then
        labels="$(_gmail_labels_fetch "$alias")" || return 1
        label="$(printf '%s' "$labels" | jq -c --arg s "$label_spec" '[(.labels // [])[] | select(.id == $s or ((.name | ascii_downcase) == ($s | ascii_downcase)))] | first // empty')"
        [ -n "$label" ] || { _google_error "No Gmail label matches '$label_spec'. Run 'gmail labels $alias'."; return 1; }
        args+=(--data-urlencode "labelIds=$(printf '%s' "$label" | jq -r '.id')")
    fi
    [ -n "$query" ] && args+=(--data-urlencode "q=${query}")
    dir="$(mktemp -d "$GMAIL_WORK/gmail-list.XXXXXX")" || return 1
    list="$(_google_get_url "$alias" "${_GMAIL_API}/messages" "${args[@]}")" || return 1
    if printf '%s' "$list" | jq -e '.nextPageToken != null' >/dev/null; then _gmail_warn "More messages exist beyond this listing bound"; fi
    for id in $(printf '%s' "$list" | jq -r '.messages[]?.id'); do
        _google_get_url "$alias" "${_GMAIL_API}/messages/$(_gmail_urlencode "$id")" \
            --data-urlencode "format=metadata" \
            --data-urlencode "metadataHeaders=From" \
            --data-urlencode "metadataHeaders=Subject" \
            --data-urlencode "metadataHeaders=Date" > "${dir}/$(printf '%04d' "$n").json" || return 1
        n=$((n + 1))
    done
    if [ "$n" -eq 0 ]; then printf '[]\n' > "${dir}/all.json"; else jq -s '.' "${dir}"/0*.json > "${dir}/all.json"; fi
    if [ "$json_mode" -eq 1 ]; then
        cat "${dir}/all.json"
    elif [ "$n" -eq 0 ]; then
        _google_say "No matching Gmail messages."
    else
        jq -r '.[] |
          ((.payload.headers // []) | map({key: (.name | ascii_downcase), value: .value}) | from_entries) as $h |
          "- " + ($h.date // "") + " | from: " + ($h.from // "") + " | " + ($h.subject // "(no subject)") +
          " | labels: " + ((.labelIds // []) | join(",")) +
          "\n  message_id: " + .id + " | thread_id: " + .threadId
        ' "${dir}/all.json"
    fi
)

# Shared engine for archive, unarchive, label, and unlabel. ADD and REMOVE are JSON arrays of label IDs. PRECONDITION is "in-inbox", "not-in-inbox", or empty.
_gmail_change_run() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="$1" action="$2" add="$3" remove="$4" precondition="$5" execute="$6" describe="$7" ids_file="$8"
    local dir cap count kind id n=0 ts failures
    _gmail_require_enabled "$alias" || return 1
    count="$(jq 'length' "$ids_file")"
    [ "$count" -gt 0 ] || { _google_error "gmail $action requires at least one --message ID, --thread ID, or --ids-file"; return 1; }
    cap="$(_gmail_change_cap "$alias")"
    [ "$count" -le "$cap" ] || { _google_error "gmail $action accepts at most $cap targets per call (got $count); split the list"; return 1; }
    dir="$(mktemp -d "$GMAIL_WORK/gmail-change.XXXXXX")" || return 1
    # Fetch each target so missing IDs fail up front and the plan can show what will change.
    while IFS=$'\t' read -r kind id; do
        if [ "$kind" = "thread" ]; then
            _google_get_url "$alias" "${_GMAIL_API}/threads/$(_gmail_urlencode "$id")" --data-urlencode "format=metadata" --data-urlencode "metadataHeaders=From" --data-urlencode "metadataHeaders=Subject" > "${dir}/t-${n}.json" \
                || printf '{"missing": true}\n' > "${dir}/t-${n}.json"
        else
            _google_get_url "$alias" "${_GMAIL_API}/messages/$(_gmail_urlencode "$id")" --data-urlencode "format=metadata" --data-urlencode "metadataHeaders=From" --data-urlencode "metadataHeaders=Subject" > "${dir}/t-${n}.json" \
                || printf '{"missing": true}\n' > "${dir}/t-${n}.json"
        fi
        jq -c --arg kind "$kind" --arg id "$id" '
          (if $kind == "thread" then (.messages // []) else [.] end) as $msgs |
          ($msgs[0] // {}) as $first |
          ((($first.payload.headers // []) | map({key: (.name | ascii_downcase), value: .value}) | from_entries)) as $h |
          {kind: $kind, id: $id, missing: (.missing // false),
           messageIds: [$msgs[] | .id | select(. != null)],
           labels: ([$msgs[] | (.labelIds // [])[]] | unique),
           subject: ($h.subject // "(no subject)"), from: ($h.from // ""), count: ($msgs | length)}
        ' "${dir}/t-${n}.json" >> "${dir}/targets.jsonl"
        n=$((n + 1))
    done < <(jq -r '.[] | [.kind, .id] | @tsv' "$ids_file")
    jq -s '.' "${dir}/targets.jsonl" > "${dir}/targets.json"
    if jq -e 'any(.[]; .missing)' "${dir}/targets.json" >/dev/null; then
        _google_error "These Gmail IDs were not found; nothing was changed:"
        jq -r '.[] | select(.missing) | "  - " + .kind + " " + .id' "${dir}/targets.json" >&2
        return 1
    fi
    # Spam is off limits except to not-spam, whose whole job is to rescue it; Trash is always off limits.
    if [ "$precondition" = "in-spam" ]; then
        if jq -e 'any(.[]; (.labels | index("TRASH")) or ((.labels | index("SPAM")) | not))' "${dir}/targets.json" >/dev/null; then
            _google_error "gmail $action only rescues mail that is currently in Spam (and not in Trash); nothing was changed. Out of place:"
            jq -r '.[] | select((.labels | index("TRASH")) or ((.labels | index("SPAM")) | not)) | "  - " + .subject + " | " + .kind + " " + .id' "${dir}/targets.json" >&2
            return 1
        fi
    elif jq -e 'any(.[]; (.labels | index("TRASH")) or (.labels | index("SPAM")))' "${dir}/targets.json" >/dev/null; then
        _google_error "Some targets are in Trash or Spam, which these commands never touch (use gmail not-spam to rescue Spam); nothing was changed:"
        jq -r '.[] | select((.labels | index("TRASH")) or (.labels | index("SPAM"))) | "  - " + .subject + " | " + .kind + " " + .id' "${dir}/targets.json" >&2
        return 1
    fi
    case "$precondition" in
        in-inbox)
            if jq -e 'any(.[]; (.labels | index("INBOX")) | not)' "${dir}/targets.json" >/dev/null; then
                _google_error "gmail $action only changes mail that is currently in the Inbox; nothing was changed. Not in Inbox:"
                jq -r '.[] | select((.labels | index("INBOX")) | not) | "  - " + .subject + " | " + .kind + " " + .id' "${dir}/targets.json" >&2
                return 1
            fi
            ;;
        not-in-inbox)
            if jq -e 'any(.[]; .labels | index("INBOX"))' "${dir}/targets.json" >/dev/null; then
                _google_error "gmail $action only restores mail that is not in the Inbox; nothing was changed. Already in Inbox:"
                jq -r '.[] | select(.labels | index("INBOX")) | "  - " + .subject + " | " + .kind + " " + .id' "${dir}/targets.json" >&2
                return 1
            fi
            ;;
    esac
    _google_say "Gmail $action plan:"
    _google_say "Account: $alias"
    _google_say "Change: $describe"
    _google_say "Targets: $count"
    jq -r '.[] | "- " + .kind + (if .kind == "thread" then " (" + (.count | tostring) + " messages)" else "" end) + " | " + .from + " | " + .subject' "${dir}/targets.json"
    if [ "$execute" -ne 1 ]; then _google_say "DRY RUN: nothing was changed. Re-run with --execute to apply."; return 0; fi
    _gmail_require_write "$alias" || return 1
    jq -c --argjson add "$add" --argjson remove "$remove" '{ids: [.[] | select(.kind == "message") | .id], addLabelIds: $add, removeLabelIds: $remove}' "${dir}/targets.json" > "${dir}/batch.json"
    if jq -e '.ids | length > 0' "${dir}/batch.json" >/dev/null; then
        _gmail_send POST "$alias" "${_GMAIL_API}/messages/batchModify" "$(cat "${dir}/batch.json")" >/dev/null || return 1
    fi
    for id in $(jq -r '.[] | select(.kind == "thread") | .id' "${dir}/targets.json"); do
        _gmail_send POST "$alias" "${_GMAIL_API}/threads/$(_gmail_urlencode "$id")/modify" "$(jq -cn --argjson add "$add" --argjson remove "$remove" '{addLabelIds: $add, removeLabelIds: $remove}')" >/dev/null || return 1
    done
    # Read back every affected message and confirm the added labels are present and the removed ones gone.
    : > "${dir}/readback.jsonl"
    for id in $(jq -r '.[].messageIds[]' "${dir}/targets.json"); do
        _google_get_url "$alias" "${_GMAIL_API}/messages/$(_gmail_urlencode "$id")" --data-urlencode "format=minimal" | jq -c '{id, labelIds: (.labelIds // [])}' >> "${dir}/readback.jsonl" || return 1
    done
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    jq -s --slurpfile t "${dir}/targets.json" --argjson add "$add" --argjson remove "$remove" '
      (map({key: .id, value: .labelIds}) | from_entries) as $now |
      [$t[0][] | . as $target |
        {kind, id, subject, from,
         verified: all(.messageIds[]; ($now[.] // null) as $l | $l != null and all($add[]; . as $a | $l | index($a)) and all($remove[]; . as $r | ($l | index($r)) | not))}]
    ' "${dir}/readback.jsonl" > "${dir}/results.json" || return 1
    jq -c --arg ts "$ts" --arg alias "$alias" --arg action "$action" --argjson add "$add" --argjson remove "$remove" '.[] | {ts: $ts, service: "gmail", alias: $alias, action: $action, target_kind: .kind, target_id: .id, add_labels: $add, remove_labels: $remove, sender: .from, subject: .subject, verified: .verified}' "${dir}/results.json" | _gmail_audit_append || _gmail_warn "Could not append to the mail audit log: $(_gmail_audit_log_path)"
    jq -r '.[] | (if .verified then "- done: " else "- NOT CONFIRMED: " end) + .subject + " | " + .kind + " " + .id' "${dir}/results.json"
    failures="$(jq '[.[] | select(.verified | not)] | length' "${dir}/results.json")"
    if [ "$failures" -gt 0 ]; then
        _google_error "$failures of $count targets were not confirmed by readback"
        return 1
    fi
    _google_say "Applied to $count targets (confirmed by readback)."
)

# Parses shared target options into a JSON array file of {kind, id} at _GMAIL_TARGETS_FILE, plus _GMAIL_LABEL, _GMAIL_SKIP_INBOX, and _GMAIL_EXECUTE.
_gmail_change_args() {
    local command="$1" line
    shift
    _GMAIL_TARGETS_FILE="$(mktemp "$GMAIL_WORK/gmail-targets.XXXXXX")" || return 1
    _GMAIL_LABEL=""
    _GMAIL_SKIP_INBOX=0
    _GMAIL_EXECUTE=0
    : > "${_GMAIL_TARGETS_FILE}.tsv"
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message) [ -n "${2:-}" ] || { _google_error "--message requires ID"; return 1; }; printf 'message\t%s\n' "$2" >> "${_GMAIL_TARGETS_FILE}.tsv"; shift 2 ;;
            --thread) [ -n "${2:-}" ] || { _google_error "--thread requires ID"; return 1; }; printf 'thread\t%s\n' "$2" >> "${_GMAIL_TARGETS_FILE}.tsv"; shift 2 ;;
            --ids-file)
                [ -n "${2:-}" ] || { _google_error "--ids-file requires FILE"; return 1; }
                _gmail_read_ids_file "$2" > /dev/null || return 1
                while IFS= read -r line; do
                    case "$line" in
                        message:*) printf 'message\t%s\n' "${line#message:}" ;;
                        thread:*) printf 'thread\t%s\n' "${line#thread:}" ;;
                        *) _google_error "Each --ids-file line must be message:ID or thread:ID (got '$line')"; return 1 ;;
                    esac
                done >> "${_GMAIL_TARGETS_FILE}.tsv" <<EOF
$(_gmail_read_ids_file "$2")
EOF
                shift 2
                ;;
            --label)
                case "$command" in label|unlabel) ;; *) _google_error "gmail $command does not take --label"; return 1 ;; esac
                [ -n "${2:-}" ] || { _google_error "--label requires NAME or ID"; return 1; }
                _GMAIL_LABEL="$2"; shift 2
                ;;
            --skip-inbox)
                [ "$command" = "label" ] || { _google_error "gmail $command does not take --skip-inbox"; return 1; }
                _GMAIL_SKIP_INBOX=1; shift
                ;;
            --execute) _GMAIL_EXECUTE=1; shift ;;
            --dry-run) _GMAIL_EXECUTE=0; shift ;;
            *) _google_error "Unknown gmail $command option: $1"; return 1 ;;
        esac
    done
    jq -R -s 'split("\n") | map(select(length > 0) | split("\t") | {kind: .[0], id: .[1]}) | unique_by([.kind, .id])' "${_GMAIL_TARGETS_FILE}.tsv" > "$_GMAIL_TARGETS_FILE"
}

_gmail_archive() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}"
    [ -n "$alias" ] || { _google_error "gmail archive requires ALIAS"; return 1; }
    shift || true
    _gmail_change_args archive "$@" || return 1
    _gmail_change_run "$alias" archive '[]' '["INBOX"]' in-inbox "$_GMAIL_EXECUTE" "remove from Inbox (archive)" "$_GMAIL_TARGETS_FILE"
)

_gmail_unarchive() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}"
    [ -n "$alias" ] || { _google_error "gmail unarchive requires ALIAS"; return 1; }
    shift || true
    _gmail_change_args unarchive "$@" || return 1
    _gmail_change_run "$alias" unarchive '["INBOX"]' '[]' not-in-inbox "$_GMAIL_EXECUTE" "return to Inbox" "$_GMAIL_TARGETS_FILE"
)

_gmail_label() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" labels label label_id label_name remove='[]' describe precondition=""
    [ -n "$alias" ] || { _google_error "gmail label requires ALIAS"; return 1; }
    shift || true
    _gmail_change_args label "$@" || return 1
    [ -n "$_GMAIL_LABEL" ] || { _google_error "gmail label requires --label"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    label="$(_gmail_resolve_user_label "$labels" "$_GMAIL_LABEL")" || return 1
    label_id="$(printf '%s' "$label" | jq -r '.id')"
    label_name="$(printf '%s' "$label" | jq -r '.name')"
    describe="add label '$label_name'"
    if [ "$_GMAIL_SKIP_INBOX" -eq 1 ]; then
        remove='["INBOX"]'
        describe="$describe and remove from Inbox"
    fi
    _gmail_change_run "$alias" label "$(jq -cn --arg id "$label_id" '[$id]')" "$remove" "$precondition" "$_GMAIL_EXECUTE" "$describe" "$_GMAIL_TARGETS_FILE"
)

_gmail_unlabel() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" labels label label_id label_name
    [ -n "$alias" ] || { _google_error "gmail unlabel requires ALIAS"; return 1; }
    shift || true
    _gmail_change_args unlabel "$@" || return 1
    [ -n "$_GMAIL_LABEL" ] || { _google_error "gmail unlabel requires --label"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    label="$(_gmail_resolve_user_label "$labels" "$_GMAIL_LABEL")" || return 1
    label_id="$(printf '%s' "$label" | jq -r '.id')"
    label_name="$(printf '%s' "$label" | jq -r '.name')"
    _gmail_change_run "$alias" unlabel '[]' "$(jq -cn --arg id "$label_id" '[$id]')" "" "$_GMAIL_EXECUTE" "remove label '$label_name'" "$_GMAIL_TARGETS_FILE"
)

# List Spam explicitly and rescue selected false positives back to Inbox; review frequency belongs to the caller.
_gmail_spam() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _google_error "gmail spam requires ALIAS"; return 1; }
    shift || true
    _gmail_list "$alias" --label SPAM "$@"
}

_gmail_not_spam() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}"
    [ -n "$alias" ] || { _google_error "gmail not-spam requires ALIAS"; return 1; }
    shift || true
    _gmail_change_args not-spam "$@" || return 1
    _gmail_change_run "$alias" not-spam '["INBOX"]' '["SPAM"]' in-spam "$_GMAIL_EXECUTE" "remove from Spam and return to Inbox (not spam)" "$_GMAIL_TARGETS_FILE"
)

_gmail_create_label() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" name="" execute=0 labels created ts
    [ -n "$alias" ] || { _google_error "gmail create-label requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --name) [ -n "${2:-}" ] || { _google_error "--name requires TEXT"; return 1; }; name="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _google_error "Unknown gmail create-label option: $1"; return 1 ;;
        esac
    done
    [ -n "$name" ] || { _google_error "gmail create-label requires --name (use Parent/Child to nest)"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    if printf '%s' "$labels" | jq -e --arg n "$name" 'any((.labels // [])[]; (.name | ascii_downcase) == ($n | ascii_downcase))' >/dev/null; then
        _google_error "A Gmail label named '$name' already exists"
        return 1
    fi
    _google_say "Gmail label create plan:"
    _google_say "Account: $alias"
    _google_say "New label: $name"
    if [ "$execute" -ne 1 ]; then _google_say "DRY RUN: no label was created. Re-run with --execute to create it."; return 0; fi
    _gmail_require_write "$alias" || return 1
    created="$(_gmail_send POST "$alias" "${_GMAIL_API}/labels" "$(jq -cn --arg name "$name" '{name: $name, labelListVisibility: "labelShow", messageListVisibility: "show"}')")" || return 1
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s' "$created" | jq -c --arg ts "$ts" --arg alias "$alias" '{ts: $ts, service: "gmail", alias: $alias, action: "create-label", label_id: .id, label: .name}' | _gmail_audit_append || _gmail_warn "Could not append to the mail audit log: $(_gmail_audit_log_path)"
    _google_say "Created label: $(printf '%s' "$created" | jq -r '.name + " | id: " + .id')"
)

_gmail_require_filters() {
    local alias="$1"
    if ! _google_account_value "$alias" '(.gmail.filters_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _google_error "Gmail filter changes are not enabled for alias '$alias'"
        _google_say "NEXT: set gmail.filters_enabled to true for '$alias' in $(_google_accounts_path), then run 'setup-google-services/scripts/authorize auth $alias' to grant gmail.settings.basic" >&2
        return 1
    fi
}

_gmail_filters_fetch() {
    _google_get_url "$1" "${_GMAIL_API}/settings/filters"
}

# Render FILTERS (the API's {filter: [...]}) with label IDs shown as names, using LABELS ({labels: [...]}).
_gmail_filters_human() {
    local filters="$1" labels="$2"
    jq -rn --argjson f "$filters" --argjson l "$labels" '
      ([($l.labels // [])[] | {key: .id, value: .name}] | from_entries) as $names |
      ($f.filter // [])[] |
      "- filter_id: " + .id +
      " | when: " + ([(.criteria // {}) | to_entries[] | .key + "=" + (.value | tostring)] | join(", ")) +
      " | then: " + ([
          ((.action.addLabelIds // [])[] | "label " + ($names[.] // .)),
          ((.action.removeLabelIds // [])[] | if . == "INBOX" then "skip inbox" else "remove " + ($names[.] // .) end),
          (if .action.forward then "forward " + .action.forward else empty end)
        ] | join(", "))
    '
}

_gmail_filters() {
    local alias="${1:-}" json_mode=0 filters labels
    [ -n "$alias" ] || { _google_error "gmail filters requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do case "$1" in --json) json_mode=1; shift ;; *) _google_error "Unknown gmail filters option: $1"; return 1 ;; esac; done
    _gmail_require_enabled "$alias" || return 1
    filters="$(_gmail_filters_fetch "$alias")" || return 1
    if [ "$json_mode" -eq 1 ]; then printf '%s\n' "$filters"; return 0; fi
    if [ "$(printf '%s' "$filters" | jq '(.filter // []) | length')" -eq 0 ]; then _google_say "No Gmail filters."; return 0; fi
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    _gmail_filters_human "$filters" "$labels"
}

# Build the Gmail search that matches the same mail as CRITERIA, so the dry run can show what the filter would have caught.
_gmail_filter_search() {
    printf '%s' "$1" | jq -r '[
        (if .from then "from:(" + .from + ")" else empty end),
        (if .to then "to:(" + .to + ")" else empty end),
        (if .subject then "subject:(" + .subject + ")" else empty end),
        (if .query then .query else empty end)
      ] | join(" ")'
}

_gmail_create_filter() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" from="" to="" subject="" query="" label_spec="" skip_inbox=0 execute=0
    local criteria action body labels label search created readback ok
    [ -n "$alias" ] || { _google_error "gmail create-filter requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --from) [ -n "${2:-}" ] || { _google_error "--from requires TEXT"; return 1; }; from="$2"; shift 2 ;;
            --to) [ -n "${2:-}" ] || { _google_error "--to requires TEXT"; return 1; }; to="$2"; shift 2 ;;
            --subject) [ -n "${2:-}" ] || { _google_error "--subject requires TEXT"; return 1; }; subject="$2"; shift 2 ;;
            --query) [ -n "${2:-}" ] || { _google_error "--query requires a Gmail search"; return 1; }; query="$2"; shift 2 ;;
            --label) [ -n "${2:-}" ] || { _google_error "--label requires NAME or ID"; return 1; }; label_spec="$2"; shift 2 ;;
            --skip-inbox) skip_inbox=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _google_error "Unknown gmail create-filter option: $1"; return 1 ;;
        esac
    done
    [ -n "$from$to$subject$query" ] || { _google_error "create-filter needs at least one of --from, --to, --subject, --query"; return 1; }
    [ -n "$label_spec" ] || [ "$skip_inbox" -eq 1 ] || { _google_error "create-filter needs --label, --skip-inbox, or both"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    criteria="$(jq -cn --arg from "$from" --arg to "$to" --arg subject "$subject" --arg query "$query" '{from: $from, to: $to, subject: $subject, query: $query} | with_entries(select(.value != ""))')"
    action='{}'
    if [ -n "$label_spec" ]; then
        labels="$(_gmail_labels_fetch "$alias")" || return 1
        label="$(_gmail_resolve_user_label "$labels" "$label_spec")" || return 1
        action="$(printf '%s' "$action" | jq -c --arg id "$(printf '%s' "$label" | jq -r '.id')" '. + {addLabelIds: [$id]}')"
    fi
    [ "$skip_inbox" -eq 1 ] && action="$(printf '%s' "$action" | jq -c '. + {removeLabelIds: ["INBOX"]}')"
    body="$(jq -cn --argjson c "$criteria" --argjson a "$action" '{criteria: $c, action: $a}')"
    search="$(_gmail_filter_search "$criteria")"
    _google_say "Gmail filter create plan:"
    _google_say "Account: $alias"
    _google_say "When: $(printf '%s' "$criteria" | jq -r 'to_entries | map(.key + "=" + .value) | join(", ")')"
    _google_say "Then: $([ -n "$label_spec" ] && printf 'label %s' "$(printf '%s' "$label" | jq -r '.name')")$([ -n "$label_spec" ] && [ "$skip_inbox" -eq 1 ] && printf ', ')$([ "$skip_inbox" -eq 1 ] && printf 'skip inbox')"
    _google_say "Applies to new mail only. Recent existing mail it would have matched (search: $search):"
    _gmail_list "$alias" --query "$search" --limit 5 || _gmail_warn "Could not run the preview search"
    if [ "$execute" -ne 1 ]; then _google_say "DRY RUN: no filter was created. Re-run with --execute to create it."; return 0; fi
    _gmail_require_filters "$alias" || return 1
    created="$(_gmail_send POST "$alias" "${_GMAIL_API}/settings/filters" "$body")" || { _google_say "NEXT: if the token predates gmail.filters_enabled, run 'setup-google-services/scripts/authorize auth $alias' to grant gmail.settings.basic" >&2; return 1; }
    readback="$(_google_get_url "$alias" "${_GMAIL_API}/settings/filters/$(_gmail_urlencode "$(printf '%s' "$created" | jq -r '.id')")")" || return 1
    ok="$(jq -n --argjson want "$body" --argjson got "$readback" '($got.criteria == $want.criteria) and (($got.action.addLabelIds // []) == ($want.action.addLabelIds // [])) and (($got.action.removeLabelIds // []) == ($want.action.removeLabelIds // []))')"
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --argjson f "$readback" --argjson ok "$ok" '{ts: $ts, service: "gmail", alias: $alias, action: "create-filter", filter_id: $f.id, criteria: $f.criteria, filter_action: $f.action, verified: $ok}' | _gmail_audit_append || _gmail_warn "Could not append to the mail audit log: $(_gmail_audit_log_path)"
    [ "$ok" = true ] || { _google_error "Created filter $(printf '%s' "$created" | jq -r '.id') but readback did not match"; return 1; }
    _google_say "Created filter (confirmed by readback): filter_id: $(printf '%s' "$created" | jq -r '.id')"
)

_gmail_delete_filter() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" filter_id="" execute=0 filter labels remaining
    [ -n "$alias" ] || { _google_error "gmail delete-filter requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --filter) [ -n "${2:-}" ] || { _google_error "--filter requires ID"; return 1; }; filter_id="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _google_error "Unknown gmail delete-filter option: $1"; return 1 ;;
        esac
    done
    [ -n "$filter_id" ] || { _google_error "delete-filter requires --filter ID"; return 1; }
    _gmail_require_enabled "$alias" || return 1
    filter="$(_google_get_url "$alias" "${_GMAIL_API}/settings/filters/$(_gmail_urlencode "$filter_id")")" || { _google_error "No Gmail filter with ID $filter_id"; return 1; }
    labels="$(_gmail_labels_fetch "$alias")" || return 1
    _google_say "Gmail filter delete plan (removes the rule only; no mail is touched):"
    _google_say "Account: $alias"
    _gmail_filters_human "$(printf '%s' "$filter" | jq -c '{filter: [.]}')" "$labels"
    if [ "$execute" -ne 1 ]; then _google_say "DRY RUN: the filter was not deleted. Re-run with --execute to delete it."; return 0; fi
    _gmail_require_filters "$alias" || return 1
    _gmail_send DELETE "$alias" "${_GMAIL_API}/settings/filters/$(_gmail_urlencode "$filter_id")" "" >/dev/null || return 1
    remaining="$(_gmail_filters_fetch "$alias")" || { _google_error 'Delete request succeeded but verification failed; inspect before retrying'; return 1; }
    printf '%s' "$remaining" | jq -e '(.error == null) and ((.filter // []) | type == "array")' >/dev/null || { _google_error 'Filter deletion readback was invalid'; return 1; }
    if printf '%s' "$remaining" | jq -e --arg id "$filter_id" 'any((.filter // [])[]; .id == $id)' >/dev/null; then _google_error "Filter $filter_id still exists after delete"; return 1; fi
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --argjson f "$filter" '{ts: $ts, service: "gmail", alias: $alias, action: "delete-filter", filter_id: $f.id, criteria: $f.criteria, filter_action: $f.action, verified: true}' | _gmail_audit_append || _gmail_warn "Could not append to the mail audit log: $(_gmail_audit_log_path)"
    _google_say "Deleted filter (confirmed): $filter_id"
)

