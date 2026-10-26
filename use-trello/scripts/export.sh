#!/usr/bin/env bash
##- Explicit, all-or-nothing local snapshot replacement; failed or incomplete reads preserve the previous file.
_trello_export() (
    set -o pipefail
    local output="" work="" temporary="" board_ids board_id board_name board_url refreshed
    local page_index count before_cursor next_cursor
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output) [ -n "${2:-}" ] || { _trello_error '--output requires FILE'; return 1; }; output="$2"; shift 2 ;;
            *) _trello_error "Unknown export option: $1"; return 1 ;;
        esac
    done
    [ -n "$output" ] || { _trello_error 'export requires --output FILE'; return 1; }
    _trello_ready || return 1
    _trello_require_var TRELLO_BOARD_IDS || return 1
    board_ids="$(printf '%s' "$TRELLO_BOARD_IDS" | tr ',' ' ')"
    case "$board_ids" in *[!A-Za-z0-9\ ]*) _trello_error 'Board IDs must be alphanumeric, separated by commas'; return 1 ;; esac
    [ -n "$(_trello_trim "$board_ids")" ] || { _trello_error 'No board IDs selected'; return 1; }
    mkdir -p "$(dirname "$output")" || return 1
    temporary="$(mktemp "$(dirname "$output")/.$(basename "$output").XXXXXX")" || return 1
    trap 'rm -f "$temporary"; [ -z "$work" ] || rm -rf "$work"' EXIT
    trap 'exit 130' HUP INT TERM
    work="$(mktemp -d "${TMPDIR:-/tmp}/trello-export.XXXXXX")" || return 1
    refreshed="$(date -u '+%Y-%m-%d %H:%M:%S UTC')" || return 1
    printf '# Trello\n\nLast refreshed: %s\n\nSynced board IDs: `%s`\n\n' "$refreshed" "$TRELLO_BOARD_IDS" > "$temporary" || return 1
    for board_id in $board_ids; do
        _trello_get "/boards/${board_id}" --data-urlencode 'fields=name,url' > "$work/board.json" || { _trello_error 'Board metadata retrieval failed; previous export preserved'; return 1; }
        jq -e 'type == "object" and (.name | type == "string")' "$work/board.json" >/dev/null || { _trello_error 'Invalid board metadata; previous export preserved'; return 1; }
        _trello_get "/boards/${board_id}/lists" --data-urlencode 'filter=open' --data-urlencode 'fields=name' > "$work/lists.json" || return 1
        _trello_get "/boards/${board_id}/cards/open" --data-urlencode 'fields=name,idList,start,due,url,labels,desc,dateLastActivity' --data-urlencode 'checklists=all' > "$work/cards.json" || return 1
        jq -e 'type == "array"' "$work/lists.json" >/dev/null && jq -e 'type == "array"' "$work/cards.json" >/dev/null || { _trello_error 'Invalid lists/cards response; previous export preserved'; return 1; }
        printf '[]' > "$work/actions.json" || return 1
        before_cursor=""
        page_index=0
        while [ "$page_index" -lt 30 ]; do
            if [ -n "$before_cursor" ]; then
                _trello_get "/boards/${board_id}/actions" --data-urlencode 'filter=commentCard' --data-urlencode 'limit=1000' --data-urlencode 'memberCreator=true' --data-urlencode 'memberCreator_fields=fullName,username' --data-urlencode "before=${before_cursor}" > "$work/page.json" || { _trello_error 'Comment retrieval failed; previous export preserved'; return 1; }
            else
                _trello_get "/boards/${board_id}/actions" --data-urlencode 'filter=commentCard' --data-urlencode 'limit=1000' --data-urlencode 'memberCreator=true' --data-urlencode 'memberCreator_fields=fullName,username' > "$work/page.json" || { _trello_error 'Comment retrieval failed; previous export preserved'; return 1; }
            fi
            jq -e 'type == "array"' "$work/page.json" >/dev/null || { _trello_error 'Invalid comments response; previous export preserved'; return 1; }
            count="$(jq 'length' "$work/page.json")" || return 1
            jq -s '.[0] + .[1]' "$work/actions.json" "$work/page.json" > "$work/combined.json" && mv "$work/combined.json" "$work/actions.json" || return 1
            [ "$count" -lt 1000 ] && break
            next_cursor="$(jq -er '.[-1].id | select(type == "string" and length > 0)' "$work/page.json")" || { _trello_error 'Missing comment cursor; previous export preserved'; return 1; }
            [ "$next_cursor" != "$before_cursor" ] || { _trello_error 'Comment cursor did not advance; previous export preserved'; return 1; }
            before_cursor="$next_cursor"
            page_index=$((page_index + 1))
        done
        [ "$page_index" -lt 30 ] || { _trello_error 'Comment history exceeds 30 pages; previous export preserved'; return 1; }
        jq --slurpfile acts "$work/actions.json" '($acts[0] | map(select(.data.card.id != null)) | group_by(.data.card.id) | map({key: (.[0].data.card.id), value: .}) | from_entries) as $bycard | map(. + {actions: ($bycard[.id] // [])})' "$work/cards.json" > "$work/merged.json" || return 1
        board_name="$(jq -r '.name' "$work/board.json")" || return 1
        board_url="$(jq -r '.url // ""' "$work/board.json")" || return 1
        printf '## %s\n\n%s\n\n' "$board_name" "$board_url" >> "$temporary" || return 1
        _trello_render_cards "$work/lists.json" "$work/merged.json" >> "$temporary" || { _trello_error 'Rendering failed; previous export preserved'; return 1; }
        printf '\n' >> "$temporary" || return 1
    done
    mv "$temporary" "$output" || return 1
    _trello_say "Updated $output"
)
