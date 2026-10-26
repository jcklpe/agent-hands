#!/usr/bin/env bash
##- Microsoft provider support; no private workspace dependency or generic request CLI.
if [ -n "${ZSH_VERSION:-}" ]; then _microsoft_source="${(%):-%x}"; else _microsoft_source="${BASH_SOURCE[0]}"; fi
M365_AUTH_DIR="$(cd "$(dirname "$_microsoft_source")/.." && pwd)"
unset _microsoft_source
_m365_error() { printf 'ERROR: %s\n' "$*" >&2; }
_m365_say() { printf '%s\n' "$*"; }
_m365_check_command() { command -v "$1" >/dev/null 2>&1; }
_m365_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }
_m365_python() {
    local project="$1"; shift
    if [ -n "${M365_PYTHON:-}" ]; then "$M365_PYTHON" "$@"
    elif command -v uv >/dev/null 2>&1; then uv run --quiet --locked --project "$project" python "$@"
    else _m365_error 'Install uv or select a compatible M365_PYTHON'; return 1
    fi
}
_m365_work_begin() {
    M365_WORK="$(mktemp -d "${TMPDIR:-/tmp}/microsoft-work.XXXXXX")" || return 1
    trap 'rm -rf "$M365_WORK"' EXIT
    trap 'exit 130' HUP INT TERM
}
_m365_validate_url() {
    case "$1" in https://graph.microsoft.com/v1.0/*|https://graph.microsoft.com/beta/*) return 0 ;; *) _m365_error 'Only the public Microsoft Graph HTTPS endpoint is supported'; return 1 ;; esac
}
_m365_expected_account() {
    _m365_account_value "$1" '.expected_account' || { _m365_error 'PowerShell aliases require expected_account to check the active SDK identity'; return 1; }
}
_m365_load_env() {
    local config line key value present
    config="${M365_ENV_FILE:-$(_m365_config_dir)/.env}"
    if [ ! -f "$config" ]; then
        [ -z "${M365_ENV_FILE:-}" ] && return 0
        _m365_error 'Selected M365_ENV_FILE does not exist'; return 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_m365_trim "$line")"
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) _m365_error 'Invalid Microsoft env assignment'; return 1 ;; esac
        key="$(_m365_trim "${line%%=*}")"; value="$(_m365_trim "${line#*=}")"
        case "$key" in M365_ACCOUNTS_PATH|M365_PYTHON|M365_PWSH_BIN|M365_FILES_AUDIT_LOG|M365_EXCEL_AUDIT_LOG|M365_PLANNER_AUDIT_LOG|M365_MAIL_AUDIT_LOG) ;; *) _m365_error 'Unsupported Microsoft configuration key'; return 1 ;; esac
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _m365_error 'Unclosed configuration quote'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _m365_error 'Unclosed configuration quote'; return 1 ;; esac ;;
        esac
        present="${!key+x}"; [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

_m365_accounts_path() {
    _m365_path "${M365_ACCOUNTS_PATH:-m365-accounts.json}"
}

_m365_path() {
    case "$1" in
        '') return 1 ;;
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$(_m365_config_dir)" "$1" ;;
    esac
}

_m365_accounts_ready() {
    local config
    config="$(_m365_accounts_path)" || return 1
    [ -f "$config" ] || { _m365_error 'Microsoft account config is missing; follow setup-microsoft-services'; return 1; }
    jq -e '(.accounts | type == "array") and (.accounts | length > 0) and all(.accounts[]; (.alias | type == "string") and (.alias | test("^[A-Za-z0-9][A-Za-z0-9_-]*$"))) and ([.accounts[].alias] | length == (unique | length))' "$config" >/dev/null || { _m365_error 'Invalid Microsoft account aliases'; return 1; }
}

_m365_account_exists() {
    local alias="$1"
    _m365_accounts_ready || return 1
    jq -e --arg alias "$alias" 'any(.accounts[]?; .alias == $alias)' "$(_m365_accounts_path)" >/dev/null
}

_m365_account_value() {
    local alias="$1" filter="$2"
    jq -er --arg alias "$alias" "(.accounts[]? | select(.alias == \$alias) | ${filter}) // empty" "$(_m365_accounts_path)"
}

_m365_auth_provider() {
    _m365_account_value "$1" '.auth_provider // "msal"'
}

_m365_account_path() {
    local alias="$1" filter="$2" value
    value="$(_m365_account_value "$alias" "$filter")" || return 1
    _m365_path "$value"
}

_m365_require_enabled() {
    local alias="$1" service="$2"
    _m365_account_exists "$alias" || { _m365_error "Unknown Microsoft 365 account alias: $alias"; return 1; }
    if ! _m365_account_value "$alias" "(.${service}.enabled // false) == true" 2>/dev/null | grep -qx true; then
        _m365_error "Microsoft 365 ${service} is not enabled for alias '$alias'"
        return 1
    fi
}

_m365_accounts_list() {
    _m365_accounts_ready || return 1
    jq -r '
      (.accounts // [])[] |
      "- " + (.alias // "missing-alias") +
      " | auth: " + (.auth_provider // "msal") +
      " | tenant: " + (.tenant // "organizations") +
      " | mail: " + (((.mail.enabled // false) == true) | tostring) +
      " | mail moves: " + (((.mail.write_enabled // false) == true) | tostring) +
      " | mail rules: " + (((.mail.rules_enabled // false) == true) | tostring) +
      " | calendar: " + (((.calendar.enabled // false) == true) | tostring) +
      " | contacts: " + (((.contacts.enabled // false) == true) | tostring) +
      " | files: " + (((.files.enabled // false) == true) | tostring) +
      " | file writes: " + (((.files.write_enabled // false) == true) | tostring) +
      " | planner: " + (((.planner.enabled // false) == true) | tostring) +
      " | planner writes: " + (((.planner.write_enabled // false) == true) | tostring)
    ' "$(_m365_accounts_path)"
}

_m365_scopes() {
    local alias="$1"
    _m365_account_exists "$alias" || return 1
    printf 'User.Read\n'
    # Mail.ReadWrite replaces Mail.Read only when the alias opts into mail moves; there is still no send or delete command.
    if _m365_account_value "$alias" '(.mail.enabled // false) == true' 2>/dev/null | grep -qx true; then
        if _m365_account_value "$alias" '(.mail.write_enabled // false) == true' 2>/dev/null | grep -qx true; then printf 'Mail.ReadWrite\n'; else printf 'Mail.Read\n'; fi
        # Inbox rules live in mailbox settings.
        _m365_account_value "$alias" '(.mail.rules_enabled // false) == true' 2>/dev/null | grep -qx true && printf 'MailboxSettings.ReadWrite\n'
    fi
    _m365_account_value "$alias" '(.calendar.enabled // false) == true' 2>/dev/null | grep -qx true && printf 'Calendars.ReadWrite\n'
    _m365_account_value "$alias" '(.contacts.enabled // false) == true' 2>/dev/null | grep -qx true && printf 'Contacts.ReadWrite\n'
    # Preserve the implemented cross-drive file access scope; capability write gates are separate.
    _m365_account_value "$alias" '(.files.enabled // false) == true' 2>/dev/null | grep -qx true && printf 'Files.ReadWrite.All\n'
    # Planner operations use task access and basic assignee-name resolution; command write gates are separate.
    if _m365_account_value "$alias" '(.planner.enabled // false) == true' 2>/dev/null | grep -qx true; then
        printf 'Tasks.ReadWrite\nUser.ReadBasic.All\n'
    fi
    return 0
}

_m365_auth_helper() {
    _m365_python "$M365_AUTH_DIR" "$M365_AUTH_DIR/scripts/auth.py" "$@"
}

_m365_powershell_bin() {
    printf '%s\n' "${M365_PWSH_BIN:-pwsh}"
}

_m365_powershell_helper() {
    printf '%s/scripts/graph.ps1\n' "$M365_AUTH_DIR"
}

_m365_powershell_ready() {
    local pwsh
    pwsh="$(_m365_powershell_bin)"
    command -v "$pwsh" >/dev/null 2>&1 || { _m365_error "PowerShell is required for Microsoft 365 auth_provider graph-powershell"; return 1; }
    "$pwsh" -NoLogo -NoProfile -Command 'if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Authentication)) { exit 1 }' >/dev/null 2>&1 || {
        _m365_error "Microsoft.Graph.Authentication is not installed for PowerShell"
        _m365_say "NEXT: Install-Module Microsoft.Graph.Authentication -Scope CurrentUser"
        return 1
    }
}

_m365_msal_ready() {
    _m365_check_command curl >/dev/null || { _m365_error "curl is required for Microsoft 365 auth_provider msal"; return 1; }
    _m365_python "$M365_AUTH_DIR" -c 'import msal' >/dev/null 2>&1 || {
        _m365_error "MSAL is not available in the selected provider environment"
        _m365_say "NEXT: run uv sync --locked in setup-microsoft-services"
        return 1
    }
}

_m365_scopes_json() {
    _m365_scopes "$1" | jq -Rsc 'split("\n") | map(select(length > 0))'
}

_m365_uri_encode() {
    jq -rn --arg value "$1" '$value | @uri'
}

_m365_prepare_powershell_request() {
    local method="$1" alias="$2" url="$3" body="$4" out="$5" pair key value separator header name headers_json scopes_json tenant input_file="" output_file=""
    shift 5
    headers_json='{}'
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --data-urlencode)
                [ "$#" -ge 2 ] || { _m365_error "--data-urlencode requires a value"; return 1; }
                pair="$2"
                key="${pair%%=*}"
                if [ "$key" = "$pair" ]; then value=""; else value="${pair#*=}"; fi
                case "$url" in *\?*) separator='&' ;; *) separator='?' ;; esac
                url="${url}${separator}$(_m365_uri_encode "$key")=$(_m365_uri_encode "$value")"
                shift 2
                ;;
            --upload-file)
                [ "$#" -ge 2 ] || { _m365_error "--upload-file requires a path"; return 1; }
                input_file="$2"
                shift 2
                ;;
            --output-file)
                [ "$#" -ge 2 ] || { _m365_error "--output-file requires a path"; return 1; }
                output_file="$2"
                shift 2
                ;;
            -H|--header)
                [ "$#" -ge 2 ] || { _m365_error "$1 requires a header value"; return 1; }
                header="$2"
                name="${header%%:*}"
                value="${header#*:}"
                while [ "${value# }" != "$value" ]; do value="${value# }"; done
                headers_json="$(jq -cn --argjson current "$headers_json" --arg name "$name" --arg value "$value" '$current + {($name): $value}')" || return 1
                shift 2
                ;;
            *)
                _m365_error "Unsupported Microsoft Graph request option for graph-powershell: $1"
                return 1
                ;;
        esac
    done
    scopes_json="$(_m365_scopes_json "$alias")" || return 1
    tenant="$(_m365_account_value "$alias" '.tenant // "organizations"')" || tenant="organizations"
    local expected_account
    expected_account="$(_m365_expected_account "$alias")" || return 1
    jq -n \
        --arg method "$method" \
        --arg uri "$url" \
        --arg body "$body" \
        --arg tenant "$tenant" \
        --arg expected_account "$expected_account" \
        --argjson headers "$headers_json" \
        --argjson scopes "$scopes_json" \
        --arg input_file "$input_file" \
        --arg output_file "$output_file" \
        '{method: $method, uri: $uri, body: $body, tenant: $tenant, expected_account: $expected_account, headers: $headers, scopes: $scopes} + (if $input_file != "" then {input_file: $input_file} else {} end) + (if $output_file != "" then {output_file: $output_file} else {} end)' > "$out"
}

_m365_powershell_invoke() {
    local mode="$1" request_path="$2" pwsh
    pwsh="$(_m365_powershell_bin)"
    "$pwsh" -NoLogo -NoProfile -File "$(_m365_powershell_helper)" -Mode "$mode" -RequestPath "$request_path"
}

_m365_powershell_auth() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" no_browser="$2" request scopes_json tenant status
    _m365_powershell_ready || return 1
    request="$(mktemp "$M365_WORK/m365-auth.XXXXXX")" || return 1
    scopes_json="$(_m365_scopes_json "$alias")" || return 1
    tenant="$(_m365_account_value "$alias" '.tenant // "organizations"')" || tenant="organizations"
    local expected_account
    expected_account="$(_m365_expected_account "$alias")" || return 1
    jq -n \
        --arg tenant "$tenant" \
        --arg expected_account "$expected_account" \
        --argjson scopes "$scopes_json" \
        --argjson no_browser "$([ -n "$no_browser" ] && printf true || printf false)" \
        '{tenant: $tenant, expected_account: $expected_account, scopes: $scopes, no_browser: $no_browser}' > "$request" || return 1
    if _m365_powershell_invoke auth "$request"; then status=0; else status=$?; fi
    rm -f "$request"
    return "$status"
)

_m365_auth() {
    local alias="${1:-}" no_browser="" provider client_id tenant token_path scope scopes=()
    [ -n "$alias" ] || { _m365_error "m365 auth requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --no-browser) no_browser="--no-browser"; shift ;;
            *) _m365_error "Unknown m365 auth option: $1"; return 1 ;;
        esac
    done
    _m365_account_exists "$alias" || { _m365_error "Unknown Microsoft 365 account alias: $alias"; return 1; }
    provider="$(_m365_auth_provider "$alias")" || return 1
    case "$provider" in
        graph-powershell)
            _m365_powershell_auth "$alias" "$no_browser"
            return
            ;;
        msal) _m365_msal_ready || return 1 ;;
        *) _m365_error "Unsupported Microsoft 365 auth_provider for alias '$alias': $provider"; return 1 ;;
    esac
    client_id="$(_m365_account_value "$alias" '.client_id')" || { _m365_error "Microsoft 365 alias '$alias' needs client_id"; return 1; }
    tenant="$(_m365_account_value "$alias" '.tenant // "organizations"')" || tenant="organizations"
    token_path="$(_m365_account_path "$alias" '.token_path')" || { _m365_error "Microsoft 365 alias '$alias' needs token_path"; return 1; }
    while IFS= read -r scope || [ -n "$scope" ]; do
        [ -n "$scope" ] && scopes+=("$scope")
    done <<EOF
$(_m365_scopes "$alias")
EOF
    if [ -n "$no_browser" ]; then
        _m365_auth_helper auth "$client_id" "$tenant" "$token_path" "${scopes[@]}" "$no_browser"
    else
        _m365_auth_helper auth "$client_id" "$tenant" "$token_path" "${scopes[@]}"
    fi
}

_m365_access_token() {
    local alias="$1" provider client_id tenant token_path scope scopes=()
    _m365_account_exists "$alias" || { _m365_error "Unknown Microsoft 365 account alias: $alias"; return 1; }
    provider="$(_m365_auth_provider "$alias")" || return 1
    [ "$provider" = "msal" ] || { _m365_error "Raw access tokens are unavailable for Microsoft 365 auth_provider '$provider'"; return 1; }
    _m365_msal_ready || return 1
    client_id="$(_m365_account_value "$alias" '.client_id')" || return 1
    tenant="$(_m365_account_value "$alias" '.tenant // "organizations"')" || tenant="organizations"
    token_path="$(_m365_account_path "$alias" '.token_path')" || return 1
    if [ ! -f "$token_path" ]; then
        _m365_error "Microsoft token cache does not exist for alias '$alias': $token_path"
        _m365_say "NEXT: run 'setup-microsoft-services/scripts/authorize auth $alias'" >&2
        return 1
    fi
    while IFS= read -r scope || [ -n "$scope" ]; do
        [ -n "$scope" ] && scopes+=("$scope")
    done <<EOF
$(_m365_scopes "$alias")
EOF
    _m365_auth_helper access-token "$client_id" "$tenant" "$token_path" "${scopes[@]}"
}

_m365_graph_base() {
    local alias="$1"
    _m365_account_value "$alias" '.graph_base // "https://graph.microsoft.com/v1.0"' 2>/dev/null || printf 'https://graph.microsoft.com/v1.0'
}

_m365_http_msal() (
    set -o pipefail
    _m365_work_begin || return 1
    local method="$1" alias="$2" url="$3" body="$4" token response http_code message
    shift 4
    token="$(_m365_access_token "$alias")" || return 1
    response="$(mktemp "$M365_WORK/m365-response.XXXXXX")" || return 1
    if [ "${1:-}" = "--output-file" ]; then
        # Raw file download: the bytes go straight to disk, following Graph's redirect to the pre-authenticated download URL.
        local output="$2"
        shift 2
        http_code="$(curl -sS -L -o "$output" -w '%{http_code}' -X "$method" "$url" \
            -H "Authorization: Bearer ${token}" "$@")" || { _m365_error "Microsoft Graph request failed before receiving a response"; rm -f "$output"; return 1; }
        case "$http_code" in
            2??) rm -f "$response"; return 0 ;;
            *) mv "$output" "$response" ;;
        esac
    elif [ "${1:-}" = "--upload-file" ]; then
        # Raw file upload: curl --upload-file sends the bytes; remaining args are headers.
        local upload="$2"
        shift 2
        http_code="$(curl -sS -o "$response" -w '%{http_code}' -X "$method" "$url" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/octet-stream" \
            --upload-file "$upload" "$@")" || { _m365_error "Microsoft Graph request failed before receiving a response"; return 1; }
    elif [ -n "$body" ]; then
        http_code="$(curl -sS -o "$response" -w '%{http_code}' -X "$method" "$url" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json; charset=utf-8" \
            --data-binary "$body" "$@")" || { _m365_error "Microsoft Graph request failed before receiving a response"; return 1; }
    else
        http_code="$(curl -sS -o "$response" -w '%{http_code}' -X "$method" --get "$url" \
            -H "Authorization: Bearer ${token}" \
            -H "Accept: application/json" "$@")" || { _m365_error "Microsoft Graph request failed before receiving a response"; return 1; }
    fi
    case "$http_code" in
        2??) cat "$response" ;;
        *)
            message="$(jq -r 'if .error then ((.error.code // "GraphError") + ": " + (.error.message // "request failed")) else empty end' "$response" 2>/dev/null)"
            [ -n "$message" ] || message="Microsoft Graph returned HTTP $http_code"
            _m365_error "$message"
            return 1
            ;;
    esac
)

_m365_http_powershell() (
    set -o pipefail
    _m365_work_begin || return 1
    local method="$1" alias="$2" url="$3" body="$4" request status
    shift 4
    _m365_powershell_ready || return 1
    request="$(mktemp "$M365_WORK/m365-request.XXXXXX")" || return 1
    _m365_prepare_powershell_request "$method" "$alias" "$url" "$body" "$request" "$@" || { rm -f "$request"; return 1; }
    if _m365_powershell_invoke request "$request"; then status=0; else status=$?; fi
    rm -f "$request"
    return "$status"
)

_m365_http() {
    local method="$1" alias="$2" url="$3" body="$4" provider
    shift 4
    _m365_validate_url "$url" || return 1
    provider="$(_m365_auth_provider "$alias")" || return 1
    case "$provider" in
        graph-powershell) _m365_http_powershell "$method" "$alias" "$url" "$body" "$@" ;;
        msal) _m365_http_msal "$method" "$alias" "$url" "$body" "$@" ;;
        *) _m365_error "Unsupported Microsoft 365 auth_provider for alias '$alias': $provider"; return 1 ;;
    esac
}

_m365_get() {
    local alias="$1" url="$2"
    shift 2
    _m365_http GET "$alias" "$url" "" "$@"
}

_m365_write() {
    local method="$1" alias="$2" url="$3" body="$4"
    _m365_http "$method" "$alias" "$url" "$body"
}

_m365_get_paginated() (
    set -o pipefail
    _m365_work_begin || return 1
    local alias="$1" max_results="$2" out="$3" url="$4" page next count=0 page_number=0 cap
    local pages=()
    shift 4
    case "$max_results" in ''|*[!0-9]*) _m365_error 'max_results must be a positive integer'; return 1 ;; esac
    [ "$max_results" -gt 0 ] || return 1
    cap="$(_m365_account_value "$alias" '.max_pages // 100')" || cap=100
    case "$cap" in ''|*[!0-9]*) _m365_error 'max_pages must be a positive integer'; return 1 ;; esac
    while :; do
        page_number=$((page_number + 1))
        [ "$page_number" -le "$cap" ] || { _m365_error 'Microsoft read exceeded the configured page cap'; return 1; }
        page="$M365_WORK/page-$page_number.json"
        _m365_get "$alias" "$url" "$@" > "$page" || return 1
        set --
        jq -e 'type == "object" and .error == null and (.value | type == "array")' "$page" >/dev/null || { _m365_error 'Invalid Microsoft collection response'; return 1; }
        pages+=("$page")
        count="$(jq -s '[.[].value[]?] | length' "${pages[@]}")" || return 1
        next="$(jq -r '."@odata.nextLink" // empty' "$page")" || return 1
        if [ "$count" -ge "$max_results" ]; then
            if [ "$count" -gt "$max_results" ] || [ -n "$next" ]; then
                if [ "${M365_REQUIRE_COMPLETE:-0}" = 1 ]; then _m365_error 'Microsoft result limit reached; complete export refused'; return 1; fi
                printf 'WARN: Microsoft results truncated at configured max_results\n' >&2
            fi
            break
        fi
        [ -n "$next" ] || break
        url="$next"
    done
    jq -s --argjson max "$max_results" '{value: ([.[].value[]?] | .[:$max])}' "${pages[@]}" > "$out"
)

_m365_profile_json() {
    local alias="$1"
    _m365_get "$alias" "$(_m365_graph_base "$alias")/me" \
        --data-urlencode "\$select=id,displayName,givenName,surname,mail,userPrincipalName"
}

_m365_profile() {
    local alias="${1:-}" json=0 profile
    [ -n "$alias" ] || { _m365_error "m365 profile requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json) json=1; shift ;;
            *) _m365_error "Unknown m365 profile option: $1"; return 1 ;;
        esac
    done
    profile="$(_m365_profile_json "$alias")" || return 1
    if [ "$json" -eq 1 ]; then
        printf '%s\n' "$profile"
    else
        printf '%s' "$profile" | jq -r '
          "Display name: " + (.displayName // "") + "\n" +
          "Mail: " + (.mail // "") + "\n" +
          "User principal: " + (.userPrincipalName // "") + "\n" +
          "Graph user ID: " + (.id // "")
        '
    fi
}

_m365_profile_email() {
    local alias="$1"
    _m365_profile_json "$alias" | jq -r '.mail // .userPrincipalName // ""'
}


# Keep existing private storage independent from the relocated provider source.
_m365_config_dir() {
    if [ -n "${M365_CONFIG_DIR:-}" ]; then printf '%s\n' "$M365_CONFIG_DIR"; return; fi
    local previous="${M365_AUTH_DIR}/../authorize-microsoft"
    if [ -f "$previous/.env" ] || [ -f "$previous/m365-accounts.json" ]; then
        (cd "$previous" && pwd)
    else printf '%s\n' "$M365_AUTH_DIR"; fi
}
