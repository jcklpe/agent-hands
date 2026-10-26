#!/usr/bin/env bash
if [ -n "${ZSH_VERSION:-}" ]; then _excel_source="${(%):-%x}"; else _excel_source="${BASH_SOURCE[0]}"; fi
EXCEL_WORKBOOKS_DIR="$(cd "$(dirname "$_excel_source")/.." && pwd)"
unset _excel_source
source "$EXCEL_WORKBOOKS_DIR/../authorize-microsoft/scripts/drive-items.sh"
_m365_excel_python() { _m365_python "$EXCEL_WORKBOOKS_DIR" "$@"; }
_m365_excel_warn() { printf 'WARN: %s\n' "$*" >&2; }
_m365_excel_audit_path() { case "${M365_EXCEL_AUDIT_LOG:-workbook-writes.jsonl}" in /*) printf '%s\n' "$M365_EXCEL_AUDIT_LOG" ;; *) printf '%s/%s\n' "$EXCEL_WORKBOOKS_DIR" "${M365_EXCEL_AUDIT_LOG:-workbook-writes.jsonl}" ;; esac; }
_m365_excel_audit_append() { _m365_excel_python "$M365_AUTH_DIR/scripts/audit.py" "$(_m365_excel_audit_path)"; }
##- Bounded Graph workbook operations. Sessionless requests save each write; there is no transaction or automatic mutation retry.

_m365_excel_help() {
    cat <<'EOF'
Usage: excel COMMAND ALIAS ITEM_ID [--drive DRIVE_ID] [--json]
  sheets
  tables [--sheet NAME_OR_ID]
  read-range --sheet NAME_OR_ID --range A1:D20
  table-range --table NAME_OR_ID
  write-range --sheet NAME_OR_ID --range A1:D20 --file PATCH.json
  format-range --sheet NAME_OR_ID --range A1:D20 --file PATCH.json [--part format|font|fill]
  add-sheet --name NAME
  add-table --sheet NAME_OR_ID --range A1:D20   # existing unique text headers required
  update-table --table NAME_OR_ID --file PATCH.json
  append-rows --table NAME_OR_ID --file ROWS.json
Writes preview by default. Execute the same plan with --expect PREVIEW_SHA256 --execute.
Range patch: {"values":[["text",42]],"numberFormat":[[null,"0.00"]]}; formulas use a separate matrix.
Append: {"values":[["new",42]]}. Null range patch cells preserve existing properties.
Maximum 10,000 cells per range/resulting table and 1 MiB per payload. Only .xlsx files.
Requires files.enabled; executing also requires files.write_enabled. No new auth scopes are requested.
No delete, clear, arbitrary Graph request, authentication change or rollback. Preview guards are not atomic locks.
EOF
}

_m365_excel_fetch() {
    local alias="$1" base="$2" reads="$3" out="$4" dir="$5" key suffix response
    printf '{}\n' > "$out"
    while IFS= read -r key; do
        suffix="$(jq -r --arg key "$key" '.[$key]' "$reads")" || return 1
        response="${dir}/read-${key}.json"
        _m365_get "$alias" "${base}${suffix}" > "$response" || return 1
        jq --arg key "$key" --slurpfile value "$response" '. + {($key): $value[0]}' "$out" > "${out}.next" || return 1
        mv "${out}.next" "$out" || return 1
    done <<EOF
$(jq -r 'keys[]' "$reads")
EOF
}

_m365_excel_audit() {
    local alias="$1" item="$2" drive="$3" op="$4" fingerprint="$5" state="$6"
    jq -nc --arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg alias "$alias" --arg item "$item" --arg drive "$drive" --arg op "$op" --arg hash "$fingerprint" --arg state "$state" \
        '{ts:$ts, service:"m365-excel", alias:$alias, item_id:$item, drive_id:$drive, action:$op, preview_sha256:$hash, state:$state}' | _m365_excel_audit_append
}

_m365_excel_dispatch() (
    set -o pipefail
    # A subshell owns cleanup; no trap or variables leak into the other command groups.
    local op="${1:-help}" alias="${2:-}" item="${3:-}" drive="" sheet="" address="" table="" part="" file="" name="" expect="" execute=0 json=0
    local work helper item_url base hash current_hash method suffix
    case "$op" in help|--help|-h) _m365_excel_help; return 0 ;; esac
    [ -n "$alias" ] && [ -n "$item" ] || { _m365_error "Excel commands require ALIAS ITEM_ID; see 'excel help'"; return 1; }
    shift 3
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --drive|--sheet|--range|--table|--part|--file|--name|--expect)
                [ "$#" -ge 2 ] && [ -n "$2" ] || { _m365_error "$1 requires a value"; return 1; }
                case "$1" in
                    --drive) drive="$2" ;; --sheet) sheet="$2" ;; --range) address="$2" ;; --table) table="$2" ;;
                    --part) part="$2" ;; --file) file="$2" ;; --name) name="$2" ;; --expect) expect="$2" ;;
                esac
                shift 2 ;;
            --execute) execute=1; shift ;;
            --dry-run) execute=0; shift ;;
            --json) json=1; shift ;;
            *) _m365_error "Unknown Excel option: $1"; return 1 ;;
        esac
    done
    work="$(mktemp -d "${TMPDIR:-/tmp}/microsoft-excel.XXXXXX")" || return 1
    trap 'rm -rf "$work"' EXIT
    helper="$EXCEL_WORKBOOKS_DIR/scripts/excel.py"
    _m365_excel_python "$helper" plan "$op" "$sheet" "$address" "$table" "$part" "$file" "$name" > "$work/plan.json" || return 1
    method="$(jq -r '.method' "$work/plan.json")"
    if [ "$method" = GET ] && { [ "$execute" -eq 1 ] || [ -n "$expect" ]; }; then _m365_error "Read commands do not accept --execute or --expect"; return 1; fi
    if [ "$execute" -eq 1 ]; then
        printf '%s' "$expect" | LC_ALL=C grep -Eq '^[a-f0-9]{64}$' || { _m365_error "Execute requires --expect PREVIEW_SHA256 from a dry run of this exact operation"; return 1; }
        _m365_files_require_write "$alias" || return 1
    fi
    _m365_require_enabled "$alias" files || return 1
    item_url="$(_m365_files_item_url "$alias" "$item" "$drive")" || return 1
    base="${item_url}/workbook"
    _m365_get "$alias" "$item_url" --data-urlencode '$select=id,name,eTag,file,webUrl,parentReference' > "$work/item.json" || return 1
    jq '.reads' "$work/plan.json" > "$work/reads.json" || return 1
    _m365_excel_fetch "$alias" "$base" "$work/reads.json" "$work/before.json" "$work" || { _m365_error "Workbook read failed. File access alone does not prove Excel API access. No workbook mutation was sent; check the Graph error before changing consent."; return 1; }
    # Table creation must use the resolved sheet-qualified address, never the active worksheet.
    if [ "$op" = add-table ]; then
        jq --slurpfile before "$work/before.json" '.body.address = $before[0].range.address' "$work/plan.json" > "$work/plan.next" || return 1
        mv "$work/plan.next" "$work/plan.json" || return 1
    fi
    hash="$(_m365_excel_python "$helper" fingerprint "$work/plan.json" "$work/item.json" "$work/before.json" "$alias" "$drive" "$item" | jq -er .)" || return 1
    if [ "$method" = GET ]; then
        if [ "$json" -eq 1 ]; then cat "$work/before.json"; else jq . "$work/before.json"; fi
        return 0
    fi
    if [ "$execute" -ne 1 ]; then
        jq -n --slurpfile item "$work/item.json" --slurpfile plan "$work/plan.json" --slurpfile before "$work/before.json" --arg hash "$hash" \
            '{dry_run:true, item:$item[0], operation:$plan[0], before:$before[0], preview_sha256:$hash, next:"Review this plan, then repeat it with --expect PREVIEW_SHA256 --execute. The check is not an atomic lock."}'
        return 0
    fi
    [ "$expect" = "$hash" ] || { _m365_error "Stale or different preview; no write sent. Run a fresh dry run and review it."; return 1; }
    # Recheck both file revision and target immediately before mutation. A concurrent edit can still occur after this check.
    _m365_get "$alias" "$item_url" --data-urlencode '$select=id,name,eTag,file,webUrl,parentReference' > "$work/current-item.json" || return 1
    _m365_excel_fetch "$alias" "$base" "$work/reads.json" "$work/current.json" "$work" || return 1
    current_hash="$(_m365_excel_python "$helper" fingerprint "$work/plan.json" "$work/current-item.json" "$work/current.json" "$alias" "$drive" "$item" | jq -er .)" || return 1
    [ "$hash" = "$current_hash" ] || { _m365_error "Workbook changed during preflight; no write sent. Review a new dry run."; return 1; }
    _m365_excel_audit "$alias" "$item" "$drive" "$op" "$hash" started || { _m365_error "Cannot record the write attempt; no write sent"; return 1; }
    suffix="$(jq -r '.suffix' "$work/plan.json")"
    if ! _m365_http "$method" "$alias" "${base}${suffix}" "$(jq -c '.body' "$work/plan.json")" > "$work/result.json"; then
        _m365_excel_audit "$alias" "$item" "$drive" "$op" "$hash" uncertain || _m365_excel_warn "Audit update failed"
        _m365_error "Write outcome is uncertain. Do not repeat it blindly; read the target first. No CLI retry or rollback was attempted."
        return 1
    fi
    if ! _m365_excel_python "$helper" readback "$work/plan.json" "$work/result.json" > "$work/readback-reads.json" || ! _m365_excel_fetch "$alias" "$base" "$work/readback-reads.json" "$work/after.json" "$work" || ! _m365_excel_python "$helper" verify "$work/plan.json" "$work/before.json" "$work/after.json" > /dev/null; then
        _m365_excel_audit "$alias" "$item" "$drive" "$op" "$hash" unverified || _m365_excel_warn "Audit update failed"
        _m365_error "Graph accepted the write, but readback verification failed. It may have applied; inspect the target before another write."
        return 1
    fi
    _m365_excel_audit "$alias" "$item" "$drive" "$op" "$hash" verified || { _m365_error "Write verified but audit completion failed; do not repeat the write"; return 1; }
    jq -n --arg op "$op" --arg item "$item" --arg hash "$hash" --slurpfile after "$work/after.json" '{verified:true, operation:$op, item_id:$item, preview_sha256:$hash, after:$after[0]}'
)
