#!/usr/bin/env bash
##- Internal bounded Graph batch transport used by task and mail capabilities.
_m365_batch() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" requests="$2" out="$3" dir total start=0 n=0 chunk expected
    local files=()
    dir="$(mktemp -d "$M365_WORK/batch.XXXXXX")" || return 1
    total="$(jq 'length' "$requests")" || return 1
    while [ "$start" -lt "$total" ]; do
        chunk="$(jq -c --argjson s "$start" '{requests: [.[$s:($s + 20)] | to_entries[] | {id: (($s + .key) | tostring)} + .value + (if .value.body then {headers: {"Content-Type": "application/json"}} else {} end)]}' "$requests")" || return 1
        _m365_write POST "$alias" "$(_m365_graph_base "$alias")/\$batch" "$chunk" > "${dir}/${n}.json" || return 1
        expected="$(printf '%s' "$chunk" | jq -c '[.requests[].id] | sort')" || return 1
        jq -e --argjson expected "$expected" '.responses | type == "array" and ((map(.id) | sort) == $expected) and all(.[]; (.status | type == "number"))' "${dir}/${n}.json" >/dev/null || { _m365_error 'Incomplete or malformed Graph batch response; inspect before retrying any writes'; return 1; }
        files+=("${dir}/${n}.json")
        n=$((n + 1))
        start=$((start + 20))
    done
    if [ "${#files[@]}" -eq 0 ]; then
        printf '[]\n' > "$out"
    else
        jq -s '[.[].responses[]?] | sort_by(.id | tonumber)' "${files[@]}" > "$out"
    fi
)
