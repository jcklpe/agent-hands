#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then _microsoft_source="${(%):-%x}"; else _microsoft_source="${BASH_SOURCE[0]}"; fi
MICROSOFT_FILES_DIR="$(cd "$(dirname "$_microsoft_source")/.." && pwd)"
unset _microsoft_source
source "$MICROSOFT_FILES_DIR/../authorize-microsoft/scripts/drive-items.sh"

_m365_files_print_item() {
    jq -r '"name: " + (.name // "?"),
           "item_id: " + (.id // "?"),
           "drive_id: " + (.parentReference.driveId // "?"),
           "size: " + ((.size // 0) | tostring) + " bytes",
           "modified: " + (.lastModifiedDateTime // "?"),
           "mimeType: " + (.file.mimeType // "(folder or unknown)"),
           "path: " + ((.parentReference.path // "") + "/" + (.name // "")),
           "url: " + (.webUrl // "")'
}

_m365_files_search() {
    local alias="$1" query="$2" drive="" json=0 base enc response encoded_drive
    [ -n "$alias" ] || { _m365_error "m365 files search requires ALIAS QUERY"; return 1; }
    [ -n "$query" ] || { _m365_error "m365 files search requires a QUERY"; return 1; }
    shift 2 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --json) json=1; shift ;;
            *) _m365_error "Unknown files search option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" files || return 1
    base="$(_m365_graph_base "$alias")"
    enc="$(_m365_uri_encode "$query")"
    if [ -n "$drive" ]; then
        encoded_drive="$(_m365_uri_encode "$drive")" || return 1
        base="${base}/drives/${encoded_drive}"
    else
        base="${base}/me/drive"
    fi
    response="$(_m365_get "$alias" "${base}/root/search(q='${enc}')" \
        --data-urlencode "\$select=id,name,size,lastModifiedDateTime,webUrl,file,parentReference" \
        --data-urlencode "\$top=25")" || return 1
    printf '%s' "$response" | jq -e '.value | type == "array"' >/dev/null || return 1
    if printf '%s' "$response" | jq -e '."@odata.nextLink"' >/dev/null; then _m365_files_warn 'File search is limited to its first response page'; fi
    if [ "$json" -eq 1 ]; then printf '%s\n' "$response"; return 0; fi
    printf '%s' "$response" |
        jq -r '(.value // [])[] |
            "- " + (.name // "?") +
            "\n  item_id: " + (.id // "?") +
            "\n  drive_id: " + (.parentReference.driveId // "?") +
            "\n  type: " + (.file.mimeType // "(folder)") +
            "\n  modified: " + (.lastModifiedDateTime // "?") +
            "\n  path: " + ((.parentReference.path // "") + "/" + (.name // "")) +
            "\n  url: " + (.webUrl // "")'
}

_m365_files_meta() {
    local alias="$1" item="$2" drive="" json=0 url response
    [ -n "$alias" ] || { _m365_error "m365 files meta requires ALIAS ITEM_ID"; return 1; }
    [ -n "$item" ] || { _m365_error "m365 files meta requires a drive-item id (from 'files search')"; return 1; }
    shift 2 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --json) json=1; shift ;;
            *) _m365_error "Unknown files meta option: $1"; return 1 ;;
        esac
    done
    _m365_require_enabled "$alias" files || return 1
    url="$(_m365_files_item_url "$alias" "$item" "$drive")" || return 1
    response="$(_m365_get "$alias" "$url" --data-urlencode "\$select=id,name,size,lastModifiedDateTime,webUrl,file,parentReference")" || return 1
    if [ "$json" -eq 1 ]; then printf '%s\n' "$response"; else printf '%s' "$response" | _m365_files_print_item; fi
}

_m365_files_resolve_link() {
    local alias="$1" sharing_url="$2" json=0 base token response
    [ -n "$alias" ] || { _m365_error "m365 files resolve-link requires ALIAS URL"; return 1; }
    [ -n "$sharing_url" ] || { _m365_error "m365 files resolve-link requires a OneDrive, SharePoint, or Teams sharing URL"; return 1; }
    shift 2 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json=1; shift ;;
            *) _m365_error "Unknown files resolve-link option: $1"; return 1 ;;
        esac
    done
    case "$sharing_url" in https://*) ;; *) _m365_error "Sharing URL must use https://"; return 1 ;; esac
    _m365_require_enabled "$alias" files || return 1
    token="$(_m365_python "$MICROSOFT_FILES_DIR" -c 'import base64, sys; print("u!" + base64.urlsafe_b64encode(sys.argv[1].encode()).decode().rstrip("="))' "$sharing_url")" || return 1
    base="$(_m365_graph_base "$alias")"
    response="$(_m365_get "$alias" "${base}/shares/${token}/driveItem" --data-urlencode "\$select=id,name,size,lastModifiedDateTime,webUrl,file,parentReference")" || return 1
    if [ "$json" -eq 1 ]; then printf '%s\n' "$response"; else printf '%s' "$response" | _m365_files_print_item; fi
}

_m365_files_download() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" item="$2" out="" drive="" force=0 url tmp mode=create
    shift 2 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --out) [ -n "${2:-}" ] || { _m365_error "--out requires PATH"; return 1; }; out="$2"; shift 2 ;;
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --force) force=1; shift ;;
            *) _m365_error "Unknown files download option: $1"; return 1 ;;
        esac
    done
    [ -n "$alias" ] || { _m365_error "m365 files download requires ALIAS ITEM_ID [--out PATH]"; return 1; }
    [ -n "$item" ] || { _m365_error "m365 files download requires a drive-item id"; return 1; }
    [ -n "$out" ] || { _m365_error "m365 files download requires --out PATH"; return 1; }
    _m365_require_enabled "$alias" files || return 1
    [ "$force" -eq 1 ] || [ ! -e "$out" ] || { _m365_error "Refusing to overwrite existing file: $out (use --force)"; return 1; }
    [ -d "$(dirname "$out")" ] || { _m365_error "Output directory does not exist: $(dirname "$out")"; return 1; }
    url="$(_m365_files_item_url "$alias" "$item" "$drive")" || return 1
    [ ! -L "$out" ] || { _m365_error 'Refusing to replace a symlink'; return 1; }
    tmp="$M365_WORK/download"
    _m365_get "$alias" "${url}/content" --output-file "$tmp" > /dev/null || return 1
    [ "$force" -eq 0 ] || mode=replace
    _m365_python "$MICROSOFT_FILES_DIR" "$M365_AUTH_DIR/scripts/publish.py" "$tmp" "$out" "$mode" || return 1
    _m365_say "Downloaded item ${item} -> ${out}"
)

# Graph's simple upload accepts up to 250 MB; larger files need an upload session, which this surface does not implement.
_M365_FILES_MAX_BYTES=262144000
_m365_files_warn() { printf 'WARN: %s\n' "$*" >&2; }
_m365_files_audit_path() { case "${M365_FILES_AUDIT_LOG:-file-writes.jsonl}" in /*) printf '%s\n' "$M365_FILES_AUDIT_LOG" ;; *) printf '%s/%s\n' "$MICROSOFT_FILES_DIR" "${M365_FILES_AUDIT_LOG:-file-writes.jsonl}" ;; esac; }
_m365_files_audit_append() { _m365_python "$MICROSOFT_FILES_DIR" "$M365_AUTH_DIR/scripts/audit.py" "$(_m365_files_audit_path)"; }


_m365_files_local_size() {
    wc -c < "$1" | tr -d ' '
}

_m365_files_check_local() {
    local file="$1" size
    [ -f "$file" ] || { _m365_error "Local file does not exist: $file"; return 1; }
    size="$(_m365_files_local_size "$file")"
    [ "$size" -le "$_M365_FILES_MAX_BYTES" ] || { _m365_error "File is $size bytes; uploads are limited to 250 MB"; return 1; }
    case "$file" in *.[oO][nN][eE]|*.[oO][nN][eE][tT][oO][cC]2) _m365_error "Refusing to upload OneNote files; OneNote notebooks cannot be safely written as files"; return 1 ;; esac
}

# Refuse anything that is a OneNote notebook or section, or not a plain file.
_m365_files_refuse_special() {
    local item="$1" what="$2"
    if printf '%s' "$item" | jq -e '.package.type == "oneNote" or ((.name // "") | test("\\.(one|onetoc2)$"; "i"))' >/dev/null; then
        _m365_error "Refusing to $what a OneNote notebook or section; OneNote cannot be safely written as files"
        return 1
    fi
}

_m365_files_audit() {
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$1" --arg action "$2" --argjson item "$3" --argjson verified "$4" \
        '{ts: $ts, service: "m365-files", alias: $alias, action: $action, item_id: $item.id, name: $item.name, drive_id: ($item.parentReference.driveId // null), size: ($item.size // null), url: ($item.webUrl // null), verified: $verified}' | _m365_files_audit_append || _m365_files_warn "Could not append to the private file audit log"
}

_m365_files_upload() {
    local alias="${1:-}" file="${2:-}" parent="" drive="" name="" execute=0 parent_url parent_item size url created readback ok
    [ -n "$alias" ] && [ -n "$file" ] || { _m365_error "m365 files upload requires ALIAS LOCAL_FILE --parent FOLDER_ITEM_ID"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --parent) [ -n "${2:-}" ] || { _m365_error "--parent requires a folder item id or 'root'"; return 1; }; parent="$2"; shift 2 ;;
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --name) [ -n "${2:-}" ] || { _m365_error "--name requires TEXT"; return 1; }; name="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown files upload option: $1"; return 1 ;;
        esac
    done
    [ -n "$parent" ] || { _m365_error "files upload requires --parent FOLDER_ITEM_ID (or root)"; return 1; }
    _m365_require_enabled "$alias" files || return 1
    _m365_files_check_local "$file" || return 1
    [ -n "$name" ] || name="$(basename "$file")"
    case "$name" in */*|*\\*) _m365_error "--name must be a file name, not a path"; return 1 ;; esac
    _m365_files_refuse_special "$(jq -nc --arg name "$name" '{name:$name}')" upload || return 1
    size="$(_m365_files_local_size "$file")"
    parent_url="$(_m365_files_item_url "$alias" "$parent" "$drive")" || return 1
    parent_item="$(_m365_get "$alias" "$parent_url" --data-urlencode '$select=id,name,folder,package,webUrl,parentReference')" || return 1
    printf '%s' "$parent_item" | jq -e '.folder != null' >/dev/null || { _m365_error "--parent is not a folder: $(printf '%s' "$parent_item" | jq -r '.name')"; return 1; }
    _m365_files_refuse_special "$parent_item" "upload into" || return 1
    if _m365_get "$alias" "${parent_url}:/$(_m365_uri_encode "$name")" --data-urlencode '$select=id' >/dev/null 2>&1; then
        _m365_error "A file named '$name' already exists in that folder; use 'files replace' to change it"
        return 1
    fi
    _m365_say "Microsoft 365 file upload plan:"
    _m365_say "Account: $alias"
    _m365_say "Local file: $file ($size bytes)"
    _m365_say "Destination: $(printf '%s' "$parent_item" | jq -r 'if (.parentReference.path // "") == "" then "" else .parentReference.path + "/" + (.name // "") end')/$name"
    _m365_say "Folder URL: $(printf '%s' "$parent_item" | jq -r '.webUrl // ""')"
    _m365_say "Note: anyone with access to that folder will see the new file."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was uploaded. Re-run with --execute to upload."; return 0; fi
    _m365_files_require_write "$alias" || return 1
    url="${parent_url}:/$(_m365_uri_encode "$name"):/content?@microsoft.graph.conflictBehavior=fail"
    created="$(_m365_http PUT "$alias" "$url" "" --upload-file "$file")" || return 1
    readback="$(_m365_get "$alias" "$(_m365_files_item_url "$alias" "$(printf '%s' "$created" | jq -r '.id')" "$(printf '%s' "$created" | jq -r '.parentReference.driveId // empty')")" --data-urlencode '$select=id,name,size,webUrl,parentReference')" || return 1
    ok="$(jq -n --argjson got "$readback" --arg name "$name" --argjson size "$size" '($got.name == $name) and ($got.size == $size)')"
    _m365_files_audit "$alias" upload "$readback" "$ok"
    [ "$ok" = true ] || { _m365_error "Uploaded, but readback did not match the local file's name and size"; return 1; }
    _m365_say "Uploaded (confirmed by readback): $(printf '%s' "$readback" | jq -r '.name + " | item_id: " + .id + " | " + (.webUrl // "")')"
}

_m365_files_replace() {
    local alias="${1:-}" item_id="${2:-}" file="" drive="" execute=0 url current size readback ok
    [ -n "$alias" ] && [ -n "$item_id" ] || { _m365_error "m365 files replace requires ALIAS ITEM_ID --file LOCAL_FILE"; return 1; }
    shift 2
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --file) [ -n "${2:-}" ] || { _m365_error "--file requires LOCAL_FILE"; return 1; }; file="$2"; shift 2 ;;
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown files replace option: $1"; return 1 ;;
        esac
    done
    [ -n "$file" ] || { _m365_error "files replace requires --file LOCAL_FILE"; return 1; }
    _m365_require_enabled "$alias" files || return 1
    _m365_files_check_local "$file" || return 1
    size="$(_m365_files_local_size "$file")"
    url="$(_m365_files_item_url "$alias" "$item_id" "$drive")" || return 1
    current="$(_m365_get "$alias" "$url" --data-urlencode '$select=id,name,size,eTag,file,folder,package,webUrl,parentReference,lastModifiedDateTime,lastModifiedBy')" || return 1
    printf '%s' "$current" | jq -e '.file != null' >/dev/null || { _m365_error "Item is not a file: $(printf '%s' "$current" | jq -r '.name')"; return 1; }
    _m365_files_refuse_special "$current" "replace" || return 1
    _m365_say "Microsoft 365 file replace plan:"
    _m365_say "Account: $alias"
    printf '%s' "$current" | jq -r '"Remote file: " + ((.parentReference.path // "") + "/" + .name), "Now: " + ((.size // 0) | tostring) + " bytes, modified " + (.lastModifiedDateTime // "?") + " by " + (.lastModifiedBy.user.displayName // "?"), "URL: " + (.webUrl // "")'
    _m365_say "New contents: $file ($size bytes)"
    _m365_say "Anyone with access sees the change. Recovery depends on the destination's version-history configuration."
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: nothing was replaced. Re-run with --execute to replace the contents."; return 0; fi
    _m365_files_require_write "$alias" || return 1
    printf '%s' "$current" | jq -e '.eTag | type == "string" and length > 0' >/dev/null || { _m365_error 'Missing remote eTag; refusing an unguarded replacement'; return 1; }
    # If-Match carries the eTag read in this run, so a file someone changed in the meantime is refused rather than overwritten.
    _m365_http PUT "$alias" "${url}/content" "" --upload-file "$file" -H "If-Match: $(printf '%s' "$current" | jq -r '.eTag')" >/dev/null || { _m365_error "Replace refused or failed; the file may have changed since it was read. Re-run to see its current state."; return 1; }
    readback="$(_m365_get "$alias" "$url" --data-urlencode '$select=id,name,size,webUrl,parentReference')" || return 1
    ok="$(jq -n --argjson got "$readback" --argjson size "$size" '$got.size == $size')"
    _m365_files_audit "$alias" replace "$readback" "$ok"
    [ "$ok" = true ] || { _m365_error "Replaced, but readback size does not match the local file"; return 1; }
    _m365_say "Replaced (confirmed by readback): $(printf '%s' "$readback" | jq -r '.name + " | " + (.size | tostring) + " bytes | " + (.webUrl // "")')"
}

_m365_files_create_folder() {
    local alias="${1:-}" parent="" drive="" name="" execute=0 parent_url parent_item created readback ok
    [ -n "$alias" ] || { _m365_error "m365 files create-folder requires ALIAS --parent FOLDER_ITEM_ID --name NAME"; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --parent) [ -n "${2:-}" ] || { _m365_error "--parent requires a folder item id or 'root'"; return 1; }; parent="$2"; shift 2 ;;
            --drive) [ -n "${2:-}" ] || { _m365_error "--drive requires DRIVE_ID"; return 1; }; drive="$2"; shift 2 ;;
            --name) [ -n "${2:-}" ] || { _m365_error "--name requires TEXT"; return 1; }; name="$2"; shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            *) _m365_error "Unknown files create-folder option: $1"; return 1 ;;
        esac
    done
    [ -n "$parent" ] && [ -n "$name" ] || { _m365_error "files create-folder requires --parent and --name"; return 1; }
    case "$name" in */*|*\\*) _m365_error "--name must be a folder name, not a path"; return 1 ;; esac
    _m365_require_enabled "$alias" files || return 1
    parent_url="$(_m365_files_item_url "$alias" "$parent" "$drive")" || return 1
    parent_item="$(_m365_get "$alias" "$parent_url" --data-urlencode '$select=id,name,folder,package,webUrl,parentReference')" || return 1
    printf '%s' "$parent_item" | jq -e '.folder != null' >/dev/null || { _m365_error "--parent is not a folder"; return 1; }
    _m365_files_refuse_special "$parent_item" "create a folder in" || return 1
    _m365_say "Microsoft 365 create-folder plan:"
    _m365_say "Account: $alias"
    _m365_say "New folder: $(printf '%s' "$parent_item" | jq -r 'if (.parentReference.path // "") == "" then "" else .parentReference.path + "/" + (.name // "") end')/$name"
    if [ "$execute" -ne 1 ]; then _m365_say "DRY RUN: no folder was created. Re-run with --execute to create it."; return 0; fi
    _m365_files_require_write "$alias" || return 1
    created="$(_m365_write POST "$alias" "${parent_url}/children" "$(jq -nc --arg n "$name" '{name: $n, folder: {}, "@microsoft.graph.conflictBehavior": "fail"}')")" || return 1
    readback="$(_m365_get "$alias" "$(_m365_files_item_url "$alias" "$(printf '%s' "$created" | jq -r '.id')" "$(printf '%s' "$created" | jq -r '.parentReference.driveId // empty')")" --data-urlencode '$select=id,name,folder,webUrl,parentReference')" || return 1
    ok="$(jq -n --argjson got "$readback" --arg name "$name" '($got.name == $name) and ($got.folder != null)')"
    _m365_files_audit "$alias" create-folder "$readback" "$ok"
    [ "$ok" = true ] || { _m365_error "Created, but readback did not match"; return 1; }
    _m365_say "Created folder (confirmed by readback): $(printf '%s' "$readback" | jq -r '.name + " | item_id: " + .id + " | " + (.webUrl // "")')"
}
