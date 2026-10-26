#!/usr/bin/env bash
# Build an immutable request plan using the existing bounded operation parsers. All planning reads are cached; writes are captured, never sent.
_trello_digest() { shasum -a 256 | awk '{print $1}'; }
_trello_plan_error() { : > "$TRELLO_PLAN_DIR/failed"; _trello_error "$*"; return 1; }
_trello_plan_get() {
    local query key response
    case "$1" in
        /cards/__AH_PLAN_*_ID__/actions) printf '[]\n'; return ;;
        *__AH_PLAN_*) _trello_plan_error 'Cannot read an unresolved future resource'; return 1 ;;
    esac
    query="$(jq -cn --args '$ARGS.positional' -- "$@")" || return 1
    key="$(printf '%s' "$query" | _trello_digest)" || return 1
    if [ ! -f "$TRELLO_PLAN_DIR/reads/$key.response" ]; then
        response="$(_trello_get_http "$@")" || { _trello_plan_error 'A required planning read failed; no writes were sent'; return 1; }
        response="$(printf '%s' "$response" | jq -cS .)" || { _trello_plan_error 'A planning response was not JSON'; return 1; }
        printf '%s\n' "$query" > "$TRELLO_PLAN_DIR/reads/$key.query"
        printf '%s\n' "$response" > "$TRELLO_PLAN_DIR/reads/$key.response"
    fi
    cat "$TRELLO_PLAN_DIR/reads/$key.response"
}
_trello_plan_object() {
    local kind="$1" ref="$2" result fields
    case "$kind" in
        cards) fields='id,idBoard,idList,name,desc,start,idLabels,closed,url' ;;
        lists) fields='id,idBoard,name,closed' ;;
        boards) fields='id,name,closed' ;;
        labels) fields='id,idBoard,name,color' ;;
        checklists) fields='id,idCard,name,pos' ;;
        *) _trello_plan_error 'Unsupported target kind'; return 1 ;;
    esac
    case "$ref" in ''|*[!A-Za-z0-9]*) _trello_plan_error "Invalid $kind reference"; return 1 ;; esac
    result="$(_trello_plan_get "/$kind/$ref" --data-urlencode "fields=$fields")" || return 1
    printf '%s' "$result" | jq -e 'type == "object" and (.id | type == "string" and test("^[a-f0-9]{24}$")) and (.closed != true)' >/dev/null || { _trello_plan_error "Missing, malformed or closed $kind target"; return 1; }
    case "$kind" in
        cards) printf '%s' "$result" | jq -e '(.idBoard | test("^[a-f0-9]{24}$")) and (.idList | test("^[a-f0-9]{24}$")) and (.name | type == "string") and (.desc | type == "string") and (.idLabels | type == "array") and (.closed == false) and (.url | startswith("https://trello.com/c/"))' >/dev/null ;;
        lists) printf '%s' "$result" | jq -e '(.idBoard | test("^[a-f0-9]{24}$")) and (.name | type == "string") and (.closed == false)' >/dev/null ;;
        boards) printf '%s' "$result" | jq -e '(.name | type == "string") and (.closed == false)' >/dev/null ;;
        labels) printf '%s' "$result" | jq -e '(.idBoard | test("^[a-f0-9]{24}$")) and (.name | type == "string")' >/dev/null ;;
        checklists) printf '%s' "$result" | jq -e '(.idCard | test("^[a-f0-9]{24}$")) and (.name | type == "string")' >/dev/null ;;
    esac || { _trello_plan_error "Malformed $kind target fields"; return 1; }
    printf '%s\n' "$result"
}
_trello_plan_write() {
    local method="$1" path="$2" fields='{}' key value target='{}' card='' list='' board='' label='' checklist='' item='' parent='' canonical='' rest='' n fake
    shift 2
    while [ "$#" -gt 0 ]; do
        [ "$1" = --data-urlencode ] && [ "$#" -ge 2 ] && [[ "$2" == *=* ]] || { _trello_plan_error 'Invalid internal write argument'; return 1; }
        key="${2%%=*}"; value="${2#*=}"
        fields="$(printf '%s' "$fields" | jq -c --arg k "$key" --arg v "$value" '. + {($k):$v}')" || return 1
        shift 2
    done
    # Canonicalize and validate targets even when a user supplied an ID rather than a name.
    case "$path" in
        /cards)
            [ "$method" = POST ] || return 1
            list="$(_trello_plan_object lists "$(printf '%s' "$fields" | jq -r .idList)")" || return 1
            board="$(_trello_plan_object boards "$(printf '%s' "$list" | jq -r .idBoard)")" || return 1
            if [ -n "$TRELLO_PLAN_BOARD" ]; then [ "$(printf '%s' "$board" | jq -r .id)" = "$TRELLO_PLAN_BOARD" ] || { _trello_plan_error 'Destination list is on a different board'; return 1; }; fi
            target="$(jq -cn --argjson list "$list" --argjson board "$board" '{list:$list,board:$board}')" ;;
        /cards/*)
            rest="${path#/cards/}"; canonical="${rest%%/*}"
            case "$canonical" in
                __AH_PLAN_*_ID__) card="$(jq -cn --arg id "$canonical" '{id:$id}')" ;;
                *) card="$(_trello_plan_object cards "$canonical")" || return 1
                   _trello_plan_object boards "$(printf '%s' "$card" | jq -r .idBoard)" >/dev/null || return 1 ;;
            esac
            path="/cards/$(printf '%s' "$card" | jq -r .id)${rest#"$canonical"}"
            target="$(jq -cn --argjson card "$card" '{card:$card}')"
            case "$path" in
                */idLabels|*/idLabels/*)
                    if [ "$method" = POST ]; then key="$(printf '%s' "$fields" | jq -r .value)"; else key="${path##*/}"; fi
                    label="$(_trello_plan_object labels "$key")" || return 1
                    if [ -n "$TRELLO_PLAN_BOARD" ]; then [ "$(printf '%s' "$label" | jq -r .idBoard)" = "$TRELLO_PLAN_BOARD" ] || { _trello_plan_error 'Label belongs to a different board'; return 1; }; fi
                    [ "$(printf '%s' "$label" | jq -r .idBoard)" = "$(printf '%s' "$card" | jq -r .idBoard)" ] || { _trello_plan_error 'Label and card belong to different boards'; return 1; }
                    target="$(printf '%s' "$target" | jq -c --argjson label "$label" '. + {label:$label}')" ;;
                */checkItem/*)
                    item="${path##*/}"; checklist="$(_trello_plan_get "/cards/$(printf '%s' "$card" | jq -r .id)/checklists" --data-urlencode 'checkItem_fields=name,state')" || return 1
                    printf '%s' "$checklist" | jq -e --arg id "$item" '[.[].checkItems[]? | select(.id == $id)] | length == 1' >/dev/null || { _trello_plan_error 'Checklist item does not belong uniquely to this card'; return 1; }
                    target="$(printf '%s' "$target" | jq -c --argjson lists "$checklist" --arg id "$item" '. + {item:([$lists[].checkItems[]? | select(.id == $id)][0])}')" ;;
                */actions/comments) : ;;
                *)
                    [ "$method" = PUT ] || { _trello_plan_error 'Unsupported card mutation'; return 1; }
                    if printf '%s' "$fields" | jq -e 'has("idList")' >/dev/null; then
                        list="$(_trello_plan_object lists "$(printf '%s' "$fields" | jq -r .idList)")" || return 1
                        board="$(_trello_plan_object boards "$(printf '%s' "$list" | jq -r .idBoard)")" || return 1
                        if [ -n "$TRELLO_PLAN_BOARD" ]; then [ "$(printf '%s' "$board" | jq -r .id)" = "$TRELLO_PLAN_BOARD" ] || { _trello_plan_error 'Destination list is on a different board'; return 1; }; fi
                        target="$(printf '%s' "$target" | jq -c --argjson list "$list" --argjson board "$board" '. + {list:$list,board:$board}')"
                    fi ;;
            esac ;;
        /checklists)
            card="$(_trello_plan_object cards "$(printf '%s' "$fields" | jq -r .idCard)")" || return 1
            target="$(jq -cn --argjson card "$card" '{card:$card}')" ;;
        /checklists/*/checkItems)
            canonical="${path#/checklists/}"; canonical="${canonical%/checkItems}"
            case "$canonical" in __AH_PLAN_*_ID__) target="$(jq -cn --arg id "$canonical" '{checklist:{id:$id}}')" ;;
                *)
                    checklist="$(_trello_plan_object checklists "$canonical")" || return 1
                    card="$(_trello_plan_object cards "$TRELLO_PLAN_CARD")" || return 1
                    [ "$(printf '%s' "$checklist" | jq -r .idCard)" = "$(printf '%s' "$card" | jq -r .id)" ] || { _trello_plan_error 'Checklist does not belong to the selected card'; return 1; }
                    _trello_plan_get "/checklists/$canonical/checkItems" --data-urlencode 'fields=name,state,pos' >/dev/null || return 1
                    target="$(jq -cn --argjson card "$card" --argjson checklist "$checklist" '{card:$card,checklist:$checklist}')" ;;
            esac ;;
        /labels)
            board="$(_trello_plan_object boards "$(printf '%s' "$fields" | jq -r .idBoard)")" || return 1
            target="$(jq -cn --argjson board "$board" '{board:$board}')" ;;
        /labels/*)
            [ "$method" = DELETE ] || return 1
            label="$(_trello_plan_object labels "${path#/labels/}")" || return 1
            board="$(_trello_plan_object boards "$(printf '%s' "$label" | jq -r .idBoard)")" || return 1
            if [ -n "$TRELLO_PLAN_BOARD" ]; then [ "$(printf '%s' "$board" | jq -r .id)" = "$TRELLO_PLAN_BOARD" ] || { _trello_plan_error 'Label belongs to a different board'; return 1; }; fi
            _trello_plan_get "/boards/$(printf '%s' "$board" | jq -r .id)/labels" --data-urlencode 'limit=1000' | jq -e 'type == "array" and length < 1000' >/dev/null || { _trello_plan_error 'Cannot establish a complete bounded label listing'; return 1; }
            target="$(jq -cn --argjson label "$label" --argjson board "$board" '{label:$label,board:$board,impact:"Deletes this label from the board and all cards carrying it"}')" ;;
        *) _trello_plan_error 'Unsupported mutation endpoint'; return 1 ;;
    esac
    n="$(($(wc -l < "$TRELLO_PLAN_DIR/steps") + 1))"
    jq -cn --arg method "$method" --arg path "$path" --argjson fields "$fields" --argjson target "$target" '{method:$method,path:$path,fields:$fields,target:$target}' >> "$TRELLO_PLAN_DIR/steps" || return 1
    fake="__AH_PLAN_${n}_ID__"
    printf '%s' "$fields" | jq -c --arg id "$fake" --arg url "https://trello.com/c/__AH_PLAN_${n}_URL__" '. + {id:$id,url:$url,date:"planned"}'
}
_trello_readback() {
    local step="$1" response="$2" method path fields id card key data board expected_id
    method="$(printf '%s' "$step" | jq -r .method)"; path="$(printf '%s' "$step" | jq -r .path)"; fields="$(printf '%s' "$step" | jq -c .fields)"
    id="$(printf '%s' "$response" | jq -r 'if type == "object" then .id // empty else empty end')" || return 1
    case "$path" in
        /cards) _trello_looks_like_id "$id" || return 1
            printf '%s' "$response" | jq -e '.url | type == "string" and startswith("https://trello.com/c/")' >/dev/null || return 1
            data="$(_trello_get_http "/cards/$id" --data-urlencode 'fields=id,idList,name,desc,start,url')" || return 1 ;;
        /cards/*/actions/comments)
            _trello_looks_like_id "$id" || return 1; card="${path#/cards/}"; card="${card%/actions/comments}"
            data="$(_trello_get_http "/cards/$card/actions" --data-urlencode 'filter=commentCard' --data-urlencode 'limit=1000')" || return 1
            printf '%s' "$data" | jq -e --arg id "$id" --argjson f "$fields" 'any(.[]; .id == $id and .data.text == $f.text)' >/dev/null; return ;;
        /cards/*/idLabels|/cards/*/idLabels/*)
            card="${path#/cards/}"; card="${card%%/*}"; data="$(_trello_get_http "/cards/$card" --data-urlencode 'fields=idLabels')" || return 1
            if [ "$method" = POST ]; then key="$(printf '%s' "$fields" | jq -r .value)"; else key="${path##*/}"; fi
            printf '%s' "$data" | jq -e --arg id "$key" --arg m "$method" '(.idLabels | index($id) != null) == ($m == "POST")' >/dev/null; return ;;
        /cards/*/checkItem/*)
            card="${path#/cards/}"; card="${card%%/*}"; key="${path##*/}"; data="$(_trello_get_http "/cards/$card/checklists" --data-urlencode 'checkItem_fields=name,state')" || return 1
            printf '%s' "$data" | jq -e --arg id "$key" --argjson f "$fields" 'any(.[].checkItems[]?; .id == $id and .state == $f.state)' >/dev/null; return ;;
        /cards/*) data="$(_trello_get_http "$path" --data-urlencode 'fields=id,idList,name,desc,start,url')" || return 1 ;;
        /checklists)
            _trello_looks_like_id "$id" || return 1; data="$(_trello_get_http "/checklists/$id" --data-urlencode 'fields=id,idCard,name,pos')" || return 1
            fields="$(printf '%s' "$fields" | jq -c 'del(.pos)')" ;;
        /checklists/*/checkItems)
            _trello_looks_like_id "$id" || return 1; data="$(_trello_get_http "$path" --data-urlencode 'fields=name,state,pos')" || return 1
            printf '%s' "$data" | jq -e --arg id "$id" --argjson f "$fields" 'type == "array" and any(.[]; .id == $id and .name == $f.name) and (max_by(.pos).id == $id)' >/dev/null; return ;;
        /labels)
            _trello_looks_like_id "$id" || return 1; data="$(_trello_get_http "/labels/$id" --data-urlencode 'fields=id,idBoard,name,color')" || return 1
            # Trello represents the colorless label as null.
            fields="$(printf '%s' "$fields" | jq -c 'if .color == "" then .color=null else . end')" ;;
        /labels/*)
            board="$(printf '%s' "$step" | jq -r .target.board.id)"; id="${path##*/}"; data="$(_trello_get_http "/boards/$board/labels" --data-urlencode 'limit=1000')" || return 1
            printf '%s' "$data" | jq -e --arg id "$id" 'type == "array" and length < 1000 and all(.[]; .id != $id)' >/dev/null; return ;;
        *) return 1 ;;
    esac
    case "$path" in /cards/*) expected_id="${path##*/}" ;; *) expected_id="$id" ;; esac
    printf '%s' "$data" | jq -e --arg id "$expected_id" --argjson f "$fields" 'type == "object" and (.id == $id) and (. as $actual | all($f | to_entries[]; $actual[.key] == .value))' >/dev/null
}
_trello_mutation() (
    set -o pipefail
    umask 077
    local command="$1" execute='' expect='' json='' arg query file actual expected fingerprint plan step response id url n=0 completed='[]' replacements='{}' data key
    local options=() request=()
    shift
    TRELLO_PLAN_BOARD=''; TRELLO_PLAN_CARD=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --execute) execute=1; shift ;;
            --json) json=1; shift ;;
            --expect) [ "$#" -ge 2 ] || { _trello_error 'Missing --expect hash'; return 1; }; expect="$2"; shift 2 ;;
            --create) options+=("$1"); shift ;;
            --*)
                [ "$#" -ge 2 ] || { _trello_error "Missing value for $1"; return 1; }
                case "$2" in *__AH_PLAN_*) _trello_error 'Reserved plan marker in input'; return 1 ;; esac
                case "$1" in
                    --file|--desc-file)
                        [ -f "$2" ] || { _trello_error "File does not exist: $2"; return 1; }
                        if LC_ALL=C grep -q '__AH_PLAN_' "$2"; then _trello_error 'Reserved plan marker in file input'; return 1; fi ;;
                esac
                case "$1" in --board) TRELLO_PLAN_BOARD="$2" ;; --card) TRELLO_PLAN_CARD="$(_trello_card_ref "$2")" ;; esac
                options+=("$1" "$2"); shift 2 ;;
            *) _trello_error "Unexpected argument: $1"; return 1 ;;
        esac
    done
    if [ -n "$TRELLO_PLAN_BOARD" ]; then _trello_looks_like_id "$TRELLO_PLAN_BOARD" || { _trello_error '--board requires a canonical board ID'; return 1; }; fi
    _trello_ready || return 1
    command -v shasum >/dev/null || { _trello_error 'shasum is required for preview fingerprints'; return 1; }
    TRELLO_PLAN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/trello-plan.XXXXXX")" || return 1
    trap 'rm -rf "$TRELLO_PLAN_DIR"' EXIT
    mkdir "$TRELLO_PLAN_DIR/reads" || return 1
    : > "$TRELLO_PLAN_DIR/steps"
    # These overrides exist only in the planning subshell. Parser output is suppressed because no mutation has happened yet.
    (
        _trello_get() { _trello_plan_get "$@"; }
        _trello_write_ready() { _trello_ready; }
        _trello_write() { _trello_plan_write "$@"; }
        "_trello_${command//-/_}" "${options[@]}" > "$TRELLO_PLAN_DIR/parser-output"
    ) || return 1
    [ ! -f "$TRELLO_PLAN_DIR/failed" ] || return 1
    plan="$(jq -cs --arg command "$command" '{command:$command,steps:.}' "$TRELLO_PLAN_DIR/steps")" || return 1
    fingerprint="$( { printf '%s\n' "$plan"; for file in "$TRELLO_PLAN_DIR"/reads/*.query; do [ -f "$file" ] || continue; cat "$file" "${file%.query}.response"; done; } | _trello_digest)" || return 1
    if [ -n "$expect" ] && [ "$expect" != "$fingerprint" ]; then _trello_error 'Preview changed or targets are stale; no writes were sent. Review a new preview.'; return 1; fi
    if [ -z "$execute" ]; then
        printf '%s' "$plan" | jq --arg hash "$fingerprint" '. + {mode:"preview",preview_hash:$hash,writes_sent:0}'
        [ -n "$json" ] || printf '\nNo writes sent. To apply this reviewed plan, repeat with --execute --expect %s\n' "$fingerprint"
        return
    fi
    _trello_write_ready || return 1
    # Re-read every dependency before the first mutation. Trello offers no atomic conditional transaction; later concurrent changes remain possible.
    for file in "$TRELLO_PLAN_DIR"/reads/*.query; do
        [ -f "$file" ] || continue
        request=(); n="$(jq length "$file")"; key=0
        while [ "$key" -lt "$n" ]; do request+=("$(jq -r --argjson i "$key" '.[$i]' "$file")"); key=$((key+1)); done
        actual="$(_trello_get_http "${request[@]}" | jq -cS .)" || { _trello_error 'Revalidation failed; no writes sent'; return 1; }
        expected="$(cat "${file%.query}.response")"
        [ "$actual" = "$expected" ] || { _trello_error 'Target state changed during preflight; no writes sent'; return 1; }
    done
    n=0
    while IFS= read -r step; do
        n=$((n+1))
        step="$(printf '%s' "$step" | jq -c --argjson r "$replacements" '(.path,.fields) |= walk(if type == "string" then reduce ($r|to_entries[]) as $e (.; split($e.key)|join($e.value)) else . end)')" || return 1
        data="$(printf '%s' "$step" | jq -c '[.path,.fields]')"
        case "$data" in *__AH_PLAN_*) _trello_error "PARTIAL or uncertain: unresolved resource at step $n; stopped. Verified prior steps: $completed"; return 1 ;; esac
        request=("$(printf '%s' "$step" | jq -r .method)" "$(printf '%s' "$step" | jq -r .path)")
        while IFS= read -r key; do request+=(--data-urlencode "$key=$(printf '%s' "$step" | jq -r --arg k "$key" '.fields[$k]')"); done < <(printf '%s' "$step" | jq -r '.fields|keys[]')
        if ! response="$(_trello_write_http "${request[@]}")"; then
            _trello_error "PARTIAL or uncertain at step $n (${request[0]} ${request[1]}). Inspect the target before retrying; no retry or rollback was attempted. Verified prior steps: $completed"; return 1
        fi
        if [ "${request[0]}" = DELETE ] && { [ -z "$response" ] || [ "$response" = null ]; }; then response='{}'; fi
        if ! printf '%s' "$response" | jq -e . >/dev/null; then _trello_error "PARTIAL or uncertain: step $n returned invalid JSON. Inspect the target before retrying. Verified prior steps: $completed"; return 1; fi
        id="$(printf '%s' "$response" | jq -r 'if type == "object" then .id // empty else empty end' 2>/dev/null)"; url="$(printf '%s' "$response" | jq -r 'if type == "object" then .url // empty else empty end' 2>/dev/null)"
        if ! _trello_readback "$step" "$response"; then
            _trello_error "PARTIAL or uncertain: step $n was sent but readback failed (returned id: ${id:-none}). Inspect the target before retrying. Verified prior steps: $completed"; return 1
        fi
        completed="$(printf '%s' "$completed" | jq -c --argjson step "$n" --arg id "$id" --arg path "${request[1]}" '. + [{step:$step,path:$path,id:$id}]')"
        if [ -n "$id" ]; then replacements="$(printf '%s' "$replacements" | jq -c --arg k "__AH_PLAN_${n}_ID__" --arg v "$id" '. + {($k):$v}')"; fi
        if [ -n "$url" ]; then
            # URL markers stand for the short link because the builder includes the fixed Trello URL prefix.
            case "$url" in https://trello.com/c/*) url="${url#https://trello.com/c/}" ;; *) _trello_error "Unexpected created card URL at step $n; stop and inspect"; return 1 ;; esac
            replacements="$(printf '%s' "$replacements" | jq -c --arg k "__AH_PLAN_${n}_URL__" --arg v "$url" '. + {($k):$v}')"
        fi
        [ -n "$json" ] || printf 'Verified step %s: %s %s (id: %s)\n' "$n" "${request[0]}" "${request[1]}" "${id:-not returned}"
    done < "$TRELLO_PLAN_DIR/steps"
    jq -n --arg hash "$fingerprint" --argjson completed "$completed" '{mode:"executed",preview_hash:$hash,verified_steps:$completed}'
)
