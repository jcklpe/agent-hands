#!/usr/bin/env bash
##- Read Sheets directly, without requiring the Drive capability.
_google_sheets_read() (
    set -o pipefail
    local alias="${1:-}" reference="${2:-}" range="" file_id directory title row_limit
    [ -n "$alias" ] && [ -n "$reference" ] || { _google_error 'sheets read requires ALIAS and FILE_URL_OR_ID'; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --range) [ -n "${2:-}" ] || { _google_error '--range requires RANGE'; return 1; }; range="$2"; shift 2 ;;
            *) _google_error 'Unknown Sheets read option'; return 1 ;;
        esac
    done
    file_id="$reference"
    case "$file_id" in
        https://docs.google.com/spreadsheets/d/*) file_id="${file_id#https://docs.google.com/spreadsheets/d/}"; file_id="${file_id%%/*}"; file_id="${file_id%%\?*}" ;;
    esac
    printf '%s' "$file_id" | grep -Eq '^[A-Za-z0-9_-]+$' || { _google_error 'Expected a Google Sheets URL or file ID'; return 1; }
    directory="$(mktemp -d "${TMPDIR:-/tmp}/google-sheets.XXXXXX")" || return 1
    trap 'rm -rf "$directory"' EXIT
    trap 'exit 130' HUP INT TERM
    _google_get_url "$alias" "https://sheets.googleapis.com/v4/spreadsheets/${file_id}" \
        --data-urlencode 'fields=properties(title),sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))' > "$directory/meta.json" || return 1
    jq -e '(.sheets | type == "array" and length > 0)' "$directory/meta.json" >/dev/null || { _google_error 'No sheet tabs were returned'; return 1; }
    if [ -z "$range" ]; then
        title="$(jq -r '.sheets[0].properties.title' "$directory/meta.json" | sed "s/'/''/g")" || return 1
        row_limit="$(_google_account_value "$alias" '.sheets.row_limit // .drive.sheet_row_limit // 200')" || return 1
        printf '%s' "$row_limit" | grep -Eq '^[1-9][0-9]*$' || { _google_error 'The configured sheet row limit must be a positive integer'; return 1; }
        range="'${title}'!A1:Z${row_limit}"
    fi
    range="$(jq -rn --arg value "$range" '$value | @uri')" || return 1
    _google_get_url "$alias" "https://sheets.googleapis.com/v4/spreadsheets/${file_id}/values/${range}" > "$directory/values.json" || return 1
    jq -e '(.values == null) or (.values | type == "array")' "$directory/values.json" >/dev/null || { _google_error 'Unexpected Sheets values response'; return 1; }
    _google_python "$GOOGLE_SHEETS_DIR" "$GOOGLE_AUTH_DIR/scripts/sheets_render.py" "$alias" "$file_id" "$directory/meta.json" "$directory/values.json"
)
