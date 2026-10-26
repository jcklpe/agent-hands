#!/usr/bin/env bash
##- Bounded operation builders. The CLI captures their requests into a preview before execution.

_trello_first_board_id() (
    set -o pipefail
    local first
    first="${TRELLO_BOARD_IDS:-}"
    first="${first%%,*}"
    _trello_trim "$first"
)

_trello_looks_like_id() (
    set -o pipefail
    case "$1" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f])
            return 0
            ;;
    esac
    return 1
)

_trello_card_ref() (
    set -o pipefail
    local ref="$1"
    case "$ref" in
        *trello.com/c/*)
            ref="${ref#*trello.com/c/}"
            ref="${ref%%/*}"
            ;;
    esac
    printf '%s\n' "$ref"
)

_trello_read_file() (
    set -o pipefail
    if [ ! -f "$1" ]; then
        _trello_error "File does not exist: $1"
        return 1
    fi
    cat "$1"
)

_trello_list_boards() (
    set -o pipefail
    _trello_ready || return 1
    _trello_get "/members/me/boards" \
        --data-urlencode "fields=name,url,closed" |
        jq -r '.[] | "- " + (.name // "Untitled board") + " | id: " + .id + " | closed: " + (.closed | tostring) + " | " + (.url // "")'
)

_trello_list_lists() (
    set -o pipefail
    local board_id="${1:-}"

    _trello_ready || return 1
    if [ -z "$board_id" ]; then
        board_id="$(_trello_first_board_id)"
    fi
    if [ -z "$board_id" ]; then
        _trello_error "Pass a board ID or set TRELLO_BOARD_IDS"
        return 1
    fi

    _trello_get "/boards/${board_id}/lists" \
        --data-urlencode "filter=all" \
        --data-urlencode "fields=name,closed" |
        jq -r '.[] | "- " + (.name // "Untitled list") + " | id: " + .id + " | closed: " + (.closed | tostring)'
)

_trello_resolve_list_id() (
    set -o pipefail
    local board_id="$1"
    local list_ref="$2"
    local matches

    if [ -z "$list_ref" ]; then
        _trello_error "Missing list"
        return 1
    fi

    if _trello_looks_like_id "$list_ref"; then
        printf '%s\n' "$list_ref"
        return 0
    fi

    if [ -z "$board_id" ]; then
        board_id="$(_trello_first_board_id)"
    fi
    if [ -z "$board_id" ]; then
        _trello_error "List names require --board or TRELLO_BOARD_IDS"
        return 1
    fi

    matches="$(
        _trello_get "/boards/${board_id}/lists" \
            --data-urlencode "filter=open" \
            --data-urlencode "fields=name" |
            jq -r --arg name "$list_ref" '.[] | select(.name == $name) | .id'
    )" || return 1

    if [ -z "$matches" ]; then
        _trello_error "No open list named '$list_ref' found on board $board_id"
        return 1
    fi

    if [ "$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')" != "1" ]; then
        _trello_error "Multiple open lists named '$list_ref' found on board $board_id; use the list ID"
        return 1
    fi

    printf '%s\n' "$matches"
)

##- Board label operations; workflow conventions belong to the consumer.
_trello_list_labels() (
    set -o pipefail
    local board_id="${1:-}"

    _trello_ready || return 1
    if [ -z "$board_id" ]; then
        board_id="$(_trello_first_board_id)"
    fi
    if [ -z "$board_id" ]; then
        _trello_error "Pass a board ID or set TRELLO_BOARD_IDS"
        return 1
    fi

    _trello_get "/boards/${board_id}/labels" \
        --data-urlencode "fields=name,color" \
        --data-urlencode "limit=1000" |
        jq -r '.[] | "- " + (if (.name // "") == "" then "(unnamed)" else .name end) + " | id: " + .id + " | color: " + (.color // "none")'
)

# Resolve a label reference (24-hex id, or an exact label name on the board) to a label id.
_trello_resolve_label_id() (
    set -o pipefail
    local board_id="$1"
    local label_ref="$2"
    local matches

    if [ -z "$label_ref" ]; then
        _trello_error "Missing label"
        return 1
    fi

    if _trello_looks_like_id "$label_ref"; then
        printf '%s\n' "$label_ref"
        return 0
    fi

    if [ -z "$board_id" ]; then
        board_id="$(_trello_first_board_id)"
    fi
    if [ -z "$board_id" ]; then
        _trello_error "Label names require --board or TRELLO_BOARD_IDS"
        return 1
    fi

    matches="$(
        _trello_get "/boards/${board_id}/labels" \
            --data-urlencode "fields=name" \
            --data-urlencode "limit=1000" |
            jq -r --arg name "$label_ref" 'if type != "array" or length >= 1000 then error("Incomplete label lookup") else .[] | select(.name == $name) | .id end'
    )" || return 1

    if [ -z "$matches" ]; then
        _trello_error "No label named '$label_ref' found on board $board_id"
        return 1
    fi
    if [ "$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')" != "1" ]; then
        _trello_error "Multiple labels named '$label_ref' found on board $board_id; use the label ID"
        return 1
    fi
    printf '%s\n' "$matches"
)

_trello_create_label() (
    set -o pipefail
    local board_id="" name="" color=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            --color) color="$2"; shift 2 ;;
            *) _trello_error "Unknown create-label option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$name" ] || { _trello_error "create-label requires --name"; return 1; }
    if [ -z "$board_id" ]; then
        board_id="$(_trello_first_board_id)"
    fi
    [ -n "$board_id" ] || { _trello_error "create-label requires --board or TRELLO_BOARD_IDS"; return 1; }
    # Trello label colors: 10 hues, each also with a _light and _dark shade (30 total), or empty for colorless.
    case "$color" in
        "") : ;;
        green|yellow|orange|red|purple|blue|sky|lime|pink|black) : ;;
        green_light|yellow_light|orange_light|red_light|purple_light|blue_light|sky_light|lime_light|pink_light|black_light) : ;;
        green_dark|yellow_dark|orange_dark|red_dark|purple_dark|blue_dark|sky_dark|lime_dark|pink_dark|black_dark) : ;;
        *) _trello_error "create-label --color must be a Trello color (e.g. green, green_dark, sky_light) or omitted; hues: green yellow orange red purple blue sky lime pink black, each with optional _light/_dark"; return 1 ;;
    esac

    _trello_write POST "/labels" \
        --data-urlencode "idBoard=${board_id}" \
        --data-urlencode "name=${name}" \
        --data-urlencode "color=${color}" |
        jq -r '"Created label: " + (.name // "(unnamed)") + " | id: " + .id + " | color: " + (.color // "none")'
)

_trello_add_label() (
    set -o pipefail
    local board_id="" card="" label_ref="" label_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --label) label_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown add-label option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "add-label requires --card"; return 1; }
    [ -n "$label_ref" ] || { _trello_error "add-label requires --label"; return 1; }

    label_id="$(_trello_resolve_label_id "$board_id" "$label_ref")" || return 1
    _trello_write POST "/cards/${card}/idLabels" \
        --data-urlencode "value=${label_id}" >/dev/null \
        || { _trello_error "Failed to add label ${label_ref} to card ${card}"; return 1; }
    _trello_say "Added label ${label_ref} to card ${card}"
)

_trello_remove_label() (
    set -o pipefail
    local board_id="" card="" label_ref="" label_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --label) label_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown remove-label option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "remove-label requires --card"; return 1; }
    [ -n "$label_ref" ] || { _trello_error "remove-label requires --label"; return 1; }

    label_id="$(_trello_resolve_label_id "$board_id" "$label_ref")" || return 1
    _trello_write DELETE "/cards/${card}/idLabels/${label_id}" >/dev/null \
        || { _trello_error "Failed to remove label ${label_ref} from card ${card}"; return 1; }
    _trello_say "Removed label ${label_ref} from card ${card}"
)

# Board-wide label deletion removes it from every card carrying it.
_trello_delete_label() (
    set -o pipefail
    local board_id="" label_ref="" label_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --label) label_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown delete-label option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$label_ref" ] || { _trello_error "delete-label requires --label"; return 1; }

    label_id="$(_trello_resolve_label_id "$board_id" "$label_ref")" || return 1
    _trello_write DELETE "/labels/${label_id}" >/dev/null \
        || { _trello_error "Failed to delete label ${label_ref} (id ${label_id})"; return 1; }
    _trello_say "Deleted label ${label_ref} (id ${label_id}) board-wide"
)

_trello_add_card() (
    set -o pipefail
    local board_id="" list_ref="" name="" desc="" desc_file="" list_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --list) list_ref="$2"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            --desc) desc="$2"; shift 2 ;;
            --desc-file) desc_file="$2"; shift 2 ;;
            *) _trello_error "Unknown add-card option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$list_ref" ] || { _trello_error "add-card requires --list"; return 1; }
    [ -n "$name" ] || { _trello_error "add-card requires --name"; return 1; }
    if [ -n "$desc" ] && [ -n "$desc_file" ]; then
        _trello_error "Use either --desc or --desc-file, not both"
        return 1
    fi
    if [ -n "$desc_file" ]; then
        desc="$(_trello_read_file "$desc_file")" || return 1
    fi

    list_id="$(_trello_resolve_list_id "$board_id" "$list_ref")" || return 1
    _trello_write POST "/cards" \
        --data-urlencode "idList=${list_id}" \
        --data-urlencode "name=${name}" \
        --data-urlencode "desc=${desc}" |
        jq -r '"Created card: " + (.name // "Untitled card") + " | " + (.url // .id)'
)

_trello_move_card() (
    set -o pipefail
    local board_id="" card="" list_ref="" list_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --list) list_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown move-card option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "move-card requires --card"; return 1; }
    [ -n "$list_ref" ] || { _trello_error "move-card requires --list"; return 1; }

    list_id="$(_trello_resolve_list_id "$board_id" "$list_ref")" || return 1
    _trello_write PUT "/cards/${card}" \
        --data-urlencode "idList=${list_id}" |
        jq -r '"Moved card: " + (.name // "Untitled card") + " | " + (.url // .id)'
)

##- Move a card to an explicit list and set its native start date. No scheduler or reactivation rule is installed.
_trello_schedule_card() (
    set -o pipefail
    local board_id="" card="" until_date="" list_ref="${TRELLO_SNOOZE_DEFAULT_LIST:-}" list_id start_iso

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --board) board_id="$2"; shift 2 ;;
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --until) until_date="$2"; shift 2 ;;
            --list) list_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown schedule-card option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "schedule-card requires --card"; return 1; }
    [ -n "$list_ref" ] || { _trello_error "schedule-card requires --list"; return 1; }
    [ -n "$until_date" ] || { _trello_error "schedule-card requires --until YYYY-MM-DD"; return 1; }
    case "$until_date" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) : ;;
        *) _trello_error "schedule-card --until must be an ISO date YYYY-MM-DD (got '$until_date')"; return 1 ;;
    esac

    printf '%s\n' "$until_date" | awk -F- '{ y=$1+0; m=$2+0; d=$3+0; days=31; if(m==4 || m==6 || m==9 || m==11) days=30; if(m==2) days=28+((y%4==0 && y%100!=0)||y%400==0); exit !(y>=1 && m>=1 && m<=12 && d>=1 && d<=days) }' || { _trello_error 'schedule-card --until must be a real calendar date'; return 1; }
    list_id="$(_trello_resolve_list_id "$board_id" "$list_ref")" || return 1
    # Date-only scheduling preserves the existing noon-UTC convention; it does not create a wake automation.
    start_iso="${until_date}T12:00:00.000Z"
    _trello_write PUT "/cards/${card}" \
        --data-urlencode "idList=${list_id}" \
        --data-urlencode "start=${start_iso}" |
        jq -r --arg d "$until_date" \
            '"Scheduled card: " + (.name // "Untitled card") + " until " + $d + " | " + (.url // .id)'
)

_trello_rename_card() (
    set -o pipefail
    local card="" name=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            *) _trello_error "Unknown rename-card option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "rename-card requires --card"; return 1; }
    [ -n "$name" ] || { _trello_error "rename-card requires --name"; return 1; }

    _trello_write PUT "/cards/${card}" \
        --data-urlencode "name=${name}" |
        jq -r '"Renamed card: " + (.name // "Untitled card") + " | " + (.url // .id)'
)

_trello_set_desc() (
    set -o pipefail
    local card="" file="" desc

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --file) file="$2"; shift 2 ;;
            *) _trello_error "Unknown set-desc option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "set-desc requires --card"; return 1; }
    [ -n "$file" ] || { _trello_error "set-desc requires --file"; return 1; }
    desc="$(_trello_read_file "$file")" || return 1

    _trello_write PUT "/cards/${card}" \
        --data-urlencode "desc=${desc}" |
        jq -r '"Updated description: " + (.name // "Untitled card") + " | " + (.url // .id)'
)

_trello_comment() (
    set -o pipefail
    local card="" text="" file=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --text) text="$2"; shift 2 ;;
            --file) file="$2"; shift 2 ;;
            *) _trello_error "Unknown comment option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "comment requires --card"; return 1; }
    if [ -n "$text" ] && [ -n "$file" ]; then
        _trello_error "Use either --text or --file, not both"
        return 1
    fi
    if [ -n "$file" ]; then
        text="$(_trello_read_file "$file")" || return 1
    fi
    [ -n "$text" ] || { _trello_error "comment requires --text or --file"; return 1; }

    _trello_write POST "/cards/${card}/actions/comments" \
        --data-urlencode "text=${text}" |
        jq -r '"Added comment at " + (.date // "unknown date")'
)

##- Checklists: create a checklist, add items, and tick or untick items. Names resolve against the card's own checklists; an ambiguous or missing name fails and lists the candidates .

# Resolve a checklist reference (24-hex id, or an exact checklist name on the card) to a checklist id.
_trello_resolve_checklist_id() (
    set -o pipefail
    local card="$1" checklist_ref="$2" checklists matches count

    [ -n "$checklist_ref" ] || { _trello_error "Missing checklist"; return 1; }
    if _trello_looks_like_id "$checklist_ref"; then
        printf '%s\n' "$checklist_ref"
        return 0
    fi

    checklists="$(_trello_get "/cards/${card}/checklists" --data-urlencode "fields=name")" || return 1
    matches="$(printf '%s' "$checklists" | jq -r --arg name "$checklist_ref" '.[] | select(.name == $name) | .id')"
    count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$count" = "0" ]; then
        _trello_error "No checklist named '$checklist_ref' on card ${card}. Checklists: $(printf '%s' "$checklists" | jq -r '[.[].name] | if length == 0 then "(none)" else join(", ") end')"
        return 1
    fi
    if [ "$count" != "1" ]; then
        _trello_error "Multiple checklists named '$checklist_ref' on card ${card}; use the checklist ID: $(printf '%s\n' "$matches" | paste -sd ' ' -)"
        return 1
    fi
    printf '%s\n' "$matches"
)

# Resolve a check-item reference (24-hex id, or an exact item name) on a card to "<item id>\t<item name>".
# --checklist narrows the search to one checklist; otherwise every checklist on the card is searched.
_trello_resolve_check_item() (
    set -o pipefail
    local card="$1" item_ref="$2" checklist_ref="$3" checklist_id="" checklists matches count

    [ -n "$item_ref" ] || { _trello_error "Missing item"; return 1; }
    if [ -n "$checklist_ref" ]; then
        checklist_id="$(_trello_resolve_checklist_id "$card" "$checklist_ref")" || return 1
    fi

    checklists="$(_trello_get "/cards/${card}/checklists" --data-urlencode "checkItem_fields=name,state")" || return 1
    matches="$(
        printf '%s' "$checklists" |
            jq -r --arg ref "$item_ref" --arg cl "$checklist_id" '
              .[] | select($cl == "" or .id == $cl) | .name as $list
              | (.checkItems // [])[] | select(.id == $ref or .name == $ref)
              | .id + "\t" + .name + "\t" + $list'
    )"
    count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$count" = "0" ]; then
        _trello_error "No checklist item '$item_ref' on card ${card}$([ -n "$checklist_ref" ] && printf ' in checklist %s' "$checklist_ref")"
        return 1
    fi
    if [ "$count" != "1" ]; then
        _trello_error "Multiple checklist items match '$item_ref' on card ${card}; pass --checklist or the item ID:"
        printf '%s\n' "$matches" | awk -F '\t' '{ printf "  - %s (in %s)\n", $1, $3 }' >&2
        return 1
    fi
    printf '%s\n' "$matches" | cut -f1,2
)

# Full 24-hex card ID for a card reference. Most card endpoints accept a short link, but POST /checklists
# rejects one in idCard with a 400, so creation resolves it first.
_trello_card_id() (
    set -o pipefail
    local card="$1" card_id
    if _trello_looks_like_id "$card"; then
        printf '%s\n' "$card"
        return 0
    fi
    card_id="$(_trello_get "/cards/${card}" --data-urlencode "fields=id" | jq -r '.id // empty')" || true
    [ -n "$card_id" ] || { _trello_error "Could not resolve card ${card} to a card ID"; return 1; }
    printf '%s\n' "$card_id"
)

_trello_add_checklist_items() (
    set -o pipefail
    local checklist_id="$1"
    shift
    local item
    for item in "$@"; do
        _trello_write POST "/checklists/${checklist_id}/checkItems" \
            --data-urlencode "name=${item}" \
            --data-urlencode "pos=bottom" >/dev/null \
            || { _trello_error "Failed to add item '${item}' to checklist ${checklist_id}"; return 1; }
        _trello_say "  Added item: ${item}"
    done
)

_trello_add_checklist() (
    set -o pipefail
    local card="" name="" checklist_id
    local items=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            --item) items+=("$2"); shift 2 ;;
            *) _trello_error "Unknown add-checklist option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "add-checklist requires --card"; return 1; }
    [ -n "$name" ] || { _trello_error "add-checklist requires --name"; return 1; }
    card="$(_trello_card_id "$card")" || return 1

    checklist_id="$(
        _trello_write POST "/checklists" \
            --data-urlencode "idCard=${card}" \
            --data-urlencode "name=${name}" \
            --data-urlencode "pos=bottom" | jq -r '.id // empty'
    )"
    [ -n "$checklist_id" ] || { _trello_error "Failed to create checklist '${name}' on card ${card}"; return 1; }
    _trello_say "Created checklist: ${name} | id: ${checklist_id} | card: ${card}"
    [ "${#items[@]}" -eq 0 ] || _trello_add_checklist_items "$checklist_id" "${items[@]}"
)

_trello_add_checklist_item() (
    set -o pipefail
    local card="" checklist_ref="" checklist_id
    local items=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --checklist) checklist_ref="$2"; shift 2 ;;
            --text) items+=("$2"); shift 2 ;;
            *) _trello_error "Unknown add-checklist-item option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "add-checklist-item requires --card"; return 1; }
    [ -n "$checklist_ref" ] || { _trello_error "add-checklist-item requires --checklist"; return 1; }
    [ "${#items[@]}" -gt 0 ] || { _trello_error "add-checklist-item requires --text"; return 1; }

    checklist_id="$(_trello_resolve_checklist_id "$card" "$checklist_ref")" || return 1
    _trello_say "Checklist ${checklist_ref} (${checklist_id}) on card ${card}:"
    _trello_add_checklist_items "$checklist_id" "${items[@]}"
)

# Shared body of check-item / uncheck-item. $1 is the Trello state to set: complete or incomplete.
_trello_set_check_item_state() (
    set -o pipefail
    local state="$1" command="$2"
    shift 2
    local card="" item_ref="" checklist_ref="" resolved item_id item_name

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --item) item_ref="$2"; shift 2 ;;
            --checklist) checklist_ref="$2"; shift 2 ;;
            *) _trello_error "Unknown ${command} option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$card" ] || { _trello_error "${command} requires --card"; return 1; }
    [ -n "$item_ref" ] || { _trello_error "${command} requires --item"; return 1; }

    resolved="$(_trello_resolve_check_item "$card" "$item_ref" "$checklist_ref")" || return 1
    item_id="$(printf '%s' "$resolved" | cut -f1)"
    item_name="$(printf '%s' "$resolved" | cut -f2)"
    _trello_write PUT "/cards/${card}/checkItem/${item_id}" \
        --data-urlencode "state=${state}" >/dev/null \
        || { _trello_error "Failed to set item '${item_name}' to ${state}"; return 1; }
    _trello_say "Set ${state}: ${item_name} | card: ${card}"
)

_trello_check_item() ( set -o pipefail; _trello_set_check_item_state complete check-item "$@"; )
_trello_uncheck_item() ( set -o pipefail; _trello_set_check_item_state incomplete uncheck-item "$@"; )

##- Neutral bidirectional links and traversal, stored as labeled comments.

# Most-recent comment text on a card whose text contains the given label, or empty.
_trello_link_comment() (
    set -o pipefail
    local card="$1" label="$2" actions
    actions="$(_trello_get "/cards/${card}/actions" --data-urlencode 'filter=commentCard' --data-urlencode 'limit=1000')" || return 1
    printf '%s' "$actions" | jq -r --arg label "$label" '
        if type != "array" then error("Invalid comments response")
        elif length >= 1000 then error("Comment lookup hit its 1000-comment cap; refusing an incomplete link check")
        else [.[] | select((.data.text // "") | contains($label))] | sort_by(.date) | reverse | (.[0].data.text // "") end'
)

# Card id referenced by the most-recent labeled link comment on a card, or empty.
_trello_link_target() (
    set -o pipefail
    local card="$1" label="$2" text rest
    text="$(_trello_link_comment "$card" "$label")" || return 1
    [ -n "$text" ] || return 0
    rest="${text#*"$label"}"
    rest="$(_trello_trim "$rest")"
    [ -n "$rest" ] || return 0
    _trello_card_ref "$rest"
)

# Append a link comment unless an equivalent one already targets the counterpart.
# Args: card_id label target_id target_url
_trello_write_link() (
    set -o pipefail
    local card="$1" label="$2" target_id="$3" target_url="$4" existing
    existing="$(_trello_link_comment "$card" "$label")" || return 1
    [ -n "$target_id" ] && [ -n "$target_url" ] || { _trello_error 'A link needs a confirmed target ID and URL'; return 1; }
    case "$existing" in
        *"$target_id"*|*"$target_url"*) _trello_say "  link already present on ${card}: ${label} ${target_url} (skipped)"; return 0 ;;
    esac
    _trello_write POST "/cards/${card}/actions/comments" \
        --data-urlencode "text=🔗 ${label} ${target_url}" >/dev/null
)

_trello_supersede() (
    set -o pipefail
    local from="" to="" do_create="" board="" list_ref="" name="" desc="" desc_file=""
    local from_json from_url to_json to_url created list_id

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --from) from="$(_trello_card_ref "$2")"; shift 2 ;;
            --to) to="$(_trello_card_ref "$2")"; shift 2 ;;
            --create) do_create=1; shift ;;
            --board) board="$2"; shift 2 ;;
            --list) list_ref="$2"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            --desc) desc="$2"; shift 2 ;;
            --desc-file) desc_file="$2"; shift 2 ;;
            *) _trello_error "Unknown supersede option: $1"; return 1 ;;
        esac
    done

    _trello_write_ready || return 1
    [ -n "$from" ] || { _trello_error "supersede requires --from"; return 1; }

    if [ -n "$do_create" ]; then
        [ -z "$to" ] || { _trello_error "--create builds the successor; do not also pass --to"; return 1; }
        [ -n "$list_ref" ] || { _trello_error "supersede --create requires --list"; return 1; }
        [ -n "$name" ] || { _trello_error "supersede --create requires --name"; return 1; }
        if [ -n "$desc" ] && [ -n "$desc_file" ]; then
            _trello_error "Use either --desc or --desc-file, not both"; return 1
        fi
        if [ -n "$desc_file" ]; then
            desc="$(_trello_read_file "$desc_file")" || return 1
        fi
    else
        [ -n "$to" ] || { _trello_error "supersede requires --to (or use --create to make the successor)"; return 1; }
        if [ -n "$list_ref" ] || [ -n "$name" ] || [ -n "$desc" ] || [ -n "$desc_file" ]; then
            _trello_error "--list/--name/--desc/--desc-file only apply with --create"; return 1
        fi
    fi

    # Pre-flight the predecessor before any write, so a typo'd ref fails clean.
    from_json="$(_trello_get "/cards/${from}" --data-urlencode "fields=id,name,url")" \
        || { _trello_error "Could not read --from card '${from}' (check the id/url and read token)"; return 1; }
    from="$(printf '%s' "$from_json" | jq -er '.id')" || return 1
    from_url="$(printf '%s' "$from_json" | jq -r '.url // empty')"
    [ -n "$from_url" ] || { _trello_error "--from card '${from}' not found"; return 1; }

    if [ -n "$do_create" ]; then
        list_id="$(_trello_resolve_list_id "$board" "$list_ref")" || return 1
        created="$(_trello_write POST "/cards" \
            --data-urlencode "idList=${list_id}" \
            --data-urlencode "name=${name}" \
            --data-urlencode "desc=${desc}")" \
            || { _trello_error "Successor creation failed or has an uncertain outcome; inspect the board before retrying. Nothing linked"; return 1; }
        to="$(printf '%s' "$created" | jq -r '.id // empty')"
        to_url="$(printf '%s' "$created" | jq -r '.url // empty')"
        [ -n "$to" ] && [ -n "$to_url" ] || { _trello_error "Successor may exist but response lacked ID or URL; inspect the board before retrying; nothing linked"; return 1; }
        _trello_say "Created successor: $(printf '%s' "$created" | jq -r '.name // "Untitled card"') | ${to_url}"
    else
        to_json="$(_trello_get "/cards/${to}" --data-urlencode "fields=id,name,url")" \
            || { _trello_error "Could not read --to card '${to}' (check the id/url and read token)"; return 1; }
        to="$(printf '%s' "$to_json" | jq -er '.id')" || return 1
        to_url="$(printf '%s' "$to_json" | jq -r '.url // empty')"
        [ -n "$to_url" ] || { _trello_error "--to card '${to}' not found"; return 1; }
    fi

    if [ "$from" = "$to" ]; then
        _trello_error "--from and --to refer to the same card; nothing to link"; return 1
    fi

    # Successor back-link first, predecessor forward-link second .
    _trello_say "Linking chain ${from_url} -> ${to_url}"
    if ! _trello_write_link "$to" "Continues from:" "$from" "$from_url"; then
        _trello_error "PARTIAL or uncertain: successor ${to_url} exists but its back-link was not confirmed. Inspect both cards; retry linking with --from ${from} --to ${to}, never --create."
        return 1
    fi
    if ! _trello_write_link "$from" "Continues in:" "$to" "$to_url"; then
        _trello_error "PARTIAL: the successor (${to_url}) now points back to the predecessor, but writing the forward link on the predecessor (${from_url}) FAILED."
        _trello_error "Inspect both cards, then retry with --from ${from} --to ${to} (without --create). The helper checks existing link comments before writing."
        return 1
    fi
    _trello_say "Superseded: ${from_url}  ->  ${to_url}"
)

_trello_chain() (
    set -o pipefail
    local card="" want_json="" head prev cur guard visited seen order count
    local id meta name url current obj all idx

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --card) card="$(_trello_card_ref "$2")"; shift 2 ;;
            --json) want_json=1; shift ;;
            *) _trello_error "Unknown chain option: $1"; return 1 ;;
        esac
    done

    _trello_ready || return 1
    [ -n "$card" ] || { _trello_error "chain requires --card"; return 1; }

    # Walk backward to the head of the chain (cycle/runaway guarded).
    head="$card"; visited=" "; guard=0
    while :; do
        case "$visited" in *" ${head} "*) break ;; esac
        visited="${visited}${head} "
        prev="$(_trello_link_target "$head" "Continues from:")" || return 1
        [ -n "$prev" ] || break
        case "$visited" in *" ${prev} "*) break ;; esac
        head="$prev"
        guard=$((guard + 1)); [ "$guard" -gt 100 ] && break
    done

    # Walk forward from the head, collecting the ordered chain.
    cur="$head"; seen=" "; order=""; guard=0
    while :; do
        case "$seen" in *" ${cur} "*) break ;; esac
        seen="${seen}${cur} "
        order="${order}${cur} "
        cur="$(_trello_link_target "$cur" "Continues in:")" || return 1
        [ -n "$cur" ] || break
        guard=$((guard + 1)); [ "$guard" -gt 100 ] && break
    done

    if [ -n "$want_json" ]; then
        all=""
        for id in $order; do
            meta="$(_trello_get "/cards/${id}" --data-urlencode "fields=name,url")" || return 1
            obj="$(printf '%s' "$meta" | jq -c \
                --arg id "$id" \
                --argjson current "$( [ "$id" = "$card" ] && echo true || echo false )" \
                '{id: $id, name: (.name // null), url: (.url // null), current: $current}')"
            all="${all}${obj}
"
        done
        printf '%s' "$all" | jq -s '{chain: .}'
        return 0
    fi

    count="$(set -- $order; echo "$#")"
    _trello_say "Task chain (head -> tail):"
    idx=1
    for id in $order; do
        meta="$(_trello_get "/cards/${id}" --data-urlencode "fields=name,url")" || return 1
        name="$(printf '%s' "$meta" | jq -r '.name // "Unknown card"')"
        url="$(printf '%s' "$meta" | jq -r '.url // empty')"
        [ -n "$url" ] || url="(card ${id} unreadable)"
        if [ "$id" = "$card" ]; then current="  <-- you are here"; else current=""; fi
        printf '%d. %s%s\n     %s\n' "$idx" "$name" "$current" "$url"
        idx=$((idx + 1))
    done
    if [ "$count" -eq 1 ]; then
        _trello_say "(no chain links found on this card)"
    fi
)

# Optional consumer-supplied list names requiring a start date.
_trello_snooze_lists() (
    set -o pipefail
    printf '%s\n' "${TRELLO_SNOOZE_LISTS:-}"
)

_trello_render_cards() (
    set -o pipefail
    local lists_file="$1"
    local cards_file="$2"

    jq -r --slurpfile lists "$lists_file" --arg snooze_lists "$(_trello_snooze_lists)" '
      def list_name($id):
        (($lists[0][] | select(.id == $id) | .name) // "Unknown list");
      def open_list_cards:
        map(select(.idList as $list_id | any($lists[0][]; .id == $list_id)));
      def quote_lines($indent):
        gsub("\r"; "") | split("\n") | map($indent + "> " + .) | join("\n");
      def labels:
        ((.labels // []) | map(.name // "") | map(select(. != "")) | join(", "));
      def checklist_progress:
        ((.checklists // []) |
          map((.name // "Checklist") + " " +
            (((.checkItems // []) | map(select(.state == "complete")) | length) | tostring) +
            "/" +
            (((.checkItems // []) | length) | tostring)
          ) |
          join(", "));
      def snooze_list($name):
        ($snooze_lists | split(",") | map(gsub("^\\s+|\\s+$"; "")) | index($name)) != null;
      def checklist_items:
        ((.checklists // []) | map(select(((.checkItems // []) | length) > 0))) as $lists |
        if ($lists | length) > 0 then
          ($lists |
            map(
              "\n  - Checklist: " + (.name // "Checklist") + "\n" +
              ((.checkItems // []) | sort_by(.pos // 0) |
                map("    - [" + (if .state == "complete" then "x" else " " end) + "] " + (.name // "")) |
                join("\n"))
            ) | join(""))
        else "" end;
      def description:
        if ((.desc // "") | length) > 0 then
          "\n  - Description:\n" + ((.desc // "") | quote_lines("    "))
        else "" end;
      def comment_text:
        (.data.text // .display.entities.comment.text // "");
      def comments:
        ((.actions // []) |
          map(select(.type == "commentCard" and ((comment_text | length) > 0))) |
          sort_by(.date)
        ) as $comments |
        if ($comments | length) > 0 then
          "\n  - Comments:\n" +
          ($comments |
            map(
              "    - " + (.date // "unknown date") +
              " by " + (.memberCreator.fullName // .memberCreator.username // "Unknown") + ":\n" +
              (comment_text | quote_lines("      "))
            ) |
            join("\n")
          )
        else "" end;
      open_list_cards as $cards |
      if ($cards | length) == 0 then
        "_No open cards._\n"
      else
        $cards |
        sort_by(.idList) |
        group_by(.idList)[] |
        "### " + list_name(.[0].idList) + "\n\n" +
        (map(
          "- [" + (.name // "Untitled card") + "](" + (.url // "") + ")" +
          (if (.start // "") != "" then " | start: " + .start
           elif snooze_list(list_name(.idList)) then " | start: MISSING (configured list requires a start date)"
           else "" end) +
          (if (.due // "") != "" then " | due: " + .due else "" end) +
          (if (.dateLastActivity // "") != "" then " | last activity: " + .dateLastActivity else "" end) +
          (if (labels | length) > 0 then " | labels: " + labels else "" end) +
          (if (checklist_progress | length) > 0 then " | checklists: " + checklist_progress else "" end) +
          checklist_items +
          description +
          comments
        ) | join("\n")) + "\n"
      end
    ' "$cards_file"
)

