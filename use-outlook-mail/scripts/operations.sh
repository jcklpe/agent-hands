#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then _mail_source="${(%):-%x}"; else _mail_source="${BASH_SOURCE[0]}"; fi
OUTLOOK_MAIL_DIR="$(cd "$(dirname "$_mail_source")/.." && pwd)"
unset _mail_source
source "$OUTLOOK_MAIL_DIR/../authorize-microsoft/scripts/batch.sh"
_m365_mail_python() { _m365_python "$OUTLOOK_MAIL_DIR" "$@"; }
_m365_mail_render_helper() { _m365_mail_python "$OUTLOOK_MAIL_DIR/scripts/render.py" "$@"; }
_m365_mail_warn() { printf 'WARN: %s\n' "$*" >&2; }
_m365_mail_audit_path() { case "${M365_MAIL_AUDIT_LOG:-mail-writes.jsonl}" in /*) printf '%s\n' "$M365_MAIL_AUDIT_LOG" ;; *) printf '%s/%s\n' "$OUTLOOK_MAIL_DIR" "${M365_MAIL_AUDIT_LOG:-mail-writes.jsonl}" ;; esac; }
_m365_mail_audit_append() { _m365_mail_python "$M365_AUTH_DIR/scripts/audit.py" "$(_m365_mail_audit_path)"; }
_m365_mail_days_ago() { _m365_mail_python -c 'from datetime import datetime, timedelta, timezone; import sys; print((datetime.now(timezone.utc) - timedelta(days=int(sys.argv[1]))).replace(microsecond=0).isoformat().replace("+00:00", "Z"))' "$1"; }
_m365_mail_read_ids_file() {
    [ -f "$1" ] || { _m365_error "IDs file does not exist: $1"; return 1; }
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$line" in ''|\#*) continue ;; esac
        printf '%s\n' "$line"
    done < "$1"
}

_m365_mail_export() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" qa=0 custom_out="" out tmp json profile_email refreshed days max_results body_limit after dir
    [ -n "$alias" ] || { _m365_error "outlook-mail export requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output) [ -n "${2:-}" ] || { _m365_error "--output requires FILE"; return 1; }; custom_out="$2"; shift 2 ;;
            *) _m365_error "Unknown outlook-mail export option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" mail || return 1
    out="$custom_out"
    [ -n "$out" ] && [ -d "$(dirname "$out")" ] && [ ! -L "$out" ] || { _m365_error 'Choose --output FILE in an existing directory, not a symlink'; return 1; }
    tmp="$M365_WORK/export.md"
    json="$M365_WORK/mail.json"
    days="$(_m365_account_value "$alias" '.mail.days // 30')" || days=30
    max_results="$(_m365_account_value "$alias" '.mail.max_results // 150')" || max_results=150
    body_limit="$(_m365_account_value "$alias" '.mail.body_character_limit // 8000')" || body_limit=8000
    after="$(_m365_mail_days_ago "$days")" || return 1
    _m365_say "Syncing Microsoft 365 Inbox: $alias" >&2
    _m365_get_paginated "$alias" "$max_results" "$json" "$(_m365_graph_base "$alias")/me/mailFolders/inbox/messages" \
        --data-urlencode "\$top=${max_results}" \
        --data-urlencode "\$filter=receivedDateTime ge ${after}" \
        --data-urlencode "\$orderby=receivedDateTime desc" \
        --data-urlencode "\$select=id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments,isRead,importance,webLink,internetMessageHeaders,categories" \
        -H 'Prefer: outlook.body-content-type="text"' || return 1
    profile_email="$(_m365_profile_email "$alias")" || return 1
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    _m365_mail_render_helper mail --alias "$alias" --email "$profile_email" --refreshed "$refreshed" --days "$days" --max-results "$max_results" --body-limit "$body_limit" --input "$json" > "$tmp" || return 1
    _m365_mail_python "$M365_AUTH_DIR/scripts/publish.py" "$tmp" "$out" replace || return 1
    _m365_say "Updated $out"
)

##- Mail folders and moves. Reads (folders, list) need only mail.enabled; executed moves and folder creation also need mail.write_enabled, which switches the scope to Mail.ReadWrite.
##- Moves target exact Graph message IDs, go through Graph JSON batching (20 requests per call, because every PowerShell-transport call costs about two seconds), and are read back afterwards. There is no delete, and folders that amount to deletion or sending (Deleted Items, Junk, Drafts, Sent, Outbox, and anything under them) are never move targets.
_M365_MAIL_WELL_KNOWN='["inbox","archive","deleteditems","junkemail","drafts","sentitems","outbox","conversationhistory","recoverableitemsdeletions"]'
_M365_MAIL_BLOCKED_TARGETS='["deleteditems","junkemail","drafts","sentitems","outbox","recoverableitemsdeletions"]'
_M365_MAIL_FOLDER_SELECT='id,displayName,parentFolderId,childFolderCount,totalItemCount,unreadItemCount'

_m365_mail_require_write() {
    local alias="$1"
    if ! _m365_account_value "$alias" '(.mail.write_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _m365_error "Microsoft 365 mail moves are not enabled for alias '$alias'"
        _m365_say "NEXT: set mail.write_enabled to true for '$alias' in $(_m365_accounts_path), then run 'authorize auth $alias' so the session requests Mail.ReadWrite" >&2
        return 1
    fi
}

_m365_mail_move_cap() {
    _m365_account_value "$1" '.mail.max_moves_per_call // 50' 2>/dev/null || printf '50'
}

# _m365_batch ALIAS REQUESTS_FILE OUT_FILE: REQUESTS_FILE holds a JSON array of {method, url, body?} with URLs relative to the Graph version root. OUT_FILE receives the responses as an array in request order.

# Write the mailbox's folder tree to OUT as a JSON array of folders, each carrying path, depth, wellKnown (or null), and moveTarget.
_m365_mail_folder_tree() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" out="$2" dir depth=0
    dir="$(mktemp -d "$M365_WORK/folders.XXXXXX")" || return 1
    _m365_get_paginated "$alias" 1000 "${dir}/top.json" "$(_m365_graph_base "$alias")/me/mailFolders" \
        --data-urlencode "\$top=250" \
        --data-urlencode "\$select=${_M365_MAIL_FOLDER_SELECT}" || return 1
    jq -e '(.value | length) < 1000' "${dir}/top.json" >/dev/null || { _m365_error 'Mail folder count reached its bound; refusing an incomplete tree'; return 1; }
    jq '[(.value // [])[] | . + {path: .displayName, depth: 0}]' "${dir}/top.json" > "${dir}/all.json" || return 1
    cp "${dir}/all.json" "${dir}/level.json"
    while jq -e 'any(.[]; (.childFolderCount // 0) > 0)' "${dir}/level.json" >/dev/null; do
        depth=$((depth + 1))
        [ "$depth" -le 10 ] || { _m365_error "Mail folder tree is deeper than 10 levels; refusing to continue"; return 1; }
        jq '[.[] | select((.childFolderCount // 0) > 0)]' "${dir}/level.json" > "${dir}/parents.json" || return 1
        jq --arg select "$_M365_MAIL_FOLDER_SELECT" '[.[] | {method: "GET", url: ("/me/mailFolders/" + (.id | @uri) + "/childFolders?$top=250&$select=" + $select)}]' "${dir}/parents.json" > "${dir}/requests.json" || return 1
        _m365_batch "$alias" "${dir}/requests.json" "${dir}/responses.json" || return 1
        jq -n --slurpfile p "${dir}/parents.json" --slurpfile r "${dir}/responses.json" '
          [range(0; ($p[0] | length)) as $i |
            ($r[0][$i]) as $resp |
            if ($resp.status // 0) != 200 then
              error("Could not list child folders of " + $p[0][$i].path + ": " + (($resp.body.error.message // "HTTP " + (($resp.status // 0) | tostring))))
            elif ($resp.body."@odata.nextLink" // "") != "" then error("Incomplete child-folder list")
            else
              ($resp.body.value // [])[] | . + {path: ($p[0][$i].path + "/" + .displayName), depth: ($p[0][$i].depth + 1)}
            end]
        ' > "${dir}/level.json" || return 1
        jq -s '.[0] + .[1]' "${dir}/all.json" "${dir}/level.json" > "${dir}/merged.json" && mv "${dir}/merged.json" "${dir}/all.json"
    done
    jq -n --argjson names "$_M365_MAIL_WELL_KNOWN" '[$names[] | {method: "GET", url: ("/me/mailFolders/" + . + "?$select=id")}]' > "${dir}/wk-requests.json"
    _m365_batch "$alias" "${dir}/wk-requests.json" "${dir}/wk-responses.json" || return 1
    jq -e 'all(.[]; .status == 200 or .status == 404)' "${dir}/wk-responses.json" >/dev/null || { _m365_error 'Could not identify protected mail folders'; return 1; }
    jq --argjson names "$_M365_MAIL_WELL_KNOWN" --argjson blocked "$_M365_MAIL_BLOCKED_TARGETS" --slurpfile wk "${dir}/wk-responses.json" '
      ([range(0; ($names | length)) as $i | select(($wk[0][$i].status // 0) == 200) | {key: $wk[0][$i].body.id, value: $names[$i]}] | from_entries) as $map |
      (sort_by(.depth) | reduce .[] as $f ({out: [], blocked: {}};
        ($map[$f.id] // null) as $name |
        ((($name != null) and (($blocked | index($name)) != null)) or (.blocked[$f.parentFolderId // ""] // false)) as $isBlocked |
        .out += [$f + {wellKnown: $name, moveTarget: ($isBlocked | not)}] |
        if $isBlocked then .blocked[$f.id] = true else . end)) |
      .out | sort_by(.path | ascii_downcase)
    ' "${dir}/all.json" > "$out"
)

# Resolve SPEC against TREE_FILE and print the matching folder as JSON. SPEC may be a well-known name (inbox, archive, ...), an exact folder ID, a full path such as "Inbox/Receipts", or a unique display name. Ambiguity and absence both fail.
_m365_mail_resolve_folder() {
    local tree="$1" spec="$2" result
    result="$(jq --arg s "$spec" '
      ($s | ascii_downcase) as $l |
      ([.[] | select(.wellKnown == $l)]) as $wk |
      ([.[] | select(.id == $s)]) as $byId |
      ([.[] | select((.path | ascii_downcase) == $l)]) as $byPath |
      ([.[] | select((.displayName | ascii_downcase) == $l)]) as $byName |
      if ($wk | length) == 1 then {match: $wk[0]}
      elif ($byId | length) == 1 then {match: $byId[0]}
      elif ($byPath | length) == 1 then {match: $byPath[0]}
      elif ($byName | length) == 1 then {match: $byName[0]}
      elif ($byName | length) > 1 then {ambiguous: [$byName[] | .path]}
      else {missing: true} end
    ' "$tree")" || return 1
    if printf '%s' "$result" | jq -e '.match' >/dev/null; then
        printf '%s' "$result" | jq -c '.match'
    elif printf '%s' "$result" | jq -e '.ambiguous' >/dev/null; then
        _m365_error "Mail folder '$spec' matches more than one folder: $(printf '%s' "$result" | jq -r '.ambiguous | join(", ")'). Pass the full path or the folder ID."
        return 1
    else
        _m365_error "No mail folder matches '$spec'. Run 'outlook-mail folders ALIAS' to see folders, or 'outlook-mail create-folder' to make one."
        return 1
    fi
}

_m365_mail_folders() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" json_mode=0 tree
    [ -n "$alias" ] || { _m365_error "m365 mail folders requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 mail folders option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" mail || return 1
    tree="$(mktemp "$M365_WORK/folder-tree.XXXXXX")" || return 1
    _m365_mail_folder_tree "$alias" "$tree" || return 1
    if [ "$json_mode" -eq 1 ]; then
        cat "$tree"
    else
        jq -r '.[] |
          ("  " * .depth) + "- " + .displayName +
          " | path: " + .path +
          " | id: " + .id +
          " | total: " + ((.totalItemCount // 0) | tostring) +
          " | unread: " + ((.unreadItemCount // 0) | tostring) +
          (if .wellKnown then " | well-known: " + .wellKnown else "" end) +
          (if .moveTarget then "" else " | move target: no" end)
        ' "$tree"
    fi
)

_M365_MAIL_LIST_SELECT='id,conversationId,subject,from,receivedDateTime,isRead,hasAttachments,categories,webLink,parentFolderId'
_M365_MAIL_READ_SELECT='id,conversationId,subject,from,toRecipients,ccRecipients,bccRecipients,replyTo,receivedDateTime,sentDateTime,body,bodyPreview,hasAttachments,isRead,isDraft,importance,webLink,internetMessageHeaders,categories,parentFolderId'

# List the newest messages in one folder, or search with KQL (Graph $search) in one folder or across the mailbox. A mailbox-wide search leaves out Junk Email; pass --folder junkemail to search it.
_m365_mail_list() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" folder_spec="" search="" limit=25 json_mode=0 dir tree folder="null" folder_id url query junk_path
    [ -n "$alias" ] || { _m365_error "m365 mail list requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --folder) [ -n "${2:-}" ] || { _m365_error "--folder requires NAME, PATH, or ID"; return 1; }; folder_spec="$2"; shift 2 ;;
            --search) [ -n "${2:-}" ] || { _m365_error "--search requires a KQL query"; return 1; }; search="$2"; shift 2 ;;
            --limit) [ -n "${2:-}" ] || { _m365_error "--limit requires N"; return 1; }; limit="$2"; shift 2 ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 mail list option: $1"; return 1 ;;
        esac
    done
    [ -n "$folder_spec" ] || [ -n "$search" ] || { _m365_error "m365 mail list requires --folder, --search, or both"; return 1; }
    case "$limit" in ''|*[!0-9]*) _m365_error "--limit must be a positive integer"; return 1 ;; esac
    [ "$limit" -ge 1 ] && [ "$limit" -le 200 ] || { _m365_error "--limit must be between 1 and 200"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    dir="$(mktemp -d "$M365_WORK/mail-list.XXXXXX")" || return 1
    tree="${dir}/tree.json"
    _m365_mail_folder_tree "$alias" "$tree" || return 1
    if [ -n "$folder_spec" ]; then
        folder="$(_m365_mail_resolve_folder "$tree" "$folder_spec")" || return 1
        folder_id="$(printf '%s' "$folder" | jq -r '.id')"
        url="$(_m365_graph_base "$alias")/me/mailFolders/$(_m365_uri_encode "$folder_id")/messages"
    else
        url="$(_m365_graph_base "$alias")/me/messages"
    fi
    if [ -n "$search" ]; then
        # Graph wants the whole query in double quotes; quotes inside it are escaped. $search returns newest first and cannot be combined with $orderby.
        query="\"$(printf '%s' "$search" | sed 's/\\/\\\\/g; s/"/\\"/g')\""
        _m365_get_paginated "$alias" "$limit" "${dir}/messages.json" "$url" \
            --data-urlencode "\$search=${query}" \
            --data-urlencode "\$top=${limit}" \
            --data-urlencode "\$select=${_M365_MAIL_LIST_SELECT}" || return 1
    else
        _m365_get_paginated "$alias" "$limit" "${dir}/messages.json" "$url" \
            --data-urlencode "\$top=${limit}" \
            --data-urlencode "\$orderby=receivedDateTime desc" \
            --data-urlencode "\$select=${_M365_MAIL_LIST_SELECT}" || return 1
    fi
    # Name each message's folder by its path; a mailbox-wide search drops Junk Email and its subfolders.
    junk_path="$(jq -r '.[] | select(.wellKnown == "junkemail") | .path' "$tree")"
    jq --slurpfile tree "$tree" --argjson folder "$folder" --arg search "$search" --arg junk "$junk_path" '
      ($tree[0] | map({key: .id, value: .path}) | from_entries) as $paths |
      [(.value // [])[] | . + {folderPath: ($paths[.parentFolderId // ""] // "(folder not listed)")}] as $all |
      (if $folder == null and $junk != "" then [$all[] | select(.folderPath != $junk and (.folderPath | startswith($junk + "/") | not))] else $all end) as $kept |
      {folder: $folder, search: (if $search == "" then null else $search end), excludedJunk: (($all | length) - ($kept | length)), value: $kept}
    ' "${dir}/messages.json" > "${dir}/result.json" || return 1
    if [ "$json_mode" -eq 1 ]; then
        cat "${dir}/result.json"
    else
        jq -r '
          (.search != null) as $searching |
          (if .search == null then "Folder: " + .folder.path + " (" + ((.folder.totalItemCount // 0) | tostring) + " total)"
           else "Search: " + .search + " | " + (if .folder == null then "all folders except Junk Email" else "folder: " + .folder.path end) + " | " + ((.value | length) | tostring) + " found" +
             (if .excludedJunk > 0 then " (" + (.excludedJunk | tostring) + " more in Junk Email left out)" else "" end) end),
          (.value[] |
            "- " + (.receivedDateTime // "") +
            " | from: " + (.from.emailAddress.name // .from.emailAddress.address // "") +
            " <" + (.from.emailAddress.address // "") + ">" +
            " | " + (.subject // "(no subject)") +
            (if .isRead then "" else " | unread" end) +
            (if ((.categories // []) | length) > 0 then " | categories: " + (.categories | join(", ")) else "" end) +
            (if $searching then " | folder: " + .folderPath else "" end) +
            "\n  message_id: " + (.id // "") +
            (if .webLink then "\n  outlook: " + .webLink else "" end))
        ' "${dir}/result.json"
    fi
    rm -rf "$dir"
)

# Read one message by exact ID from any folder: headers, recipients, text body, attachment names, folder, and web link. Read-only; the body is capped at mail.body_character_limit unless --full.
_m365_mail_read() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" message_id="" json_mode=0 full=0 dir base folder_id body_limit
    [ -n "$alias" ] || { _m365_error "m365 mail read requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message) [ -n "${2:-}" ] || { _m365_error "--message requires ID"; return 1; }; message_id="$2"; shift 2 ;;
            --full) full=1; shift ;;
            --json) json_mode=1; shift ;;
            *) _m365_error "Unknown m365 mail read option: $1"; return 1 ;;
        esac
    done
    [ -n "$message_id" ] || { _m365_error "m365 mail read requires --message ID"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    dir="$(mktemp -d "$M365_WORK/mail-read.XXXXXX")" || return 1
    base="$(_m365_graph_base "$alias")"
    _m365_get "$alias" "${base}/me/messages/$(_m365_uri_encode "$message_id")" \
        --data-urlencode "\$select=${_M365_MAIL_READ_SELECT}" \
        --data-urlencode "\$expand=attachments(\$select=id,name,contentType,size,isInline)" \
        -H 'Prefer: outlook.body-content-type="text"' > "${dir}/message.json" || return 1
    if jq -e '(."attachments@odata.nextLink" // "") != ""' "${dir}/message.json" >/dev/null; then _m365_mail_warn 'Attachment names in this message read are incomplete'; fi
    # The folder name is a convenience; a failed lookup leaves it out rather than failing the read.
    folder_id="$(jq -r '.parentFolderId // empty' "${dir}/message.json")"
    if [ -z "$folder_id" ] || ! _m365_get "$alias" "${base}/me/mailFolders/$(_m365_uri_encode "$folder_id")" --data-urlencode "\$select=id,displayName" > "${dir}/folder.json" 2>/dev/null; then
        printf '{}\n' > "${dir}/folder.json"
    fi
    jq --slurpfile f "${dir}/folder.json" '. + {folder: ($f[0].displayName // null)}' "${dir}/message.json" > "${dir}/read.json" || return 1
    if [ "$json_mode" -eq 1 ]; then
        cat "${dir}/read.json"
    else
        body_limit=0
        [ "$full" -eq 1 ] || body_limit="$(_m365_account_value "$alias" '.mail.body_character_limit // 8000')" || body_limit=8000
        _m365_mail_render_helper message --body-limit "$body_limit" --input "${dir}/read.json" || return 1
    fi
    rm -rf "$dir"
)

# Shared engine for move, archive, and unarchive. REQUIRED_SOURCE is a folder spec every message must currently sit in, or empty for no source rule.
_m365_mail_move_run() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" action="$2" dest_spec="$3" required_source="$4" execute="$5"
    shift 5
    local ids=() id cap tree dir dest dest_id dest_path source source_id count failures ts
    for id in "$@"; do
        case " ${ids[*]:-} " in *" $id "*) continue ;; esac
        ids+=("$id")
    done
    [ "${#ids[@]}" -gt 0 ] || { _m365_error "m365 mail $action requires at least one --message ID or --ids-file"; return 1; }
    cap="$(_m365_mail_move_cap "$alias")"
    [ "${#ids[@]}" -le "$cap" ] || { _m365_error "m365 mail $action accepts at most $cap messages per call (got ${#ids[@]}); split the list"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    dir="$(mktemp -d "$M365_WORK/move.XXXXXX")" || return 1
    tree="${dir}/tree.json"
    _m365_mail_folder_tree "$alias" "$tree" || return 1
    dest="$(_m365_mail_resolve_folder "$tree" "$dest_spec")" || return 1
    dest_id="$(printf '%s' "$dest" | jq -r '.id')"
    dest_path="$(printf '%s' "$dest" | jq -r '.path')"
    if ! printf '%s' "$dest" | jq -e '.moveTarget' >/dev/null; then
        _m365_error "Refusing to move mail into '$dest_path': Deleted Items, Junk, Drafts, Sent, Outbox, and their subfolders are never move targets"
        return 1
    fi
    source_id=""
    if [ -n "$required_source" ]; then
        source="$(_m365_mail_resolve_folder "$tree" "$required_source")" || return 1
        source_id="$(printf '%s' "$source" | jq -r '.id')"
    fi
    printf '%s\n' "${ids[@]}" | jq -R . | jq -s '[.[] | {method: "GET", url: ("/me/messages/" + (. | @uri) + "?$select=id,subject,from,receivedDateTime,parentFolderId")}]' > "${dir}/get-requests.json"
    _m365_batch "$alias" "${dir}/get-requests.json" "${dir}/get-responses.json" || return 1
    printf '%s\n' "${ids[@]}" | jq -R . | jq -s --slurpfile r "${dir}/get-responses.json" --slurpfile tree "$tree" '
      ($tree[0] | map({key: .id, value: .path}) | from_entries) as $paths |
      [range(0; length) as $i | {requested: .[$i], status: ($r[0][$i].status // 0), message: $r[0][$i].body} |
        . + {folderPath: ($paths[.message.parentFolderId // ""] // "(folder not listed)")}]
    ' > "${dir}/targets.json" || return 1
    if jq -e 'any(.[]; .status != 200)' "${dir}/targets.json" >/dev/null; then
        _m365_error "These message IDs were not found; nothing was moved:"
        jq -r '.[] | select(.status != 200) | "  - " + .requested + " (" + (.message.error.code // ("HTTP " + (.status | tostring))) + ")"' "${dir}/targets.json" >&2
        return 1
    fi
    if [ -n "$source_id" ] && jq -e --arg src "$source_id" 'any(.[]; .message.parentFolderId != $src)' "${dir}/targets.json" >/dev/null; then
        _m365_error "m365 mail $action only moves messages that are currently in '$(printf '%s' "$source" | jq -r '.path')'; nothing was moved. Out of place:"
        jq -r --arg src "$source_id" '.[] | select(.message.parentFolderId != $src) | "  - " + (.message.subject // "(no subject)") + " | in: " + .folderPath + " | " + .requested' "${dir}/targets.json" >&2
        return 1
    fi
    if jq -e --arg dest "$dest_id" 'any(.[]; .message.parentFolderId == $dest)' "${dir}/targets.json" >/dev/null; then
        _m365_error "Some messages are already in '$dest_path'; nothing was moved. Remove them from the list:"
        jq -r --arg dest "$dest_id" '.[] | select(.message.parentFolderId == $dest) | "  - " + (.message.subject // "(no subject)") + " | " + .requested' "${dir}/targets.json" >&2
        return 1
    fi
    count="${#ids[@]}"
    _m365_say "Microsoft 365 mail $action plan:"
    _m365_say "Account: $alias"
    _m365_say "Destination: $dest_path"
    _m365_say "Messages: $count"
    jq -r '.[] | "- " + (.message.receivedDateTime // "") + " | " + (.message.from.emailAddress.address // "") + " | " + (.message.subject // "(no subject)") + " | from folder: " + .folderPath' "${dir}/targets.json"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was moved. Re-run with --execute to move these messages."; return 0; fi
    _m365_mail_require_write "$alias" || return 1
    jq --arg dest "$dest_id" '[.[] | {method: "POST", url: ("/me/messages/" + (.requested | @uri) + "/move"), body: {destinationId: $dest}}]' "${dir}/targets.json" > "${dir}/move-requests.json"
    _m365_batch "$alias" "${dir}/move-requests.json" "${dir}/move-responses.json" || return 1
    # Read back each moved message under its new ID, since a Graph move returns the message with a different ID.
    jq '[.[] | select((.status // 0) == 201 or (.status // 0) == 200) | {method: "GET", url: ("/me/messages/" + (.body.id | @uri) + "?$select=id,parentFolderId")}]' "${dir}/move-responses.json" > "${dir}/readback-requests.json"
    _m365_batch "$alias" "${dir}/readback-requests.json" "${dir}/readback-responses.json" || return 1
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    jq -n --slurpfile t "${dir}/targets.json" --slurpfile m "${dir}/move-responses.json" --slurpfile rb "${dir}/readback-responses.json" --arg dest "$dest_id" '
      ([$rb[0][] | select((.status // 0) == 200) | {key: .body.id, value: .body.parentFolderId}] | from_entries) as $now |
      [range(0; ($t[0] | length)) as $i | $t[0][$i] as $target | $m[0][$i] as $resp |
        (($resp.status // 0) == 201 or ($resp.status // 0) == 200) as $moved |
        {requested: $target.requested, subject: ($target.message.subject // ""), from: ($target.message.from.emailAddress.address // ""), fromFolder: $target.folderPath,
         newId: (if $moved then $resp.body.id else null end),
         verified: ($moved and ($now[$resp.body.id] // "") == $dest),
         error: (if $moved then null else ($resp.body.error.message // ("HTTP " + (($resp.status // 0) | tostring))) end)}]
    ' > "${dir}/results.json" || return 1
    jq -c --arg ts "$ts" --arg alias "$alias" --arg action "$action" --arg dest "$dest_path" '.[] | {ts: $ts, service: "m365", alias: $alias, action: $action, message_id: .requested, new_message_id: .newId, destination: $dest, from_folder: .fromFolder, sender: .from, subject: .subject, verified: .verified, error: .error}' "${dir}/results.json" | _m365_mail_audit_append || _m365_mail_warn "Could not append to the mail audit log: $(_m365_mail_audit_path)"
    jq -r '.[] | if .verified then "- moved: " + .subject + "\n  new message_id: " + .newId elif .newId then "- MOVED BUT NOT CONFIRMED in destination: " + .subject + "\n  new message_id: " + .newId else "- FAILED: " + .subject + " | " + .error + "\n  message_id: " + .requested end' "${dir}/results.json"
    failures="$(jq '[.[] | select(.verified | not)] | length' "${dir}/results.json")"
    if [ "$failures" -gt 0 ]; then
        _m365_error "$failures of $count messages were not confirmed in '$dest_path'"
        return 1
    fi
    _m365_say "Moved $count messages to $dest_path (confirmed by readback). Moved messages have new IDs, shown above."
)

_m365_mail_move_args() {
    # Parses the shared move options into _MOVE_IDS, _MOVE_FOLDER, and _MOVE_EXECUTE.
    local command="$1"
    shift
    _MOVE_IDS=()
    _MOVE_FOLDER=""
    _MOVE_EXECUTE=0
    local line
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message) [ -n "${2:-}" ] || { _m365_error "--message requires ID"; return 1; }; _MOVE_IDS+=("$2"); shift 2 ;;
            --ids-file)
                [ -n "${2:-}" ] || { _m365_error "--ids-file requires FILE"; return 1; }
                _m365_mail_read_ids_file "$2" > /dev/null || return 1
                while IFS= read -r line; do [ -n "$line" ] && _MOVE_IDS+=("$line"); done <<EOF
$(_m365_mail_read_ids_file "$2")
EOF
                shift 2
                ;;
            --folder)
                [ "$command" = "move" ] || { _m365_error "m365 mail $command does not take --folder"; return 1; }
                [ -n "${2:-}" ] || { _m365_error "--folder requires NAME, PATH, or ID"; return 1; }
                _MOVE_FOLDER="$2"; shift 2
                ;;
            --execute) _MOVE_EXECUTE=1; shift ;;
            --dry-run) _MOVE_EXECUTE=0; shift ;;
            *) _m365_error "Unknown m365 mail $command option: $1"; return 1 ;;
        esac
    done
}

_m365_mail_move() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _m365_error "m365 mail move requires ALIAS"; return 1; }
    shift || true
    _m365_mail_move_args move "$@" || return 1
    [ -n "$_MOVE_FOLDER" ] || { _m365_error "m365 mail move requires --folder"; return 1; }
    _m365_mail_move_run "$alias" move "$_MOVE_FOLDER" "" "$_MOVE_EXECUTE" ${_MOVE_IDS[@]+"${_MOVE_IDS[@]}"}
}

_m365_mail_archive() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _m365_error "m365 mail archive requires ALIAS"; return 1; }
    shift || true
    _m365_mail_move_args archive "$@" || return 1
    _m365_mail_move_run "$alias" archive archive inbox "$_MOVE_EXECUTE" ${_MOVE_IDS[@]+"${_MOVE_IDS[@]}"}
}

_m365_mail_unarchive() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _m365_error "m365 mail unarchive requires ALIAS"; return 1; }
    shift || true
    _m365_mail_move_args unarchive "$@" || return 1
    _m365_mail_move_run "$alias" unarchive inbox archive "$_MOVE_EXECUTE" ${_MOVE_IDS[@]+"${_MOVE_IDS[@]}"}
}

# List a message's attachments, or save its file attachments into an existing directory. Read-only (Mail.Read); refuses to overwrite unless --force.
_m365_mail_attachments() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" message_id="" save_dir="" force=0 base list dir id name out
    [ -n "$alias" ] || { _m365_error "m365 mail attachments requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --message) [ -n "${2:-}" ] || { _m365_error "--message requires ID"; return 1; }; message_id="$2"; shift 2 ;;
            --save) [ -n "${2:-}" ] || { _m365_error "--save requires DIR"; return 1; }; save_dir="$2"; shift 2 ;;
            --force) force=1; shift ;;
            *) _m365_error "Unknown m365 mail attachments option: $1"; return 1 ;;
        esac
    done
    [ -n "$message_id" ] || { _m365_error "m365 mail attachments requires --message ID"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    base="$(_m365_graph_base "$alias")/me/messages/$(_m365_uri_encode "$message_id")/attachments"
    list="$(_m365_get "$alias" "$base" --data-urlencode "\$select=id,name,contentType,size,isInline")" || return 1
    printf '%s' "$list" | jq -e '(.value | type == "array") and ((."@odata.nextLink" // "") == "")' >/dev/null || { _m365_error 'Incomplete attachment list'; return 1; }
    if [ -z "$save_dir" ]; then
        printf '%s' "$list" | jq -r '(.value // [])[] | "- " + .name + " | " + (.contentType // "") + " | " + ((.size // 0) | tostring) + " bytes" + (if .isInline then " | inline" else "" end) + " | type: " + ((."@odata.type" // "") | sub("#microsoft.graph."; ""))'
        return 0
    fi
    dir="$M365_WORK/attachments"
    mkdir "$dir" || return 1
    printf '%s' "$list" > "$dir/list.json"
    _m365_mail_python "$OUTLOOK_MAIL_DIR/scripts/attachments.py" plan "$dir/list.json" "$save_dir" "$force" > "$dir/plan.json" || return 1
    local index=0
    while IFS= read -r id; do
        [ -n "$id" ] || continue
        _m365_get "$alias" "${base}/$(_m365_uri_encode "$id")" > "$dir/$index.json" || return 1
        index=$((index + 1))
    done <<EOF2
$(jq -r '.[].id' "$dir/plan.json")
EOF2
    _m365_mail_python "$OUTLOOK_MAIL_DIR/scripts/attachments.py" save "$dir/plan.json" "$dir" "$save_dir" "$force" || return 1
    rm -rf "$dir"
    printf '%s' "$list" | jq -r '(.value // [])[] | select((."@odata.type" // "") != "#microsoft.graph.fileAttachment" or .isInline) | "Skipped (inline or not a file): " + .name'
)

##- Outlook categories: the Microsoft 365 counterpart of Gmail's user labels, used for subject-matter tags during triage. A category name is free text on the message; it does not need to exist in the mailbox's master category list (it then shows without a color). Same gates as moves: dry run by default, mail.write_enabled to execute, exact IDs, per-call cap, batched, read back, and audit-logged.
_m365_mail_category_run() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" action="$2" category="$3" execute="$4"
    shift 4
    local ids=() id cap dir count failures ts
    for id in "$@"; do
        case " ${ids[*]:-} " in *" $id "*) continue ;; esac
        ids+=("$id")
    done
    [ -n "$category" ] || { _m365_error "m365 mail $action requires --category NAME"; return 1; }
    case "$category" in *,*) _m365_error "Category names may not contain commas"; return 1 ;; esac
    [ "${#ids[@]}" -gt 0 ] || { _m365_error "m365 mail $action requires at least one --message ID or --ids-file"; return 1; }
    cap="$(_m365_mail_move_cap "$alias")"
    [ "${#ids[@]}" -le "$cap" ] || { _m365_error "m365 mail $action accepts at most $cap messages per call (got ${#ids[@]}); split the list"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    dir="$(mktemp -d "$M365_WORK/category.XXXXXX")" || return 1
    printf '%s\n' "${ids[@]}" | jq -R . | jq -s '[.[] | {method: "GET", url: ("/me/messages/" + (. | @uri) + "?$select=id,subject,from,receivedDateTime,categories")}]' > "${dir}/get-requests.json"
    _m365_batch "$alias" "${dir}/get-requests.json" "${dir}/get-responses.json" || return 1
    printf '%s\n' "${ids[@]}" | jq -R . | jq -s --slurpfile r "${dir}/get-responses.json" '[range(0; length) as $i | {requested: .[$i], status: ($r[0][$i].status // 0), message: $r[0][$i].body}]' > "${dir}/targets.json" || return 1
    if jq -e 'any(.[]; .status != 200)' "${dir}/targets.json" >/dev/null; then
        _m365_error "These message IDs were not found; nothing was changed:"
        jq -r '.[] | select(.status != 200) | "  - " + .requested + " (" + (.message.error.code // ("HTTP " + (.status | tostring))) + ")"' "${dir}/targets.json" >&2
        return 1
    fi
    # Compute each message's new category list; categories are compared case-insensitively, as Outlook does.
    jq --arg c "$category" --arg action "$action" '[.[] |
        (.message.categories // []) as $now |
        (($now | map(ascii_downcase)) | index($c | ascii_downcase)) as $has |
        . + {current: $now,
             wanted: (if $action == "categorize" then (if $has then $now else $now + [$c] end) else [$now[] | select(ascii_downcase != ($c | ascii_downcase))] end),
             noop: (if $action == "categorize" then ($has != null) else ($has == null) end)}]' "${dir}/targets.json" > "${dir}/plan.json" || return 1
    if jq -e 'any(.[]; .noop)' "${dir}/plan.json" >/dev/null; then
        _m365_error "Some messages already $( [ "$action" = categorize ] && echo have || echo lack ) category '$category'; nothing was changed. Remove them from the list:"
        jq -r '.[] | select(.noop) | "  - " + (.message.subject // "(no subject)") + " | " + .requested' "${dir}/plan.json" >&2
        return 1
    fi
    count="${#ids[@]}"
    _m365_say "Microsoft 365 mail $action plan:"
    _m365_say "Account: $alias"
    _m365_say "Category: $category ($( [ "$action" = categorize ] && echo add || echo remove ))"
    _m365_say "Messages: $count"
    jq -r '.[] | "- " + (.message.receivedDateTime // "") + " | " + (.message.from.emailAddress.address // "") + " | " + (.message.subject // "(no subject)") + " | categories now: " + ((.current | join(", ")) // "") ' "${dir}/plan.json"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was changed. Re-run with --execute to apply."; return 0; fi
    _m365_mail_require_write "$alias" || return 1
    jq '[.[] | {method: "PATCH", url: ("/me/messages/" + (.requested | @uri)), body: {categories: .wanted}}]' "${dir}/plan.json" > "${dir}/patch-requests.json"
    _m365_batch "$alias" "${dir}/patch-requests.json" "${dir}/patch-responses.json" || return 1
    jq '[.[] | {method: "GET", url: ("/me/messages/" + (.requested | @uri) + "?$select=id,categories")}]' "${dir}/plan.json" > "${dir}/readback-requests.json"
    _m365_batch "$alias" "${dir}/readback-requests.json" "${dir}/readback-responses.json" || return 1
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    jq -n --slurpfile p "${dir}/plan.json" --slurpfile w "${dir}/patch-responses.json" --slurpfile rb "${dir}/readback-responses.json" '
      [range(0; ($p[0] | length)) as $i | $p[0][$i] as $t |
        ((($w[0][$i].status // 0) / 100 | floor) == 2) as $patched |
        ($rb[0][$i].body.categories // null) as $after |
        {requested: $t.requested, subject: ($t.message.subject // ""), from: ($t.message.from.emailAddress.address // ""),
         verified: ($patched and $after != null and (($after | map(ascii_downcase) | sort) == ($t.wanted | map(ascii_downcase) | sort))),
         error: (if $patched then null else ($w[0][$i].body.error.message // ("HTTP " + (($w[0][$i].status // 0) | tostring))) end)}]
    ' > "${dir}/results.json" || return 1
    jq -c --arg ts "$ts" --arg alias "$alias" --arg action "$action" --arg category "$category" '.[] | {ts: $ts, service: "m365", alias: $alias, action: $action, category: $category, message_id: .requested, sender: .from, subject: .subject, verified: .verified, error: .error}' "${dir}/results.json" | _m365_mail_audit_append || _m365_mail_warn "Could not append to the mail audit log: $(_m365_mail_audit_path)"
    jq -r '.[] | (if .verified then "- done: " else "- NOT CONFIRMED: " end) + .subject + (if .error then " | " + .error else "" end)' "${dir}/results.json"
    failures="$(jq '[.[] | select(.verified | not)] | length' "${dir}/results.json")"
    if [ "$failures" -gt 0 ]; then
        _m365_error "$failures of $count messages were not confirmed by readback"
        return 1
    fi
    _m365_say "Applied to $count messages (confirmed by readback). Message IDs are unchanged."
)

_m365_mail_category_cmd() {
    local action="$1" alias="${2:-}" category="" line
    local ids=()
    [ -n "$alias" ] || { _m365_error "m365 mail $action requires ALIAS"; return 1; }
    shift 2 || true
    local execute=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --category) [ -n "${2:-}" ] || { _m365_error "--category requires NAME"; return 1; }; category="$2"; shift 2 ;;
            --message) [ -n "${2:-}" ] || { _m365_error "--message requires ID"; return 1; }; ids+=("$2"); shift 2 ;;
            --ids-file)
                [ -n "${2:-}" ] || { _m365_error "--ids-file requires FILE"; return 1; }
                _m365_mail_read_ids_file "$2" > /dev/null || return 1
                while IFS= read -r line; do [ -n "$line" ] && ids+=("$line"); done <<EOF
$(_m365_mail_read_ids_file "$2")
EOF
                shift 2
                ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 mail $action option: $1"; return 1 ;;
        esac
    done
    _m365_mail_category_run "$alias" "$action" "$category" "$execute" ${ids[@]+"${ids[@]}"}
}

# Junk review: list Junk Email and rescue false positives to the Inbox. Junk is never part of mail sync, and Junk stays refused as a move destination.
_m365_mail_junk() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _m365_error "m365 mail junk requires ALIAS"; return 1; }
    shift || true
    _m365_mail_list "$alias" --folder junkemail "$@"
}

_m365_mail_not_junk() {
    local alias="${1:-}"
    [ -n "$alias" ] || { _m365_error "m365 mail not-junk requires ALIAS"; return 1; }
    shift || true
    _m365_mail_move_args not-junk "$@" || return 1
    _m365_mail_move_run "$alias" not-junk inbox junkemail "$_MOVE_EXECUTE" ${_MOVE_IDS[@]+"${_MOVE_IDS[@]}"}
}

_m365_mail_create_folder() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" name="" parent_spec="" execute=0 tree parent parent_id parent_path url created new_path ts
    [ -n "$alias" ] || { _m365_error "m365 mail create-folder requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --name) [ -n "${2:-}" ] || { _m365_error "--name requires TEXT"; return 1; }; name="$2"; shift 2 ;;
            --parent) [ -n "${2:-}" ] || { _m365_error "--parent requires NAME, PATH, or ID"; return 1; }; parent_spec="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 mail create-folder option: $1"; return 1 ;;
        esac
    done
    [ -n "$name" ] || { _m365_error "m365 mail create-folder requires --name"; return 1; }
    case "$name" in */*) _m365_error "Folder names may not contain '/'; use --parent to nest"; return 1 ;; esac
    _m365_require_enabled "$alias" mail || return 1
    tree="$(mktemp "$M365_WORK/folder-tree.XXXXXX")" || return 1
    _m365_mail_folder_tree "$alias" "$tree" || return 1
    parent_id=""
    parent_path=""
    if [ -n "$parent_spec" ]; then
        parent="$(_m365_mail_resolve_folder "$tree" "$parent_spec")" || return 1
        parent_id="$(printf '%s' "$parent" | jq -r '.id')"
        parent_path="$(printf '%s' "$parent" | jq -r '.path')"
        printf '%s' "$parent" | jq -e '.moveTarget' >/dev/null || { _m365_error "Refusing to create a folder under '$parent_path'"; return 1; }
        new_path="${parent_path}/${name}"
    else
        new_path="$name"
    fi
    if jq -e --arg p "$new_path" 'any(.[]; (.path | ascii_downcase) == ($p | ascii_downcase))' "$tree" >/dev/null; then
        _m365_error "A mail folder already exists at '$new_path'"
        return 1
    fi
    _m365_say "Microsoft 365 mail folder create plan:"
    _m365_say "Account: $alias"
    _m365_say "New folder: $new_path"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no folder was created. Re-run with --execute to create it."; return 0; fi
    _m365_mail_require_write "$alias" || return 1
    if [ -n "$parent_id" ]; then
        url="$(_m365_graph_base "$alias")/me/mailFolders/$(_m365_uri_encode "$parent_id")/childFolders"
    else
        url="$(_m365_graph_base "$alias")/me/mailFolders"
    fi
    created="$(_m365_write POST "$alias" "$url" "$(jq -cn --arg name "$name" '{displayName: $name}')")" || return 1
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s' "$created" | jq -c --arg ts "$ts" --arg alias "$alias" --arg path "$new_path" '{ts: $ts, service: "m365", alias: $alias, action: "create-folder", folder_id: .id, folder: $path}' | _m365_mail_audit_append || _m365_mail_warn "Could not append to the mail audit log: $(_m365_mail_audit_path)"
    _m365_say "Created folder: $new_path | id: $(printf '%s' "$created" | jq -r '.id // "(unknown)"')"
)

_m365_mail_require_rules() {
    local alias="$1"
    if ! _m365_account_value "$alias" '(.mail.rules_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _m365_error "Microsoft 365 Inbox rule changes are not enabled for alias '$alias'"
        _m365_say "NEXT: set mail.rules_enabled to true for '$alias' in $(_m365_accounts_path), then run 'authorize auth $alias' so the session requests MailboxSettings.ReadWrite" >&2
        return 1
    fi
}

_m365_mail_rules_url() {
    printf '%s/me/mailFolders/inbox/messageRules\n' "$(_m365_graph_base "$1")"
}

_m365_mail_rules_collection() {
    local rules
    rules="$(_m365_get "$1" "$(_m365_mail_rules_url "$1")")" || return 1
    printf '%s' "$rules" | jq -e '(.value | type == "array") and ((."@odata.nextLink" // "") == "")' >/dev/null || { _m365_error 'Incomplete Inbox rule list; refusing to guess'; return 1; }
    printf '%s\n' "$rules"
}

# Render RULES ({value: [...]}) with folder IDs shown as paths, using TREE (from _m365_mail_folder_tree) when given.
_m365_mail_rules_human() {
    local rules="$1" tree="${2:-[]}"
    jq -rn --argjson r "$rules" --argjson t "$tree" '
      ([$t[] | {key: .id, value: .path}] | from_entries) as $paths |
      ($r.value // []) | sort_by(.sequence // 0)[] |
      "- " + (.displayName // "(unnamed rule)") + " | rule_id: " + .id + " | " + (if .isEnabled then "enabled" else "disabled" end) +
      " | when: " + ([(.conditions // {}) | to_entries[] | select(.value != null and .value != [] and .value != false) |
          .key + "=" + (if (.value | type) == "array" then (.value | map(if type == "object" then (.emailAddress.address // tostring) else tostring end) | join("|")) else (.value | tostring) end)] | join(", ")) +
      " | then: " + ([(.actions // {}) | to_entries[] | select(.value != null and .value != [] and .value != false) |
          if .key == "moveToFolder" then "move to " + ($paths[.value] // .value)
          elif .key == "assignCategories" then "category " + (.value | join(", "))
          else .key + "=" + (.value | tostring) end] | join(", "))
    '
}

_m365_mail_rules() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" json_mode=0 rules dir
    [ -n "$alias" ] || { _m365_error "m365 mail rules requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do case "$1" in --json) json_mode=1; shift ;; *) _m365_error "Unknown m365 mail rules option: $1"; return 1 ;; esac; done
    _m365_require_enabled "$alias" mail || return 1
    rules="$(_m365_mail_rules_collection "$alias")" || return 1
    if [ "$json_mode" -eq 1 ]; then printf '%s\n' "$rules"; return 0; fi
    if [ "$(printf '%s' "$rules" | jq '(.value // []) | length')" -eq 0 ]; then _m365_say "No Inbox rules."; return 0; fi
    dir="$(mktemp -d "$M365_WORK/rules.XXXXXX")" || return 1
    _m365_mail_folder_tree "$alias" "${dir}/tree.json" || printf '[]' > "${dir}/tree.json"
    _m365_mail_rules_human "$rules" "$(cat "${dir}/tree.json")"
)

_m365_mail_create_rule() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" name="" category="" folder_spec="" stop=0 delete=0 execute=0 dir folder="" existing sequence conditions actions body created readback ok
    local froms=() senders=() subjects=() recipients=()
    [ -n "$alias" ] || { _m365_error "m365 mail create-rule requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --name) [ -n "${2:-}" ] || { _m365_error "--name requires TEXT"; return 1; }; name="$2"; shift 2 ;;
            --from) [ -n "${2:-}" ] || { _m365_error "--from requires ADDRESS"; return 1; }; froms+=("$2"); shift 2 ;;
            --sender-contains) [ -n "${2:-}" ] || { _m365_error "--sender-contains requires TEXT"; return 1; }; senders+=("$2"); shift 2 ;;
            --subject-contains) [ -n "${2:-}" ] || { _m365_error "--subject-contains requires TEXT"; return 1; }; subjects+=("$2"); shift 2 ;;
            --recipient-contains) [ -n "${2:-}" ] || { _m365_error "--recipient-contains requires TEXT"; return 1; }; recipients+=("$2"); shift 2 ;;
            --category) [ -n "${2:-}" ] || { _m365_error "--category requires NAME"; return 1; }; category="$2"; shift 2 ;;
            --folder) [ -n "${2:-}" ] || { _m365_error "--folder requires NAME, PATH, or ID"; return 1; }; folder_spec="$2"; shift 2 ;;
            --delete) delete=1; shift ;;
            --stop) stop=1; shift ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 mail create-rule option: $1"; return 1 ;;
        esac
    done
    [ -n "$name" ] || { _m365_error "create-rule requires --name"; return 1; }
    [ "${#froms[@]}" -gt 0 ] || [ "${#senders[@]}" -gt 0 ] || [ "${#subjects[@]}" -gt 0 ] || [ "${#recipients[@]}" -gt 0 ] || { _m365_error "create-rule needs at least one --from, --sender-contains, --subject-contains, or --recipient-contains"; return 1; }
    [ -n "$category" ] || [ -n "$folder_spec" ] || [ "$delete" -eq 1 ] || { _m365_error "create-rule needs --category, --folder, or --delete"; return 1; }
    if [ "$delete" -eq 1 ]; then
        [ "${#froms[@]}" -gt 0 ] && [ "${#recipients[@]}" -gt 0 ] || { _m365_error "--delete requires both --from ADDRESS and --recipient-contains ADDRESS to scope duplicate-mail cleanup"; return 1; }
        [ -z "$category$folder_spec" ] || { _m365_error "--delete cannot be combined with --category or --folder"; return 1; }
        local address
        for address in "${froms[@]}" "${recipients[@]}"; do
            if ! printf '%s\n' "$address" | LC_ALL=C grep -Eq '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$'; then _m365_error "--delete requires complete sender and recipient email addresses, not fragments"; return 1; fi
        done
    fi
    case "$category" in *,*) _m365_error "Category names may not contain commas"; return 1 ;; esac
    _m365_require_enabled "$alias" mail || return 1
    dir="$(mktemp -d "$M365_WORK/create-rule.XXXXXX")" || return 1
    if [ -n "$folder_spec" ]; then
        _m365_mail_folder_tree "$alias" "${dir}/tree.json" || return 1
        folder="$(_m365_mail_resolve_folder "${dir}/tree.json" "$folder_spec")" || return 1
        if [ "$(printf '%s' "$folder" | jq -r '.moveTarget')" != true ]; then _m365_error "Rules may not move mail into $(printf '%s' "$folder" | jq -r '.path')"; return 1; fi
    else
        printf '[]' > "${dir}/tree.json"
    fi
    existing="$(_m365_mail_rules_collection "$alias")" || return 1
    if printf '%s' "$existing" | jq -e --arg n "$name" 'any((.value // [])[]; (.displayName // "" | ascii_downcase) == ($n | ascii_downcase))' >/dev/null; then _m365_error "An Inbox rule named '$name' already exists"; return 1; fi
    sequence="$(printf '%s' "$existing" | jq '([(.value // [])[].sequence // 0] | max // 0) + 1')"
    conditions="$(jq -cn \
        --argjson froms "$(printf '%s\n' "${froms[@]+"${froms[@]}"}" | jq -R . | jq -sc 'map(select(. != ""))')" \
        --argjson senders "$(printf '%s\n' "${senders[@]+"${senders[@]}"}" | jq -R . | jq -sc 'map(select(. != ""))')" \
        --argjson subjects "$(printf '%s\n' "${subjects[@]+"${subjects[@]}"}" | jq -R . | jq -sc 'map(select(. != ""))')" \
        --argjson recipients "$(printf '%s\n' "${recipients[@]+"${recipients[@]}"}" | jq -R . | jq -sc 'map(select(. != ""))')" \
        '{} + (if ($froms | length) > 0 then {fromAddresses: [$froms[] | {emailAddress: {address: .}}]} else {} end)
            + (if ($senders | length) > 0 then {senderContains: $senders} else {} end)
            + (if ($subjects | length) > 0 then {subjectContains: $subjects} else {} end)
            + (if ($recipients | length) > 0 then {recipientContains: $recipients} else {} end)')"
    actions="$(jq -cn --arg c "$category" --arg f "$(printf '%s' "$folder" | jq -r '.id // empty' 2>/dev/null)" --argjson stop "$stop" --argjson delete "$delete" \
        '{} + (if $c != "" then {assignCategories: [$c]} else {} end) + (if $f != "" then {moveToFolder: $f} else {} end) + (if $stop == 1 then {stopProcessingRules: true} else {} end) + (if $delete == 1 then {delete: true} else {} end)')"
    body="$(jq -cn --arg n "$name" --argjson s "$sequence" --argjson c "$conditions" --argjson a "$actions" '{displayName: $n, sequence: $s, isEnabled: true, conditions: $c, actions: $a}')"
    _m365_say "Microsoft 365 Inbox rule create plan:"
    _m365_say "Account: $alias"
    _m365_mail_rules_human "$(jq -cn --argjson b "$body" '{value: [$b + {id: "(new)"}]}')" "$(cat "${dir}/tree.json")"
    _m365_say "Different condition types must all match; values within one type are alternatives."
    [ "$delete" -ne 1 ] || _m365_say "Delete means move to Outlook Deleted Items, not permanent deletion."
    _m365_say "Applies to new mail arriving in the Inbox only; existing mail is unchanged."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no rule was created. Re-run with --execute to create it."; return 0; fi
    _m365_mail_require_rules "$alias" || return 1
    created="$(_m365_write POST "$alias" "$(_m365_mail_rules_url "$alias")" "$body")" || return 1
    readback="$(_m365_get "$alias" "$(_m365_mail_rules_url "$alias")/$(_m365_uri_encode "$(printf '%s' "$created" | jq -r '.id')")")" || return 1
    ok="$(jq -n --argjson want "$body" --argjson got "$readback" '
      def meaningful: with_entries(select(.value != null and .value != [] and .value != false and .value != {}));
      def predicates: (. // {}) | del(."@odata.type") | meaningful | with_entries(
        if (.value | type) == "array" then .value |= (map(if type == "object" and has("emailAddress") then {emailAddress: {address: (.emailAddress.address | ascii_downcase)}} elif type == "string" then ascii_downcase else . end) | sort) else . end);
      def rule_actions: (. // {}) | del(."@odata.type") | meaningful | with_entries(if (.value | type) == "array" then .value |= sort else . end);
      ($got.displayName == $want.displayName) and ($got.isEnabled == true) and (($got.hasError // false) == false) and
      ($got.sequence == $want.sequence) and
      (($got.conditions | predicates) == ($want.conditions | predicates)) and
      (($got.exceptions | predicates) == {}) and
      (($got.actions | rule_actions) == ($want.actions | rule_actions))')"
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --argjson r "$readback" --argjson ok "$ok" '{ts: $ts, service: "m365", alias: $alias, action: "create-rule", rule_id: $r.id, rule: $r.displayName, conditions: $r.conditions, rule_actions: $r.actions, verified: $ok}' | _m365_mail_audit_append || _m365_mail_warn "Could not append to the mail audit log: $(_m365_mail_audit_path)"
    [ "$ok" = true ] || { _m365_error "Created rule but readback did not match"; return 1; }
    _m365_say "Created rule (confirmed by readback): $name | rule_id: $(printf '%s' "$created" | jq -r '.id')"
)

_m365_mail_delete_rule() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="${1:-}" rule_id="" execute=0 rule url
    [ -n "$alias" ] || { _m365_error "m365 mail delete-rule requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --rule) [ -n "${2:-}" ] || { _m365_error "--rule requires ID"; return 1; }; rule_id="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown m365 mail delete-rule option: $1"; return 1 ;;
        esac
    done
    [ -n "$rule_id" ] || { _m365_error "delete-rule requires --rule ID"; return 1; }
    _m365_require_enabled "$alias" mail || return 1
    url="$(_m365_mail_rules_url "$alias")/$(_m365_uri_encode "$rule_id")"
    rule="$(_m365_get "$alias" "$url")" || { _m365_error "No Inbox rule with ID $rule_id"; return 1; }
    _m365_say "Microsoft 365 Inbox rule delete plan (removes the rule only; no mail is touched):"
    _m365_say "Account: $alias"
    _m365_mail_rules_human "$(printf '%s' "$rule" | jq -c '{value: [.]}')"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: the rule was not deleted. Re-run with --execute to delete it."; return 0; fi
    _m365_mail_require_rules "$alias" || return 1
    _m365_write DELETE "$alias" "$url" "" >/dev/null || return 1
    local remaining
    remaining="$(_m365_mail_rules_collection "$alias")" || { _m365_error 'Rule deletion could not be verified; inspect before retrying'; return 1; }
    if printf '%s' "$remaining" | jq -e --arg id "$rule_id" 'any(.value[]; .id == $id)' >/dev/null; then _m365_error "Rule $rule_id still exists after delete"; return 1; fi
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --argjson r "$rule" '{ts: $ts, service: "m365", alias: $alias, action: "delete-rule", rule_id: $r.id, rule: $r.displayName, conditions: $r.conditions, rule_actions: $r.actions, verified: true}' | _m365_mail_audit_append || _m365_mail_warn "Could not append to the mail audit log: $(_m365_mail_audit_path)"
    _m365_say "Deleted rule (confirmed): $rule_id"
)

_m365_mail_dispatch() {
    local command="${1:-}"
    shift || true
    case "$command" in
        export) _m365_mail_export "$@" ;;
        folders) _m365_mail_folders "$@" ;;
        list) _m365_mail_list "$@" ;;
        read) _m365_mail_read "$@" ;;
        attachments) _m365_mail_attachments "$@" ;;
        move) _m365_mail_move "$@" ;;
        archive) _m365_mail_archive "$@" ;;
        unarchive) _m365_mail_unarchive "$@" ;;
        not-junk) _m365_mail_not_junk "$@" ;;
        junk) _m365_mail_junk "$@" ;;
        create-folder) _m365_mail_create_folder "$@" ;;
        rules) _m365_mail_rules "$@" ;;
        create-rule) _m365_mail_create_rule "$@" ;;
        delete-rule) _m365_mail_delete_rule "$@" ;;
        categorize|uncategorize) _m365_mail_category_cmd "$command" "$@" ;;
        *) _m365_error "Unknown Outlook Mail command: $command"; return 1 ;;
    esac
}
