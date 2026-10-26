#!/usr/bin/env bash
##- Portable Google Drive operations; Google authorization is the only runtime skill dependency.
GOOGLE_DRIVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_drive_warn() { printf 'WARN: %s\n' "$*" >&2; }
_drive_urlencode() { jq -rn --arg value "$1" '$value | @uri'; }
_drive_work_begin() {
    DRIVE_WORK="$(mktemp -d "${TMPDIR:-/tmp}/google-drive.XXXXXX")" || return 1
    trap 'rm -rf "$DRIVE_WORK"' EXIT
    trap 'exit 130' HUP INT TERM
}
_drive_publish() { _google_python "$GOOGLE_DRIVE_DIR" "$GOOGLE_AUTH_DIR/scripts/publish.py" "$@"; }

_drive_accounts() {
    _google_accounts_ready || return 1
    jq -r '
      (.accounts // [])[] |
      select((.drive.enabled // false) == true) |
      "- " + (.alias // "missing-alias") + " | email: " + (.email // "")
    ' "$(_google_accounts_path)"
}

_drive_page_size() {
    local alias="$1"
    _google_account_value "$alias" '.drive.search_page_size // 20' 2>/dev/null || printf '20'
}

_drive_read_limit() {
    local alias="$1"
    _google_account_value "$alias" '.drive.read_character_limit // 20000' 2>/dev/null || printf '20000'
}

_drive_sheet_row_limit() {
    local alias="$1"
    _google_account_value "$alias" '.drive.sheet_row_limit // 200' 2>/dev/null || printf '200'
}

_drive_write_enabled() {
    local alias="$1"
    _google_account_value "$alias" '(.drive.write_enabled // false) == true' 2>/dev/null | grep -qx true
}

# Rename has its own opt-in because it needs metadata access to files this app did not create, which drive.write_enabled (drive.file) never granted.
_drive_rename_enabled() {
    local alias="$1"
    _google_account_value "$alias" '(.drive.enabled // false) == true and (.drive.rename_enabled // false) == true' 2>/dev/null | grep -qx true
}

_drive_query_escape() {
    printf '%s' "$1" | sed "s/\\\\/\\\\\\\\/g; s/'/\\\\'/g"
}

_drive_file_id() {
    local reference="$1"
    case "$reference" in
        https://drive.google.com/file/d/*|https://docs.google.com/document/d/*|https://docs.google.com/spreadsheets/d/*|https://docs.google.com/presentation/d/*) reference="${reference#*/d/}"; reference="${reference%%/*}"; reference="${reference%%\?*}" ;;
        https://drive.google.com/open\?id=*) reference="${reference#*id=}"; reference="${reference%%&*}" ;;
        https://drive.google.com/drive/folders/*|https://drive.google.com/drive/u/*/folders/*) reference="${reference#*/folders/}"; reference="${reference%%[/?]*}" ;;
    esac
    printf '%s' "$reference" | grep -Eq '^[A-Za-z0-9_-]+$' || { _google_error 'Expected a Google file URL or ID'; return 1; }
    printf '%s\n' "$reference"
}

_drive_files_human() {
    jq -r '
      (.files // [])[] |
      "- " + (.name // "Untitled") +
      " | id: " + (.id // "") +
      " | type: " + (.mimeType // "") +
      " | modified: " + (.modifiedTime // "") +
      " | owner: " + (((.owners // []) | map(.emailAddress // .displayName // "") | map(select(. != "")) | join(", "))) +
      " | " + (.webViewLink // "")
    '
}

_drive_meta_human() {
    jq -r '
      "Name: " + (.name // "Untitled") + "\n" +
      "ID: " + (.id // "") + "\n" +
      "MIME type: " + (.mimeType // "") + "\n" +
      "Modified: " + (.modifiedTime // "") + "\n" +
      "Owners: " + (((.owners // []) | map(.emailAddress // .displayName // "") | map(select(. != "")) | join(", "))) + "\n" +
      "Parents: " + (((.parents // []) | join(", "))) + "\n" +
      "Drive ID: " + (.driveId // "") + "\n" +
      "URL: " + (.webViewLink // "")
    '
}

_drive_fetch_meta() {
    local alias="$1"
    local file_id="$2"
    _google_get_url "$alias" "https://www.googleapis.com/drive/v3/files/${file_id}" \
        --data-urlencode "supportsAllDrives=true" \
        --data-urlencode "fields=id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),parents,driveId,size"
}

_drive_search() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" query="${2:-}" json=0 page_size escaped q
    local result_file
    [ -n "$alias" ] || { _google_error "drive search requires ALIAS"; return 1; }
    [ -n "$query" ] || { _google_error "drive search requires QUERY"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json=1; shift ;;
            *) _google_error "Unknown drive search option: $1"; return 1 ;;
        esac
    done
    page_size="$(_drive_page_size "$alias")"
    escaped="$(_drive_query_escape "$query")"
    q="trashed = false and (name contains '${escaped}' or fullText contains '${escaped}')"
    result_file="$(mktemp "$DRIVE_WORK/google-drive-search.XXXXXX")" || return 1
    _google_get_url "$alias" "https://www.googleapis.com/drive/v3/files" \
        --data-urlencode "q=${q}" \
        --data-urlencode "pageSize=${page_size}" \
        --data-urlencode "supportsAllDrives=true" \
        --data-urlencode "includeItemsFromAllDrives=true" \
        --data-urlencode "fields=files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),parents,driveId),nextPageToken" > "$result_file" || return 1

    if [ "$json" -eq 1 ]; then
        cat "$result_file"
    else
        _drive_files_human < "$result_file" || return 1
        if jq -e '.nextPageToken != null' "$result_file" >/dev/null; then _drive_warn "More results exist; this is one bounded page. --json includes the continuation token."; fi
    fi
)

_drive_list() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" folder_id="${2:-}" json=0 q
    local result_file
    [ -n "$alias" ] || { _google_error "drive list requires ALIAS"; return 1; }
    [ -n "$folder_id" ] || { _google_error "drive list requires FOLDER_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json=1; shift ;;
            *) _google_error "Unknown drive list option: $1"; return 1 ;;
        esac
    done
    q="'$(_drive_query_escape "$folder_id")' in parents and trashed = false"
    result_file="$(mktemp "$DRIVE_WORK/google-drive-list.XXXXXX")" || return 1
    _google_get_url "$alias" "https://www.googleapis.com/drive/v3/files" \
        --data-urlencode "q=${q}" \
        --data-urlencode "pageSize=$(_drive_page_size "$alias")" \
        --data-urlencode "supportsAllDrives=true" \
        --data-urlencode "includeItemsFromAllDrives=true" \
        --data-urlencode "fields=files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),parents,driveId),nextPageToken" > "$result_file" || return 1

    if [ "$json" -eq 1 ]; then
        cat "$result_file"
    else
        _drive_files_human < "$result_file" || return 1
        if jq -e '.nextPageToken != null' "$result_file" >/dev/null; then _drive_warn "More results exist; this is one bounded page. --json includes the continuation token."; fi
    fi
)

_drive_meta() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" ref="${2:-}" json=0 file_id
    [ -n "$alias" ] || { _google_error "drive meta requires ALIAS"; return 1; }
    [ -n "$ref" ] || { _google_error "drive meta requires FILE_URL_OR_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json=1; shift ;;
            *) _google_error "Unknown drive meta option: $1"; return 1 ;;
        esac
    done
    file_id="$(_drive_file_id "$ref")" || return 1
    if [ "$json" -eq 1 ]; then
        _drive_fetch_meta "$alias" "$file_id"
    else
        _drive_fetch_meta "$alias" "$file_id" | _drive_meta_human
    fi
)

_drive_quote_sheet_name() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
}

_drive_text_cap_file() {
    _google_python "$GOOGLE_DRIVE_DIR" -c 'import sys
limit = int(sys.argv[1])
data = sys.stdin.read()
if len(data) <= limit:
    print(data, end="")
else:
    print(data[:limit].rstrip(), end="")
    print("\n\n[content truncated]")' "$1"
}

_drive_read() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" ref="${2:-}" range="" file_id meta_file mime name limit content_file
    local sheet_meta_file values_file sheet_title escaped_title encoded_range
    [ -n "$alias" ] || { _google_error "drive read requires ALIAS"; return 1; }
    [ -n "$ref" ] || { _google_error "drive read requires FILE_URL_OR_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --range) [ -n "${2:-}" ] || { _google_error "--range requires RANGE"; return 1; }; range="$2"; shift 2 ;;
            *) _google_error "Unknown drive read option: $1"; return 1 ;;
        esac
    done

    file_id="$(_drive_file_id "$ref")" || return 1
    meta_file="$(mktemp "$DRIVE_WORK/google-drive-meta.XXXXXX")" || return 1
    _drive_fetch_meta "$alias" "$file_id" > "$meta_file" || return 1
    mime="$(jq -r '.mimeType // ""' "$meta_file")"
    name="$(jq -r '.name // "Untitled"' "$meta_file")"

    case "$mime" in
        application/vnd.google-apps.document)
            content_file="$(mktemp "$DRIVE_WORK/google-drive-doc.XXXXXX")" || return 1
            _google_get_url "$alias" "https://www.googleapis.com/drive/v3/files/${file_id}/export" \
                --data-urlencode "mimeType=text/plain" > "$content_file" || return 1
            limit="$(_drive_read_limit "$alias")"
            printf '# Google Doc - %s\n\n' "$name"
            printf 'Account alias: `%s`\n\n' "$alias"
            printf 'File ID: `%s`\n\n' "$file_id"
            _drive_text_cap_file "$limit" < "$content_file"
            ;;
        application/vnd.google-apps.spreadsheet)
            sheet_meta_file="$(mktemp "$DRIVE_WORK/google-sheet-meta.XXXXXX")" || return 1
            values_file="$(mktemp "$DRIVE_WORK/google-sheet-values.XXXXXX")" || return 1
            _google_get_url "$alias" "https://sheets.googleapis.com/v4/spreadsheets/${file_id}" \
                --data-urlencode "fields=properties(title),sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))" > "$sheet_meta_file" || return 1
            if [ -z "$range" ]; then
                sheet_title="$(jq -r '.sheets[0].properties.title // "Sheet1"' "$sheet_meta_file")"
                escaped_title="$(_drive_quote_sheet_name "$sheet_title")"
                range="${escaped_title}!A1:Z$(_drive_sheet_row_limit "$alias")"
            fi
            encoded_range="$(_drive_urlencode "$range")" || return 1
            _google_get_url "$alias" "https://sheets.googleapis.com/v4/spreadsheets/${file_id}/values/${encoded_range}" > "$values_file" || return 1
            _google_python "$GOOGLE_DRIVE_DIR" "$GOOGLE_AUTH_DIR/scripts/sheets_render.py" "$alias" "$file_id" "$sheet_meta_file" "$values_file"
            ;;
        *)
            _drive_warn "Drive read supports Google Docs and Google Sheets for now. Showing metadata only."
            _drive_meta_human < "$meta_file"
            ;;
    esac
)

_drive_export_default_mime() {
    # native google mimeType -> default export mimeType (space) extension
    case "$1" in
        application/vnd.google-apps.document) printf 'application/pdf pdf' ;;
        application/vnd.google-apps.spreadsheet) printf 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet xlsx' ;;
        application/vnd.google-apps.presentation) printf 'application/pdf pdf' ;;
        application/vnd.google-apps.drawing) printf 'image/png png' ;;
        *) printf '' ;;
    esac
}

_drive_ext_for_mime() {
    case "$1" in
        application/pdf) printf 'pdf' ;;
        application/vnd.openxmlformats-officedocument.wordprocessingml.document) printf 'docx' ;;
        application/vnd.openxmlformats-officedocument.spreadsheetml.sheet) printf 'xlsx' ;;
        application/vnd.openxmlformats-officedocument.presentationml.presentation) printf 'pptx' ;;
        application/msword) printf 'doc' ;;
        application/vnd.ms-excel) printf 'xls' ;;
        text/plain) printf 'txt' ;;
        text/html) printf 'html' ;;
        text/csv) printf 'csv' ;;
        image/png) printf 'png' ;;
        image/jpeg) printf 'jpg' ;;
        image/gif) printf 'gif' ;;
        application/vnd.oasis.opendocument.text) printf 'odt' ;;
        application/zip) printf 'zip' ;;
        *) printf '' ;;
    esac
}

# drive download ALIAS FILE_URL_OR_ID [--out PATH] [--mime EXPORT_MIME] [--force]
# Binary files download byte-for-byte via alt=media; native Google files export
# (Doc->PDF, Sheet->XLSX, Slides->PDF, Drawing->PNG by default, override with --mime).
_drive_download() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" ref="${2:-}" out="" export_mime="" force=0
    local file_id meta_file mime name is_native default_pair token url target dest_dir ext
    [ -n "$alias" ] || { _google_error "drive download requires ALIAS"; return 1; }
    [ -n "$ref" ] || { _google_error "drive download requires FILE_URL_OR_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --out) [ -n "${2:-}" ] || { _google_error "--out requires PATH"; return 1; }; out="$2"; shift 2 ;;
            --mime) [ -n "${2:-}" ] || { _google_error "--mime requires EXPORT_MIME"; return 1; }; export_mime="$2"; shift 2 ;;
            --force) force=1; shift ;;
            *) _google_error "Unknown drive download option: $1"; return 1 ;;
        esac
    done

    file_id="$(_drive_file_id "$ref")" || return 1
    meta_file="$(mktemp "$DRIVE_WORK/google-drive-dl-meta.XXXXXX")" || return 1
    _drive_fetch_meta "$alias" "$file_id" > "$meta_file" || return 1
    mime="$(jq -r '.mimeType // ""' "$meta_file")"
    name="$(jq -r '.name // "download"' "$meta_file")"

    case "$mime" in
        application/vnd.google-apps.*) is_native=1 ;;
        *) is_native=0 ;;
    esac

    if [ "$is_native" -eq 1 ]; then
        if [ -z "$export_mime" ]; then
            default_pair="$(_drive_export_default_mime "$mime")"
            [ -n "$default_pair" ] || { _google_error "No default export format for Google type '$mime'. Pass --mime EXPORT_MIME."; return 1; }
            export_mime="${default_pair%% *}"
        fi
        ext="$(_drive_ext_for_mime "$export_mime")"
    else
        ext="$(_drive_ext_for_mime "$mime")"
    fi

    if [ -z "$out" ] || [ -d "$out" ]; then
        case "$name" in ''|.|..|*/*|*\\*) _google_error 'Remote filename is unsafe locally; supply --out with an explicit filename'; return 1 ;; esac
    fi
    if [ -z "$out" ]; then
        target="./$name"
    elif [ -d "$out" ]; then
        target="${out%/}/$name"
    else
        target="$out"
    fi
    # Native exports carry the resulting format's extension when the target lacks it.
    if [ "$is_native" -eq 1 ] && [ -n "$ext" ]; then
        case "$target" in
            *.$ext) : ;;
            *) target="${target}.${ext}" ;;
        esac
    fi

    if [ -e "$target" ] && [ "$force" -ne 1 ]; then
        _google_error "Refusing to overwrite existing file: $target (use --force)"; return 1
    fi
    dest_dir="$(dirname "$target")"
    [ -d "$dest_dir" ] || { _google_error "Destination directory does not exist: $dest_dir"; return 1; }

    token="$(_google_access_token "$alias")" || return 1
    if [ "$is_native" -eq 1 ]; then
        url="https://www.googleapis.com/drive/v3/files/${file_id}/export?mimeType=$(_drive_urlencode "$export_mime")&supportsAllDrives=true"
    else
        url="https://www.googleapis.com/drive/v3/files/${file_id}?alt=media&supportsAllDrives=true"
    fi

    if ! curl -fsSL -o "$DRIVE_WORK/download" "$url" -H "Authorization: Bearer ${token}"; then
        _google_error "Download failed (no access, or export unsupported for this type: $mime)"
        return 1
    fi
    if [ "$force" -eq 1 ]; then _drive_publish "$DRIVE_WORK/download" "$target" replace || return 1
    else _drive_publish "$DRIVE_WORK/download" "$target" create || return 1
    fi

    _google_say "Downloaded: $target"
    _google_say "Source: $name ($mime)"
    if [ "$is_native" -eq 1 ]; then
        _google_say "Exported as: $export_mime"
    fi
)

# Bounded metadata export; destination and exclusions are caller choices.
_drive_days_ago() {
    _google_python "$GOOGLE_DRIVE_DIR" -c 'from datetime import datetime, timedelta, timezone; import sys; print((datetime.now(timezone.utc) - timedelta(days=int(sys.argv[1]))).replace(microsecond=0).isoformat().replace("+00:00", "Z"))' "$1"
}

_drive_sync_excludes() {
    local alias="$1"
    _google_account_value "$alias" '(.drive.index_exclude | if . == null then [] else . end) | if type == "array" and all(.[]; type == "string" and length > 0 and (test("[\r\n]") | not)) then join("\n") else error("index_exclude must be an array of nonempty single-line names") end'
}

_drive_render_index() {
    _google_python "$GOOGLE_DRIVE_DIR" "$GOOGLE_DRIVE_DIR/scripts/render_index.py" "$@"
}

_drive_export_index() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" out="" max_folders=25 children=12 max_recent=30 recent_days=45 value extra_excludes=""
    [ -n "$alias" ] || { _google_error 'export-index requires ALIAS'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --exclude-folder)
                [ -n "${2:-}" ] || { _google_error '--exclude-folder requires NAME'; return 1; }
                case "$2" in *$'\n'*|*$'\r'*) _google_error 'Excluded names must be single-line'; return 1 ;; esac
                extra_excludes="${extra_excludes}${2}"$'\n'
                shift 2 ;;
            --output|--folders|--recent|--recent-days)
                [ -n "${2:-}" ] || { _google_error 'Missing export option value'; return 1; }
                case "$1" in
                    --output) out="$2" ;;
                    --folders) max_folders="$2" ;;
                    --recent) max_recent="$2" ;;
                    --recent-days) recent_days="$2" ;;
                esac
                shift 2 ;;
            *) _google_error 'Unknown export-index option'; return 1 ;;
        esac
    done
    [ -n "$out" ] || { _google_error 'export-index requires --output FILE'; return 1; }
    for value in "$max_folders" "$recent_days"; do
        printf '%s' "$value" | grep -Eq '^[1-9][0-9]{0,3}$' || { _google_error 'Export bounds must be positive integers below 10000'; return 1; }
    done
    printf '%s' "$max_recent" | grep -Eq '^(0|[1-9][0-9]{0,3})$' || { _google_error 'Recent bound must be zero or a positive integer below 10000'; return 1; }
    [ "$max_folders" -le 1000 ] && [ "$max_recent" -le 1000 ] || { _google_error 'Drive page bounds cannot exceed 1000'; return 1; }
    local email excludes folders_json recent_json enriched='[]' skipped='[]' row fid fname kids kid_count since payload result
    _google_account_exists "$alias" || { _google_error 'Unknown Google account'; return 1; }
    email="$(_google_account_email "$alias")"
    excludes="$(_drive_sync_excludes "$alias")" || { _google_error 'Cannot read configured folder exclusions'; return 1; }
    excludes="${excludes}"$'\n'"${extra_excludes}"
    folders_json="$(_drive_index_list "$alias" "'root' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false" name "$max_folders")" || return 1
    printf '%s' "$folders_json" | jq -c '.files[]' > "$DRIVE_WORK/folders.jsonl" || return 1
    while IFS= read -r row; do
        fid="$(printf '%s' "$row" | jq -er '.id')" || return 1
        fname="$(printf '%s' "$row" | jq -er '.name')" || return 1
        if printf '%s\n' "$excludes" | grep -qxF -- "$fname"; then
            skipped="$(printf '%s' "$skipped" | jq --arg name "$fname" '. + [$name]')" || return 1
            continue
        fi
        kids="$(_drive_index_list "$alias" "'$(_drive_query_escape "$fid")' in parents and trashed=false" 'folder,modifiedTime desc' "$((children + 1))")" || return 1
        kid_count="$(printf '%s' "$kids" | jq '.files | length')" || return 1
        enriched="$(printf '%s' "$enriched" | jq -c --argjson folder "$row" --argjson response "$kids" --argjson count "$kid_count" --argjson cap "$children" '. + [$folder + {children: ($response.files[0:$cap]), child_count: $count, child_truncated: ($count > $cap or ($response.nextPageToken != null))}]')" || return 1
    done < "$DRIVE_WORK/folders.jsonl"
    recent_json='{"files":[]}'
    if [ "$max_recent" -gt 0 ]; then
        since="$(_drive_days_ago "$recent_days")" || return 1
        recent_json="$(_drive_index_list "$alias" "modifiedTime > '${since}' and trashed=false and mimeType != 'application/vnd.google-apps.folder'" 'modifiedTime desc' "$max_recent")" || return 1
    fi
    payload="$(jq -n --arg alias "$alias" --arg email "$email" --argjson folders "$enriched" --argjson recent "$recent_json" --argjson skipped "$skipped" --argjson first "$folders_json" --argjson mf "$max_folders" --argjson cpf "$children" --argjson mr "$max_recent" --argjson rd "$recent_days" '{alias:$alias, email:$email, folders:$folders, recent:$recent.files, recent_enabled:($mr > 0), skipped:$skipped, folders_truncated:($first.nextPageToken != null), recent_truncated:($recent.nextPageToken != null), caps:{max_folders:$mf,children_per_folder:$cpf,max_recent:$mr,recent_days:$rd}}')" || return 1
    result="$DRIVE_WORK/index.md"
    printf '%s' "$payload" | _drive_render_index > "$result" || return 1
    mkdir -p "$(dirname "$out")" || return 1
    _drive_publish "$result" "$out" replace || return 1
    _google_say "Updated $out"
)

_drive_index_list() {
    local alias="$1" query="$2" order="$3" size="$4" response
    response="$(_google_get_url "$alias" 'https://www.googleapis.com/drive/v3/files' --data-urlencode "q=$query" --data-urlencode 'fields=files(id,name,mimeType,modifiedTime,webViewLink),nextPageToken' --data-urlencode "orderBy=$order" --data-urlencode "pageSize=$size")" || return 1
    printf '%s' "$response" | jq -e '(.files | type == "array") and (.error == null)' >/dev/null || { _google_error 'Drive listing returned an invalid/error response'; return 1; }
    printf '%s' "$response"
}

_drive_import_source_mime() {
    local source="$1"
    case "$source" in
        *.html|*.htm) printf 'text/html' ;;
        # Markdown gets its own type so Drive converts headings, lists, tables and emphasis into real Doc styles. Sending it as text/plain makes Google import the syntax literally, so the Doc shows "## Heading" and "**bold**" as visible characters. Confirmed against drive/v3/about?fields=importFormats, which lists text/markdown -> application/vnd.google-apps.document.
        *.md|*.markdown) printf 'text/markdown' ;;
        *.txt) printf 'text/plain' ;;
        *.rtf) printf 'application/rtf' ;;
        *.docx) printf 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ;;
        *.doc) printf 'application/msword' ;;
        *) printf 'text/plain' ;;
    esac
}

_drive_import_doc() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" source_file="${2:-}" title="" folder="" execute=0
    local token metadata_file mime result_file
    [ -n "$alias" ] || { _google_error "drive import-doc requires ALIAS"; return 1; }
    [ -n "$source_file" ] || { _google_error "drive import-doc requires SOURCE_FILE"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --title) [ -n "${2:-}" ] || { _google_error "--title requires TITLE"; return 1; }; title="$2"; shift 2 ;;
            --folder) [ -n "${2:-}" ] || { _google_error "--folder requires FOLDER_ID"; return 1; }; folder="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            *) _google_error "Unknown drive import-doc option: $1"; return 1 ;;
        esac
    done

    [ -f "$source_file" ] || { _google_error "Source file does not exist: $source_file"; return 1; }
    [ -n "$title" ] || { _google_error "drive import-doc requires --title TITLE"; return 1; }
    _drive_write_enabled "$alias" || {
        _google_error "Drive import is not enabled for '$alias'. Set drive.write_enabled=true in google-accounts.json and re-run 'authorize-google/scripts/authorize auth $alias'."
        return 1
    }

    _google_say "Google Drive import-doc plan:"
    mime="$(_drive_import_source_mime "$source_file")"
    _google_say "Account: $alias"
    _google_say "Source: $source_file"
    _google_say "Upload type: $mime"
    _google_say "Title: $title"
    if [ -n "$folder" ]; then
        _google_say "Folder: $folder"
    else
        _google_say "Folder: <default Drive location>"
    fi

    if [ "$execute" -ne 1 ]; then
        _google_say "DRY RUN: add --execute to create the Google Doc."
        return 0
    fi

    # BSD mktemp only substitutes X's at the very end of the template, so a trailing ".json" made this fail on macOS every time. Both files are handed to curl with an explicit content type, so the extension was never doing any work.
    metadata_file="$(mktemp "$DRIVE_WORK/google-drive-import-meta.XXXXXX")" || return 1
    result_file="$(mktemp "$DRIVE_WORK/google-drive-import-result.XXXXXX")" || return 1
    if [ -n "$folder" ]; then
        jq -n --arg name "$title" --arg parent "$folder" \
            '{name: $name, mimeType: "application/vnd.google-apps.document", parents: [$parent]}' > "$metadata_file" || return 1
    else
        jq -n --arg name "$title" \
            '{name: $name, mimeType: "application/vnd.google-apps.document"}' > "$metadata_file" || return 1
    fi

    token="$(_google_access_token "$alias")" || return 1
    curl -fsS -X POST "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,mimeType,webViewLink,parents,driveId" \
        -H "Authorization: Bearer ${token}" \
        -F "metadata=@${metadata_file};type=application/json;charset=UTF-8" \
        -F "file=@${source_file};type=${mime}" > "$result_file" || return 1

    jq -e '.id | type == "string" and length > 0' "$result_file" >/dev/null || { _google_error "Import returned no document ID; inspect the target before retrying"; return 1; }
    jq -r '
      "Created Google Doc: " + (.webViewLink // "") + "\n" +
      "Name: " + (.name // "") + "\n" +
      "ID: " + (.id // "") + "\n" +
      "Parents: " + (((.parents // []) | join(", "))) + "\n" +
      "Drive ID: " + (.driveId // "")
    ' "$result_file"
)

_drive_rename_fetch() {
    local alias="$1" file_id="$2" response
    response="$(_google_get_url "$alias" "https://www.googleapis.com/drive/v3/files/${file_id}" \
        --data-urlencode "supportsAllDrives=true" \
        --data-urlencode "fields=id,name,mimeType,parents,driveId,trashed,webViewLink,capabilities(canRename)")" || return 1
    printf '%s' "$response" | jq -e --arg id "$file_id" '.id == $id and (.name | type == "string")' >/dev/null || { _google_error 'Drive returned unexpected metadata for this file ID'; return 1; }
    printf '%s\n' "$response"
}

# Prints IDs of other nontrashed items in PARENT whose name is exactly NAME; Drive allows duplicates, so a match would make the result ambiguous.
_drive_rename_siblings() {
    local alias="$1" parent="$2" drive_id="$3" name="$4" self="$5" response
    local args=(--data-urlencode "q='$(_drive_query_escape "$parent")' in parents and name = '$(_drive_query_escape "$name")' and trashed = false" --data-urlencode 'fields=files(id,name),nextPageToken' --data-urlencode 'pageSize=10' --data-urlencode 'supportsAllDrives=true' --data-urlencode 'includeItemsFromAllDrives=true')
    [ -z "$drive_id" ] || args+=(--data-urlencode 'corpora=drive' --data-urlencode "driveId=${drive_id}")
    response="$(_google_get_url "$alias" 'https://www.googleapis.com/drive/v3/files' "${args[@]}")" || return 1
    printf '%s' "$response" | jq -er --arg name "$name" --arg self "$self" 'if (.files | type) == "array" then [.files[] | select(.name == $name and .id != $self) | .id] | join(", ") else error("invalid listing") end'
}

_drive_sha256() {
    _google_python "$GOOGLE_DRIVE_DIR" -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

# drive rename ALIAS FILE_URL_OR_ID --name NEW_NAME [--expect PREVIEW_SHA256 --execute]
# Changes only the name of one file or folder. The fingerprint detects changes between preview and execution; it is not an atomic lock.
_drive_rename() (
    set -o pipefail
    _drive_work_begin || return 1
    local alias="${1:-}" ref="${2:-}" name="" execute=0 expect=""
    local file_id meta_file plan_hash parent duplicates sibling_check="no other item in the parent uses the proposed name" body_file result_file token status request_ok=0 error_message
    [ -n "$alias" ] || { _google_error "drive rename requires ALIAS"; return 1; }
    [ -n "$ref" ] || { _google_error "drive rename requires FILE_URL_OR_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --name) [ -n "${2:-}" ] || { _google_error "--name requires NEW_NAME"; return 1; }; name="$2"; shift 2 ;;
            --expect) [ -n "${2:-}" ] || { _google_error "--expect requires PREVIEW_SHA256"; return 1; }; expect="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            *) _google_error "Unknown drive rename option: $1"; return 1 ;;
        esac
    done
    [ -n "$name" ] || { _google_error "drive rename requires --name NEW_NAME"; return 1; }
    case "$name" in *[[:cntrl:]]*) _google_error 'New name must be a single line without control characters'; return 1 ;; esac
    [ -n "$(_google_trim "$name")" ] || { _google_error 'New name cannot be blank'; return 1; }
    [ "$name" = "$(_google_trim "$name")" ] || { _google_error 'New name cannot start or end with whitespace'; return 1; }
    if [ "$execute" -eq 1 ]; then
        _drive_rename_enabled "$alias" || { _google_error "Drive rename is not enabled for '$alias'. Set drive.rename_enabled=true in google-accounts.json; see the authorize-google scope notes."; return 1; }
        printf '%s' "$expect" | LC_ALL=C grep -Eq '^[a-f0-9]{64}$' || { _google_error 'Execute requires --expect PREVIEW_SHA256 from a preview of this exact rename'; return 1; }
    elif [ -n "$expect" ]; then
        _google_error '--expect is only used with --execute'; return 1
    fi

    file_id="$(_drive_file_id "$ref")" || return 1
    meta_file="$DRIVE_WORK/rename-before.json"
    _drive_rename_fetch "$alias" "$file_id" > "$meta_file" || return 1
    jq -e '(.trashed // false) | not' "$meta_file" >/dev/null || { _google_error 'Refusing to rename a trashed item'; return 1; }
    jq -e '.driveId == null or .id != .driveId' "$meta_file" >/dev/null || { _google_error 'This ID is a shared drive root; shared drives are renamed through drives.update, which this CLI does not support'; return 1; }
    jq -e --arg name "$name" '.name != $name' "$meta_file" >/dev/null || { _google_error 'The item already has this name; nothing to rename'; return 1; }

    while IFS= read -r parent; do
        [ -n "$parent" ] || continue
        duplicates="$(_drive_rename_siblings "$alias" "$parent" "$(jq -r '.driveId // ""' "$meta_file")" "$name" "$file_id")" || { _google_error "Cannot check parent $parent for an existing item with this name"; return 1; }
        [ -z "$duplicates" ] || { _google_error "Parent $parent already contains an item with this exact name ($duplicates); choose an unambiguous name"; return 1; }
    done <<EOF
$(jq -r '(.parents // [])[]' "$meta_file")
EOF
    jq -e '(.parents // []) | length > 0' "$meta_file" >/dev/null || sibling_check='skipped because no parent is visible to this account'

    plan_hash="$(jq -cS --arg alias "$alias" --arg name "$name" '{alias:$alias, id:.id, mimeType:(.mimeType // ""), driveId:(.driveId // ""), parents:(.parents // []), trashed:(.trashed // false), current_name:.name, proposed_name:$name}' "$meta_file" | _drive_sha256)" || return 1

    _google_say "Google Drive rename plan:"
    _google_say "Account: $alias ($(_google_account_email "$alias"))"
    jq -r --arg name "$name" '
      "File ID: " + .id + "\n" +
      "MIME type: " + (.mimeType // "") + "\n" +
      "Current name: " + .name + "\n" +
      "Proposed name: " + $name + "\n" +
      "Parents: " + (((.parents // []) | join(", ")) | if . == "" then "<none visible>" else . end) + "\n" +
      "Drive ID: " + (.driveId // "<My Drive>") + "\n" +
      "URL: " + (.webViewLink // "") + "\n" +
      "Account can rename: " + ((.capabilities.canRename // false) | tostring)
    ' "$meta_file"
    _google_say "Same-name check: $sibling_check"
    if jq -e '.mimeType == "application/vnd.google-apps.shortcut"' "$meta_file" >/dev/null; then _drive_warn 'This is a shortcut; renaming it does not rename its target.'; fi
    _google_say "Preview SHA-256: $plan_hash"

    if [ "$execute" -ne 1 ]; then
        _drive_rename_enabled "$alias" || _google_say "Execution is currently blocked: drive.rename_enabled is not true for '$alias'."
        _google_say "DRY RUN: review, then repeat the same arguments with --expect $plan_hash --execute."
        return 0
    fi
    [ "$expect" = "$plan_hash" ] || { _google_error 'The item or rename no longer matches the reviewed preview (name, parent, or arguments changed). Nothing was renamed; preview again.'; return 1; }
    jq -e '.capabilities.canRename == true' "$meta_file" >/dev/null || { _google_error "Drive reports that '$alias' cannot rename this item"; return 1; }

    body_file="$DRIVE_WORK/rename-body.json"
    result_file="$DRIVE_WORK/rename-result.json"
    jq -n --arg name "$name" '{name: $name}' > "$body_file" || return 1
    token="$(_google_access_token "$alias")" || return 1
    status="$(curl -sS -o "$result_file" -w '%{http_code}' -X PATCH "https://www.googleapis.com/drive/v3/files/${file_id}?supportsAllDrives=true&fields=id,name" \
        -H "Authorization: Bearer ${token}" \
        -H 'Content-Type: application/json; charset=UTF-8' \
        --data-binary "@${body_file}")" || status=000
    case "$status" in 2??) request_ok=1 ;; esac
    if [ "$request_ok" -ne 1 ]; then
        error_message="$(jq -r '.error.message // empty' "$result_file" 2>/dev/null || true)"
        _google_error "Rename request failed (HTTP $status)${error_message:+: $error_message}"
        if jq -e '[.. | .reason? // empty] | any(. == "insufficientPermissions" or . == "ACCESS_TOKEN_SCOPE_INSUFFICIENT")' "$result_file" >/dev/null 2>&1; then
            _google_error "The '$alias' token lacks a scope that can rename this item: drive.metadata or full drive is required, and drive.file reaches only files this app created or opened."
        fi
    fi

    # Readback runs after every attempt so an uncertain outcome is reported from Drive's current state, not assumed.
    if ! _drive_rename_fetch "$alias" "$file_id" > "$DRIVE_WORK/rename-after.json"; then
        _google_error "Readback failed; the rename outcome is unknown. Inspect with 'drive meta $alias $file_id' before retrying."
        return 1
    fi
    if jq -e --arg name "$name" '.name == $name' "$DRIVE_WORK/rename-after.json" >/dev/null; then
        if [ "$request_ok" -ne 1 ]; then
            _google_error "Readback shows the proposed name although the request reported failure; inspect before relying on it."
            return 1
        fi
        jq -r --slurpfile before "$meta_file" '
          "Renamed Drive item: " + .id + "\n" +
          "Previous name: " + $before[0].name + "\n" +
          "Confirmed name: " + .name + "\n" +
          "URL: " + (.webViewLink // "")
        ' "$DRIVE_WORK/rename-after.json"
        return 0
    fi
    if [ "$request_ok" -eq 1 ]; then
        _google_error "Drive accepted the request, but readback shows a different name: $(jq -r '.name' "$DRIVE_WORK/rename-after.json"). Inspect before retrying."
    else
        _google_error "Not renamed; current name: $(jq -r '.name' "$DRIVE_WORK/rename-after.json")"
    fi
    return 1
)

