#!/usr/bin/env bash
##- Drive-item addressing and opt-in shared by file and workbook capabilities.

_m365_files_item_url() {
    local alias="$1" item="$2" drive="$3" base encoded_item encoded_drive
    base="$(_m365_graph_base "$alias")"
    encoded_item="$(_m365_uri_encode "$item")" || return 1
    if [ -n "$drive" ]; then
        encoded_drive="$(_m365_uri_encode "$drive")" || return 1
        printf '%s/drives/%s/items/%s\n' "$base" "$encoded_drive" "$encoded_item"
    else
        printf '%s/me/drive/items/%s\n' "$base" "$encoded_item"
    fi
}

_m365_files_require_write() {
    local alias="$1"
    if ! _m365_account_value "$alias" '(.files.write_enabled // false) == true' 2>/dev/null | grep -qx true; then
        _m365_error "Microsoft 365 file writes are not enabled for alias '$alias'"
        _m365_say "NEXT: set files.write_enabled to true for '$alias' in $(_m365_accounts_path)" >&2
        return 1
    fi
}
