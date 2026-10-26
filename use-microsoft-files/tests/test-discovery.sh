#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
source "$SKILL/../setup-microsoft-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
M365_PYTHON="${M365_PYTHON:-python3}"
export M365_CONFIG_DIR="$WORK"
jq '.accounts[0].files.enabled=true' "$SKILL/../setup-microsoft-services/m365-powershell-accounts.example.json" > "$WORK/m365-accounts.json"
FILES_SEARCH_OUT="$WORK/search"; FILES_META_OUT="$WORK/meta"; FILES_LINK_OUT="$WORK/link"
_m365_get() {
    case "$2" in
        *"/root/search("*) printf '%s\n' '{"value":[{"id":"item-1","name":"Team work plan.docx","size":1234,"lastModifiedDateTime":"2026-09-19T12:00:00Z","webUrl":"https://example.sharepoint.com/work-plan","file":{"mimeType":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},"parentReference":{"driveId":"drive-1","path":"/drives/drive-1/root:/General"}}]}' ;;
        *"/shares/"*) printf '%s\n' '{"id":"item-1","name":"Team work plan.docx","size":1234,"lastModifiedDateTime":"2026-09-19T12:00:00Z","webUrl":"https://example.sharepoint.com/work-plan","file":{"mimeType":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},"parentReference":{"driveId":"drive-1","path":"/drives/drive-1/root:/General"}}' ;;
        *"/drives/drive-1/items/item-1") printf '%s\n' '{"id":"item-1","name":"Team work plan.docx","size":1234,"lastModifiedDateTime":"2026-09-19T12:00:00Z","webUrl":"https://example.sharepoint.com/work-plan","file":{"mimeType":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},"parentReference":{"driveId":"drive-1","path":"/drives/drive-1/root:/General"}}' ;;
        *) return 1 ;;
    esac
}
_m365_files_search example Team --drive drive-1 > "$FILES_SEARCH_OUT"
grep -F -- "item_id: item-1" "$FILES_SEARCH_OUT" >/dev/null
grep -F -- "drive_id: drive-1" "$FILES_SEARCH_OUT" >/dev/null
_m365_files_meta example item-1 --drive drive-1 > "$FILES_META_OUT"
grep -F -- "path: /drives/drive-1/root:/General/Team work plan.docx" "$FILES_META_OUT" >/dev/null
_m365_files_resolve_link example 'https://example.sharepoint.com/:w:/r/sites/connect/work-plan' > "$FILES_LINK_OUT"
grep -F -- "drive_id: drive-1" "$FILES_LINK_OUT" >/dev/null

printf 'm365 shell pagination, find, and file fixtures passed\n'
