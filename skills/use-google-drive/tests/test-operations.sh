#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-google/scripts/client.sh"
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
    if [ "${FAIL_LIST:-0}" = 1 ]; then printf '%s' '{"error":{"code":403}}'; return; fi
    case "$url" in
        */files/synthetic-file) jq -n --arg name "${REMOTE_NAME:-example.txt}" '{id:"synthetic-file",name:$name,mimeType:"text/plain"}' ;;
        */files)
            case "$query" in
                *"'root' in parents"*) printf '%s' '{"files":[{"id":"folder-one","name":"Example Folder","mimeType":"application/vnd.google-apps.folder"}],"nextPageToken":"more-folders"}' ;;
                *"'folder-one' in parents"*)
                    [ "${FAIL_CHILDREN:-0}" = 0 ] || return 1
                    printf '%s' '{"files":[{"id":"child-one","name":"Example Child","mimeType":"text/plain"}]}' ;;
                *) printf '%s' '{"files":[]}' ;;
            esac ;;
        *) return 1 ;;
    esac
}
curl() {
    local out="" arg previous=""
    printf '%s\n' called >> "$WORK/curl-calls"
    for arg in "$@"; do
        [ "$previous" != -o ] || out="$arg"
        previous="$arg"
    done
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
for residual in "$WORK/temp"/google-drive.* "$WORK"/.google-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Drive failure preservation, path safety, export bounds, import gates, and cleanup passed'
