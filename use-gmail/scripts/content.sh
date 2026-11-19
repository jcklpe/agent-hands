#!/usr/bin/env bash
##- Exact-message attachment reads and preview-first drafts for manual sending.
_gmail_content_helper() { _google_python "$GOOGLE_GMAIL_DIR" "$GOOGLE_GMAIL_DIR/scripts/content.py" "$@"; }
_gmail_message_full() { _gmail_get "$1" "${_GMAIL_API}/messages/$(_gmail_urlencode "$2")" --data-urlencode 'format=full'; }

_gmail_attachments() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" message="" json_mode=0
    [ -n "$alias" ] || { _google_error 'attachments requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message) [ -n "${2:-}" ] || return 1; message="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _google_error 'Unknown attachments option'; return 1 ;;
        esac
    done
    [ -n "$message" ] || { _google_error 'Supply an exact --message ID'; return 1; }
    _gmail_require_enabled "$alias" || return 1
    _gmail_message_full "$alias" "$message" > "$GMAIL_WORK/message.json" || return 1
    _gmail_content_helper attachments "$GMAIL_WORK/message.json" "$message" > "$GMAIL_WORK/attachments.json" || return 1
    if [ "$json_mode" -eq 1 ]; then cat "$GMAIL_WORK/attachments.json"
    else jq -r '.[] | "- part: " + .partId + " | filename: " + (.filename | tojson) + " | type: " + .mimeType + " | bytes: " + (.size | tostring)' "$GMAIL_WORK/attachments.json"; fi
)

_gmail_download_attachment() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" message="" part="" out="" mode=create attachment_id
    [ -n "$alias" ] || { _google_error 'download-attachment requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message|--part|--output)
                [ -n "${2:-}" ] || { _google_error 'Missing attachment option value'; return 1; }
                case "$1" in --message) message="$2" ;; --part) part="$2" ;; --output) out="$2" ;; esac
                shift 2 ;;
            --overwrite) mode=replace; shift ;;
            *) _google_error 'Unknown download-attachment option'; return 1 ;;
        esac
    done
    [ -n "$message" ] && [ -n "$part" ] && [ -n "$out" ] || { _google_error 'Supply exact --message, --part and --output'; return 1; }
    [ ! -L "$out" ] || { _google_error 'Refusing a symlink output'; return 1; }
    if [ "$mode" = create ] && [ -e "$out" ]; then _google_error 'Output exists; choose another path or explicitly use --overwrite'; return 1; fi
    _gmail_require_enabled "$alias" || return 1
    _gmail_message_full "$alias" "$message" > "$GMAIL_WORK/message.json" || return 1
    _gmail_content_helper select "$GMAIL_WORK/message.json" "$message" "$part" > "$GMAIL_WORK/part.json" || return 1
    attachment_id="$(jq -r '.attachmentId // empty' "$GMAIL_WORK/part.json")"
    if [ -n "$attachment_id" ]; then
        _gmail_get "$alias" "${_GMAIL_API}/messages/$(_gmail_urlencode "$message")/attachments/$(_gmail_urlencode "$attachment_id")" > "$GMAIL_WORK/body.json" || return 1
    else jq '.body' "$GMAIL_WORK/part.json" > "$GMAIL_WORK/body.json"; fi
    _gmail_content_helper decode "$GMAIL_WORK/message.json" "$message" "$part" "$GMAIL_WORK/body.json" "$GMAIL_WORK/bytes" || return 1
    mkdir -p "$(dirname "$out")" || return 1
    _google_python "$GOOGLE_GMAIL_DIR" "$GOOGLE_AUTH_DIR/scripts/publish.py" "$GMAIL_WORK/bytes" "$out" "$mode" || return 1
    _google_say "Downloaded attachment to $out"
)

_gmail_create_draft() (
    set -o pipefail
    _gmail_work_begin || return 1
    local alias="${1:-}" execute=0 allow=0 reply="" sender profile draft_id thread_id link created_message requested_thread
    local args=()
    [ -n "$alias" ] || { _google_error 'create-draft requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --to|--cc|--bcc|--subject|--body-file|--attach)
                [ -n "${2:-}" ] || { _google_error 'Missing draft option value'; return 1; }
                args+=("$1" "$2"); shift 2 ;;
            --reply-to-message) [ -n "${2:-}" ] || return 1; reply="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --allow-draft-write) allow=1; shift ;;
            *) _google_error "Unknown create-draft option: $1"; return 1 ;;
        esac
    done
    _gmail_require_enabled "$alias" || return 1
    sender="$(_google_account_email "$alias")"
    if [ -n "$reply" ]; then
        _gmail_message_full "$alias" "$reply" > "$GMAIL_WORK/reply.json" || return 1
        args+=(--reply-source "$GMAIL_WORK/reply.json" --reply-message "$reply")
    fi
    _gmail_content_helper draft --sender "$sender" --request "$GMAIL_WORK/request.json" --expected "$GMAIL_WORK/expected.json" "${args[@]}" || return 1
    if [ "$execute" -eq 0 ]; then _google_say 'DRY RUN: no draft was created. Review the content, then use --execute --allow-draft-write for this account.'; return 0; fi
    [ "$allow" -eq 1 ] || { _google_error 'Draft creation requires the action-time opt-in --allow-draft-write; no account configuration or scopes were changed'; return 1; }
    profile="$(_gmail_get "$alias" "${_GMAIL_API}/profile")" || return 1
    printf '%s' "$profile" | jq -e --arg email "$sender" '(.emailAddress | ascii_downcase) == ($email | ascii_downcase)' >/dev/null || { _google_error 'Authenticated mailbox differs from the configured account email; no draft was created'; return 1; }
    if ! _gmail_send POST "$alias" "${_GMAIL_API}/drafts" "$(cat "$GMAIL_WORK/request.json")" > "$GMAIL_WORK/created.json"; then
        _google_error 'Draft creation failed or has an uncertain outcome. Inspect Drafts before retrying. Existing gmail.modify or gmail.compose is required; do not expand OAuth access without approval.'
        return 1
    fi
    draft_id="$(jq -r '.id // empty' "$GMAIL_WORK/created.json")"
    thread_id="$(jq -r '.message.threadId // empty' "$GMAIL_WORK/created.json")"
    created_message="$(jq -r '.message.id // empty' "$GMAIL_WORK/created.json")"
    [ -n "$draft_id" ] && [ -n "$thread_id" ] && [ -n "$created_message" ] || { _google_error 'Creation response is incomplete; a draft may exist. Inspect Drafts before retrying'; return 1; }
    link="https://mail.google.com/mail/u/?authuser=$(_gmail_urlencode "$sender")#drafts/$(_gmail_urlencode "$thread_id")"
    requested_thread="$(jq -r '.message.threadId // empty' "$GMAIL_WORK/request.json")"
    if [ -n "$requested_thread" ] && [ "$requested_thread" != "$thread_id" ]; then
        _google_error "Draft $draft_id was created but its returned thread differs from the reply target. Do not create it again; inspect Drafts for this account."
        return 1
    fi
    if ! _gmail_get "$alias" "${_GMAIL_API}/drafts/$(_gmail_urlencode "$draft_id")" --data-urlencode 'format=raw' > "$GMAIL_WORK/readback.json" || ! _gmail_content_helper verify-draft "$GMAIL_WORK/readback.json" "$GMAIL_WORK/expected.json" "$draft_id" "$created_message" "$thread_id"; then
        _google_error "Draft $draft_id was created but readback was not verified. Do not create it again; inspect $link"
        return 1
    fi
    jq -cn --arg account "$alias" --arg id "$draft_id" --arg message "$created_message" '{service:"gmail",action:"create-draft",account:$account,draft_id:$id,message_id:$message,verified:true}' | _gmail_audit_append || _gmail_warn 'Draft created, but private audit logging failed'
    _google_say "Created draft $draft_id; content confirmed by readback. No email was sent."
    _google_say "Review: $link"
    _google_say "Drafts folder: https://mail.google.com/mail/u/?authuser=$(_gmail_urlencode "$sender")#drafts"
)
