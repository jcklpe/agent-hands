#!/usr/bin/env bash
##- Offline regression checks for snapshot replacement, pipeline errors, and partially completed links.
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRELLO_AUTH_DIR="$(cd "$HERE/../../authorize-trello" && pwd)"
. "$TRELLO_AUTH_DIR/scripts/client.sh"
. "$HERE/../scripts/operations.sh"
. "$HERE/../scripts/export.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/trello-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT
TRELLO_API_KEY=synthetic TRELLO_TOKEN=synthetic TRELLO_WRITE_TOKEN=synthetic TRELLO_BOARD_IDS=board1
mode=success
_trello_get() {
    case "$1" in
        /boards/board1)
            [ "$mode" != board ] || return 1
            printf '{"name":"Example","url":"https://trello.com/b/example"}' ;;
        /boards/board1/lists)
            [ "$mode" != lists ] || return 1
            printf '[{"id":"list1","name":"Work"}]' ;;
        /boards/board1/cards/open)
            [ "$mode" != cards ] || return 1
            printf '[{"id":"card1","idList":"list1","name":"Example card"}]' ;;
        /boards/board1/actions)
            [ "$mode" != comments ] || return 1
            if [ "$mode" = malformed ]; then printf '{'; return; fi
            if [ "$mode" = second-page ] || [ "$mode" = stalled ]; then
                if [ "$mode" = second-page ] && [ "$#" -gt 9 ]; then return 1; fi
                jq -n '[range(0;1000) | {id:("action" + tostring),date:"2026-01-01",data:{card:{id:"card1"},text:"Example"}}]'
            elif [ "$mode" = cap ]; then
                printf x >> "$work/page-count"
                jq -n --arg cursor "page$(wc -c < "$work/page-count" | tr -d ' ')" '[range(0;1000) | {id:$cursor,date:"2026-01-01",data:{card:{id:"card1"}}}]'
            else printf '[]'; fi ;;
        /members/me/boards) return 1 ;;
        *) printf 'Unexpected request\n' >&2; return 1 ;;
    esac
}
for mode in board lists cards comments malformed second-page stalled cap; do
    printf 'previous export' > "$work/export.md"
    if _trello_export --output "$work/export.md" > "$work/stdout" 2> "$work/stderr"; then echo "FAIL: $mode reported success"; exit 1; fi
    [ "$(cat "$work/export.md")" = 'previous export' ] || { echo "FAIL: $mode replaced prior export"; exit 1; }
    if grep -q 'Updated' "$work/stdout"; then echo "FAIL: $mode printed success"; exit 1; fi
done
mode=success
_trello_export --output "$work/export.md" > "$work/stdout"
grep -q 'Example card' "$work/export.md"
if _trello_list_boards > /dev/null; then echo 'FAIL: read pipeline swallowed HTTP failure'; exit 1; fi
_trello_write() { return 1; }
if _trello_rename_card --card card1 --name Example > /dev/null; then echo 'FAIL: write pipeline swallowed HTTP failure'; exit 1; fi

mode=partial
_trello_get() {
    case "$1" in
        /cards/source|/cards/aaaaaaaaaaaaaaaaaaaaaaaa) printf '{"id":"aaaaaaaaaaaaaaaaaaaaaaaa","url":"https://trello.com/c/source"}' ;;
        /cards/target|/cards/bbbbbbbbbbbbbbbbbbbbbbbb) printf '{"id":"bbbbbbbbbbbbbbbbbbbbbbbb","url":"https://trello.com/c/target"}' ;;
        */actions)
            [ "$mode" != failed-lookup ] || return 1
            printf '[]' ;;
        *) return 1 ;;
    esac
}
_trello_write() {
    printf '%s %s\n' "$1" "$2" >> "$work/writes"
    case "$2" in /cards/aaaaaaaaaaaaaaaaaaaaaaaa/actions/comments) return 1 ;; esac
    printf '{}'
}
: > "$work/writes"
if _trello_supersede --from source --to target > "$work/stdout" 2> "$work/stderr"; then echo 'FAIL: partial link reported success'; exit 1; fi
grep -q 'PARTIAL' "$work/stderr"
grep -q 'without --create' "$work/stderr"
[ "$(wc -l < "$work/writes" | tr -d ' ')" = 2 ]
: > "$work/writes"
if _trello_supersede --from source --to aaaaaaaaaaaaaaaaaaaaaaaa > /dev/null 2>&1; then echo 'FAIL: self-link via alternate reference'; exit 1; fi
[ ! -s "$work/writes" ]
mode=failed-lookup
if _trello_supersede --from source --to target > /dev/null 2>&1; then echo 'FAIL: failed lookup was treated as no existing link'; exit 1; fi
[ ! -s "$work/writes" ]
printf 'ok: export failures preserve old snapshots; link failures are explicit\n'
