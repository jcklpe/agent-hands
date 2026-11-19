#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/../setup-google-services/scripts/client.sh"
source "$ROOT/scripts/operations.sh"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
_google_python() { shift; python3 "$@"; }
_drive_write_enabled() { [ "${WRITE:-1}" = 1 ]; }
_google_access_token() { printf synthetic; }
_drive_rename_siblings() { [ "${DUP:-0}" = 0 ] || printf existing; }
_google_get_url() {
 case "$2" in
 */folder) printf '{"id":"folder","name":"Archive","mimeType":"application/vnd.google-apps.folder","capabilities":{"canAddChildren":true}}' ;;
 */created) jq --arg md5 "${BAD_MD5:-$(jq -r .md5 "$DRIVE_WORK/upload.plan")}" '. + {id:"created",parents:[.folder],md5Checksum:$md5}' "$DRIVE_WORK/upload.plan" ;;
 esac
}
curl() {
 local last='' out=''
 for arg in "$@"; do [ "$last" != -o ] || out="$arg"; last="$arg"; done
 printf call >> "$WORK/posts"
 printf '{"id":"created"}' > "$out"; printf 200
}
fail() { if "$@" > "$WORK/out" 2> "$WORK/err"; then echo 'Expected refusal'; exit 1; fi; }
printf 'original bytes' > "$WORK/sample.pdf"
_drive_upload example "$WORK/sample.pdf" --folder folder > "$WORK/preview"
[ ! -f "$WORK/posts" ]
hash="$(sed -n 's/Preview SHA-256: //p' "$WORK/preview")"
fail _drive_upload example "$WORK/sample.pdf" --folder folder --execute
[ ! -f "$WORK/posts" ]
printf 'changed' >> "$WORK/sample.pdf"
fail _drive_upload example "$WORK/sample.pdf" --folder folder --expect "$hash" --execute
[ ! -f "$WORK/posts" ]
printf 'original bytes' > "$WORK/sample.pdf"
DUP=1 fail _drive_upload example "$WORK/sample.pdf" --folder folder --expect "$hash" --execute
WRITE=0 fail _drive_upload example "$WORK/sample.pdf" --folder folder --expect "$hash" --execute
[ ! -f "$WORK/posts" ]
_drive_upload example "$WORK/sample.pdf" --folder folder --expect "$hash" --execute > "$WORK/result"
grep -q 'Created ID: created' "$WORK/result"
BAD_MD5=wrong fail _drive_upload example "$WORK/sample.pdf" --folder folder --expect "$hash" --execute
grep -q 'readback mismatch' "$WORK/err"
echo 'Upload guard and readback tests passed'
