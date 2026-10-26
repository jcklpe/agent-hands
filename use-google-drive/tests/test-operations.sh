#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_CONFIG_DIR="$WORK" TMPDIR="$WORK/temp"
jq '.accounts[0].drive.enabled=true | .accounts[0].drive.write_enabled=true' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/google-accounts.json"
_google_access_token() { printf '%s' synthetic-access; }
_google_get_url() {
    local url="$2" arg query=""
    shift 2
    for arg in "$@"; do case "$arg" in q=*) query="${arg#q=}" ;; esac; done
    printf '%s\n' "$query" >> "$WORK/queries"
    printf '%s\n' "$*" >> "$WORK/get-args"
    if [ "${FAIL_LIST:-0}" = 1 ]; then printf '%s' '{"error":{"code":403}}'; return; fi
    case "$url" in
        */files/synthetic-file) jq -n --arg name "${REMOTE_NAME:-example.txt}" '{id:"synthetic-file",name:$name,mimeType:"text/plain"}' ;;
        */files/rename-*)
            if [ "${FAIL_READBACK:-0}" = 1 ] && [ -s "$WORK/patches" ]; then return 1; fi
            cat "$WORK/remote/${url##*/files/}.json" ;;
        */files)
            case "$query" in
                *"'root' in parents"*) printf '%s' '{"files":[{"id":"folder-one","name":"Example Folder","mimeType":"application/vnd.google-apps.folder"}],"nextPageToken":"more-folders"}' ;;
                *"'folder-one' in parents"*)
                    [ "${FAIL_CHILDREN:-0}" = 0 ] || return 1
                    printf '%s' '{"files":[{"id":"child-one","name":"Example Child","mimeType":"text/plain"}]}' ;;
                *"name = '"*)
                    if [ -n "${SIBLING_NAME:-}" ]; then jq -n --arg name "$SIBLING_NAME" '{files:[{id:"sibling-item",name:$name}]}'; else printf '%s' '{"files":[]}'; fi ;;
                *) printf '%s' '{"files":[]}' ;;
            esac ;;
        *) return 1 ;;
    esac
}
# PATCH_MODE: ok applies and confirms; ignored confirms without applying; scope refuses with a 403 scope error; lost applies but the transport fails.
curl() {
    local out="" arg previous="" patch=0 body="" url="" id new_name
    printf '%s\n' called >> "$WORK/curl-calls"
    for arg in "$@"; do
        [ "$previous" != -o ] || out="$arg"
        [ "$previous" != --data-binary ] || body="${arg#@}"
        case "$arg" in PATCH) patch=1 ;; https://*) url="$arg" ;; esac
        previous="$arg"
    done
    if [ "$patch" -eq 1 ]; then
        id="${url##*/files/}"; id="${id%%\?*}"
        new_name="$(jq -r .name "$body")"
        jq -c . "$body" >> "$WORK/patches"
        case "${PATCH_MODE:-ok}" in ok|lost) jq --arg name "$new_name" '.name = $name' "$WORK/remote/$id.json" > "$WORK/remote/next.json" && mv "$WORK/remote/next.json" "$WORK/remote/$id.json" ;; esac
        case "${PATCH_MODE:-ok}" in
            ok|ignored) jq -n --arg id "$id" --arg name "$new_name" '{id:$id, name:$name}' > "$out"; printf 200 ;;
            scope) printf '%s' '{"error":{"code":403,"message":"Request had insufficient authentication scopes.","errors":[{"reason":"insufficientPermissions"}],"details":[{"reason":"ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}' > "$out"; printf 403 ;;
            lost) printf 000; return 28 ;;
        esac
        return 0
    fi
    if [ -n "$out" ]; then
        printf '%s' 'downloaded bytes' > "$out"
        [ "${FAIL_DOWNLOAD:-0}" = 0 ] || return 1
    else
        printf '%s' '{"id":"created-doc","name":"Synthetic upload","webViewLink":"https://docs.google.com/document/d/created-doc/edit"}'
    fi
}
expect_failure() { if "$@" > "$WORK/failure-out" 2> "$WORK/failure-error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
printf '%s' previous > "$WORK/download.txt"
expect_failure _drive_download example synthetic-file --out "$WORK/download.txt"
FAIL_DOWNLOAD=1 expect_failure _drive_download example synthetic-file --out "$WORK/download.txt" --force
[ "$(cat "$WORK/download.txt")" = previous ]
_drive_download example synthetic-file --out "$WORK/download.txt" --force > /dev/null
[ "$(cat "$WORK/download.txt")" = 'downloaded bytes' ]
REMOTE_NAME=../escape expect_failure _drive_download example synthetic-file --out "$WORK"
ln -s "$WORK/download.txt" "$WORK/symlink.txt"
expect_failure _drive_download example synthetic-file --out "$WORK/symlink.txt" --force
[ "$(cat "$WORK/download.txt")" = 'downloaded bytes' ]
printf '%s' previous > "$WORK/index.md"
FAIL_LIST=1 expect_failure _drive_export_index example --output "$WORK/index.md"
[ "$(cat "$WORK/index.md")" = previous ]
FAIL_CHILDREN=1 expect_failure _drive_export_index example --output "$WORK/index.md"
[ "$(cat "$WORK/index.md")" = previous ]
_drive_export_index example --output "$WORK/index.md" > /dev/null
grep -F 'Example Child' "$WORK/index.md" >/dev/null
grep -F 'Additional folders or recent files were omitted' "$WORK/index.md" >/dev/null
# A disabled recent sample must skip the request itself, not hide an already fetched response.
: > "$WORK/queries"
_drive_export_index example --output "$WORK/index.md" --recent 0 > /dev/null
! grep -F 'modifiedTime >' "$WORK/queries" >/dev/null
grep -F 'no account-wide recent-file query was performed' "$WORK/index.md" >/dev/null
grep -F 'Example Child' "$WORK/index.md" >/dev/null
expect_failure _drive_export_index example --output "$WORK/index.md" --recent -1
# Caller exclusions add to configured exclusions and prevent the child request itself.
cp "$WORK/google-accounts.json" "$WORK/original.json"
jq '.accounts[0].drive.index_exclude=["Configured Folder"]' "$WORK/original.json" > "$WORK/google-accounts.json"
: > "$WORK/queries"
_drive_export_index example --output "$WORK/index.md" --recent 0 --exclude-folder 'Unrelated Folder' --exclude-folder 'Example Folder' > /dev/null
! grep -F "'folder-one' in parents" "$WORK/queries" >/dev/null
! grep -F 'Example Child' "$WORK/index.md" >/dev/null
jq '.accounts[0].drive.index_exclude=["Example Folder"]' "$WORK/original.json" > "$WORK/google-accounts.json"
: > "$WORK/queries"
_drive_export_index example --output "$WORK/index.md" --recent 0 --exclude-folder 'Other Folder' > /dev/null
! grep -F "'folder-one' in parents" "$WORK/queries" >/dev/null
cp "$WORK/index.md" "$WORK/previous-index.md"
for invalid in '"invalid"' 'false' '{}' '["two\nlines"]' '[7]'; do
    jq --argjson invalid "$invalid" '.accounts[0].drive.index_exclude=$invalid' "$WORK/original.json" > "$WORK/google-accounts.json"
    : > "$WORK/queries"
    expect_failure _drive_export_index example --output "$WORK/index.md" --exclude-folder 'Example Folder'
    [ ! -s "$WORK/queries" ]
    cmp "$WORK/index.md" "$WORK/previous-index.md"
done
cp "$WORK/original.json" "$WORK/google-accounts.json"
expect_failure _drive_export_index example --output "$WORK/index.md" --exclude-folder
expect_failure _drive_export_index example --output "$WORK/index.md" --exclude-folder $'two\nlines'
expect_failure _drive_export_index example
printf '%s' 'Example body' > "$WORK/body.md"
: > "$WORK/curl-calls"
_drive_import_doc example "$WORK/body.md" --title 'Synthetic upload' > "$WORK/preview"
grep -F 'DRY RUN' "$WORK/preview" >/dev/null
[ ! -s "$WORK/curl-calls" ]
_drive_import_doc example "$WORK/body.md" --title 'Synthetic upload' --execute > "$WORK/created"
grep -F 'created-doc' "$WORK/created" >/dev/null
jq '.accounts[0].drive.write_enabled=false' "$WORK/google-accounts.json" > "$WORK/disabled.json"
GOOGLE_ACCOUNTS_PATH=disabled.json expect_failure _drive_import_doc example "$WORK/body.md" --title Example --execute
# Rename previews without the opt-in, executes only with the opt-in and a matching fingerprint, and reports Drive's readback rather than the request result.
mkdir "$WORK/remote"
remote_item() {
    local extra="${3:-}"
    [ -n "$extra" ] || extra='{}'
    jq -n --arg id "$1" --arg name "$2" --argjson extra "$extra" '{id:$id, name:$name, mimeType:"application/vnd.google-apps.document", parents:["parent-folder"], trashed:false, webViewLink:("https://docs.google.com/document/d/" + $id + "/edit"), capabilities:{canRename:true}} + $extra' > "$WORK/remote/$1.json"
}
preview_hash() { sed -n 's/^Preview SHA-256: //p' "$1"; }
no_write() { [ ! -s "$WORK/curl-calls" ] && [ ! -s "$WORK/patches" ]; }
reset_calls() { : > "$WORK/curl-calls"; : > "$WORK/patches"; : > "$WORK/get-args"; }
cp "$WORK/original.json" "$WORK/google-accounts.json"
remote_item rename-doc 'Old Project Overview'
reset_calls
_drive_rename example rename-doc --name 'New Project Overview' > "$WORK/preview"
for expected in 'Account: example (person@example.com)' 'File ID: rename-doc' 'MIME type: application/vnd.google-apps.document' 'Current name: Old Project Overview' 'Proposed name: New Project Overview' 'Parents: parent-folder' 'Drive ID: <My Drive>' 'Account can rename: true' 'Same-name check: no other item' 'Execution is currently blocked' 'DRY RUN'; do
    grep -F -- "$expected" "$WORK/preview" >/dev/null
done
no_write
hash="$(preview_hash "$WORK/preview")"
printf '%s' "$hash" | grep -Eq '^[a-f0-9]{64}$'
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$hash" --execute
grep -F 'drive.rename_enabled' "$WORK/failure-error" >/dev/null
no_write
jq '.accounts[0].drive.rename_enabled = true' "$WORK/original.json" > "$WORK/google-accounts.json"
_drive_rename example rename-doc --name 'New Project Overview' > "$WORK/preview"
[ "$(preview_hash "$WORK/preview")" = "$hash" ]
if grep -F 'Execution is currently blocked' "$WORK/preview" >/dev/null; then exit 1; fi
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --execute
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$hash"
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$(printf '0%.0s' $(seq 64))" --execute
expect_failure _drive_rename example rename-doc --name 'Different Name' --expect "$hash" --execute
no_write
: > "$WORK/get-args"
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect not-a-preview-hash --execute
[ ! -s "$WORK/get-args" ]
for invalid in '' '   ' ' Leading space' 'Trailing space ' $'two\nlines' $'tab\tname' 'Old Project Overview'; do
    expect_failure _drive_rename example rename-doc --name "$invalid"
done
SIBLING_NAME='Taken Name' expect_failure _drive_rename example rename-doc --name 'Taken Name'
grep -F 'sibling-item' "$WORK/failure-error" >/dev/null
no_write
# A name changed by someone else after the preview invalidates the reviewed fingerprint before any write.
remote_item rename-doc 'Renamed Elsewhere'
expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$hash" --execute
grep -F 'Current name: Renamed Elsewhere' "$WORK/failure-out" >/dev/null
grep -F 'no longer matches the reviewed preview' "$WORK/failure-error" >/dev/null
no_write
remote_item rename-doc 'Old Project Overview'
_drive_rename example rename-doc --name 'New Project Overview' --expect "$hash" --execute > "$WORK/renamed"
grep -F 'Previous name: Old Project Overview' "$WORK/renamed" >/dev/null
grep -F 'Confirmed name: New Project Overview' "$WORK/renamed" >/dev/null
[ "$(cat "$WORK/patches")" = '{"name":"New Project Overview"}' ]
[ "$(jq -r .name "$WORK/remote/rename-doc.json")" = 'New Project Overview' ]
for mode in ignored scope lost readback; do
    remote_item rename-doc 'Old Project Overview'
    reset_calls
    if [ "$mode" = readback ]; then
        FAIL_READBACK=1 expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$hash" --execute
    else
        PATCH_MODE="$mode" expect_failure _drive_rename example rename-doc --name 'New Project Overview' --expect "$hash" --execute
    fi
    [ "$(wc -l < "$WORK/patches" | tr -d ' ')" = 1 ]
    case "$mode" in
        ignored) grep -F 'readback shows a different name: Old Project Overview' "$WORK/failure-error" >/dev/null ;;
        scope) grep -F 'lacks a scope' "$WORK/failure-error" >/dev/null; grep -F 'Not renamed; current name: Old Project Overview' "$WORK/failure-error" >/dev/null ;;
        lost) grep -F 'although the request reported failure' "$WORK/failure-error" >/dev/null ;;
        readback) grep -F 'outcome is unknown' "$WORK/failure-error" >/dev/null ;;
    esac
done
# Folders on shared drives accept folder URLs and confine the same-name check to that drive.
remote_item rename-folder 'Landlord Mapper' '{"mimeType":"application/vnd.google-apps.folder","driveId":"shared-drive","parents":["shared-drive"],"webViewLink":"https://drive.google.com/drive/folders/rename-folder"}'
reset_calls
_drive_rename example 'https://drive.google.com/drive/folders/rename-folder?usp=sharing' --name 'Texas LandlordMapper' > "$WORK/preview"
grep -F 'MIME type: application/vnd.google-apps.folder' "$WORK/preview" >/dev/null
grep -F 'Drive ID: shared-drive' "$WORK/preview" >/dev/null
grep -F 'corpora=drive' "$WORK/get-args" >/dev/null
grep -F 'driveId=shared-drive' "$WORK/get-args" >/dev/null
_drive_rename example rename-folder --name 'Texas LandlordMapper' --expect "$(preview_hash "$WORK/preview")" --execute > "$WORK/renamed"
grep -F 'Confirmed name: Texas LandlordMapper' "$WORK/renamed" >/dev/null
remote_item rename-root 'Shared Drive' '{"driveId":"rename-root","parents":[]}'
remote_item rename-trashed 'Trashed Doc' '{"trashed":true}'
reset_calls
expect_failure _drive_rename example rename-root --name 'Other Drive'
expect_failure _drive_rename example rename-trashed --name 'Other Doc'
remote_item rename-locked 'Locked Doc' '{"capabilities":{"canRename":false},"parents":[]}'
_drive_rename example rename-locked --name 'Unlocked Doc' > "$WORK/preview"
grep -F 'Account can rename: false' "$WORK/preview" >/dev/null
grep -F 'Same-name check: skipped because no parent is visible' "$WORK/preview" >/dev/null
expect_failure _drive_rename example rename-locked --name 'Unlocked Doc' --expect "$(preview_hash "$WORK/preview")" --execute
grep -F 'cannot rename this item' "$WORK/failure-error" >/dev/null
no_write
for residual in "$WORK/temp"/google-drive.* "$WORK"/.google-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Drive failure preservation, path safety, export bounds, import and rename gates, rename readback, and cleanup passed'
