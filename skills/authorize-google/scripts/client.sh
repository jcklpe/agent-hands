#!/usr/bin/env bash
##- Shared Google authorization and account configuration, independent of capability implementations.
GOOGLE_AUTH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_google_error() { printf 'ERROR: %s\n' "$*" >&2; }
_google_say() { printf '%s\n' "$*"; }
_google_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }
_google_python() {
    local project="$1"
    shift
    if [ -n "${GOOGLE_PYTHON:-}" ]; then "$GOOGLE_PYTHON" "$@"
    elif command -v uv >/dev/null 2>&1; then uv run --project "$project" python "$@"
    else _google_error 'Install uv or set GOOGLE_PYTHON to a compatible Python 3.11+ executable'; return 1
    fi
}
_google_load_env() {
    local config line key value present
    config="${GOOGLE_ENV_FILE:-${GOOGLE_CONFIG_DIR:-$GOOGLE_AUTH_DIR}/.env}"
    if [ ! -f "$config" ]; then
        [ -z "${GOOGLE_ENV_FILE:-}" ] && return 0
        _google_error 'Selected GOOGLE_ENV_FILE does not exist'; return 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_google_trim "$line")"
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) _google_error 'Invalid Google env assignment'; return 1 ;; esac
        key="$(_google_trim "${line%%=*}")"; value="$(_google_trim "${line#*=}")"
        case "$key" in GOOGLE_ACCOUNTS_PATH|GOOGLE_PYTHON) ;; *) _google_error 'Unsupported Google configuration key'; return 1 ;; esac
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _google_error 'Unclosed configuration quote'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _google_error 'Unclosed configuration quote'; return 1 ;; esac ;;
        esac
        present="${!key+x}"; [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

_google_accounts_path() {
    _google_config_path "${GOOGLE_ACCOUNTS_PATH:-google-accounts.json}"
}

_google_config_path() {
    case "$1" in
        '') return 1 ;;
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "${GOOGLE_CONFIG_DIR:-$GOOGLE_AUTH_DIR}" "$1" ;;
    esac
}

_google_accounts_ready() {
    local config
    config="$(_google_accounts_path)"
    command -v curl >/dev/null 2>&1 || { _google_error 'curl is required'; return 1; }
    command -v jq >/dev/null 2>&1 || { _google_error 'jq is required'; return 1; }
    [ -f "$config" ] || { _google_error 'Google account config is missing; see setup-google-services'; return 1; }
    jq -e '
        (.accounts | type == "array") and
        ([.accounts[].alias] | length == (unique | length)) and
        all(.accounts[]; (.alias | type == "string" and test("^[A-Za-z0-9_-]+$")) and
            (.token_path | type == "string" and length > 0) and
            ((.credentials_path // "google-credentials.json") | type == "string" and length > 0))
    ' "$config" >/dev/null 2>&1 || { _google_error 'Invalid Google config: use unique simple aliases and credential/token paths'; return 1; }
}

_google_account_exists() {
    local alias="$1"
    _google_accounts_ready || return 1
    jq -e --arg alias "$alias" 'any(.accounts[]?; .alias == $alias)' "$(_google_accounts_path)" >/dev/null
}

_google_account_value() {
    local alias="$1"
    local filter="$2"
    jq -er --arg alias "$alias" "(.accounts[]? | select(.alias == \$alias) | ${filter}) // empty" "$(_google_accounts_path)"
}

_google_account_path() {
    local alias="$1"
    local filter="$2"
    local value
    value="$(_google_account_value "$alias" "$filter")" || return 1
    _google_config_path "$value"
}

_google_account_email() {
    local alias="$1"
    _google_account_value "$alias" '.email // ""' 2>/dev/null || printf ''
}

_google_accounts_list() {
    _google_accounts_ready || return 1
    jq -r '
      (.accounts // [])[] |
      "- " + (.alias // "missing-alias") +
      " | email: " + (.email // "") +
      " | gmail: " + (((.gmail.enabled // false) == true) | tostring) +
      " | gmail labels: " + (((.gmail.write_enabled // false) == true) | tostring) +
      " | gmail filters: " + (((.gmail.filters_enabled // false) == true) | tostring) +
      " | drive: " + (((.drive.enabled // false) == true) | tostring) +
      " | docs: " + (((.docs.enabled // false) == true) | tostring)
    ' "$(_google_accounts_path)"
}

_google_enabled_aliases() {
    local service="$1"
    _google_accounts_ready || return 1
    jq -r --arg service "$service" '
      (.accounts // [])[] |
      select((.[$service].enabled // false) == true) |
      .alias
    ' "$(_google_accounts_path)"
}

_google_account_scopes() {
    local alias="$1"
    _google_account_exists "$alias" || { _google_error "Unknown Google account alias: $alias"; return 1; }
    jq -r --arg alias "$alias" '
      (.accounts[]? | select(.alias == $alias)) as $account |
      [
        (if (($account.gmail.enabled // false) == true) then
          "https://www.googleapis.com/auth/gmail.readonly",
          (if (($account.gmail.write_enabled // false) == true) then
            "https://www.googleapis.com/auth/gmail.modify"
          else empty end),
          (if (($account.gmail.filters_enabled // false) == true) then
            "https://www.googleapis.com/auth/gmail.settings.basic"
          else empty end)
        else empty end),
        (if (($account.drive.enabled // false) == true) then
          "https://www.googleapis.com/auth/drive.metadata.readonly",
          "https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly",
          (if (($account.drive.write_enabled // false) == true) then
            "https://www.googleapis.com/auth/drive.file"
          else empty end)
        else empty end)
        ,(if (($account.docs.enabled // false) == true) then
          "https://www.googleapis.com/auth/documents.readonly"
        else empty end),
        (if (($account.docs.comments_enabled // false) == true) then
          "https://www.googleapis.com/auth/drive.readonly"
        else empty end)
      ] | unique | .[]
    ' "$(_google_accounts_path)"
}

_google_oauth_helper() {
    _google_python "$GOOGLE_AUTH_DIR" "${GOOGLE_AUTH_DIR}/scripts/oauth.py" "$@"
}

_google_auth() {
    local alias="${1:-}" credentials_path token_path no_browser="" docs_write="" docs_comment=""
    local scopes=() scope

    [ -n "$alias" ] || { _google_error "google auth requires ALIAS"; return 1; }
    shift || true
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --no-browser) no_browser="--no-browser"; shift ;;
            --docs-write) docs_write="1"; shift ;;
            --docs-comment) docs_comment="1"; shift ;;
            *) _google_error "Unknown google auth option: $1"; return 1 ;;
        esac
    done

    _google_account_exists "$alias" || { _google_error "Unknown Google account alias: $alias"; return 1; }
    credentials_path="$(_google_account_path "$alias" '.credentials_path // "google-credentials.json"')" || return 1
    token_path="$(_google_account_path "$alias" '.token_path')" || { _google_error "Google account '$alias' needs token_path"; return 1; }
    if [ ! -f "$credentials_path" ]; then
        _google_error "Google credentials file does not exist: $credentials_path"
        return 1
    fi

    while IFS= read -r scope || [ -n "$scope" ]; do
        [ -n "$scope" ] || continue
        scopes+=( "$scope" )
    done <<EOF
$(_google_account_scopes "$alias")
EOF

    if [ "$docs_write" = "1" ]; then
        scopes+=( "https://www.googleapis.com/auth/documents" )
    fi
    # Drive comments on files this app did not create need the full Drive scope; drive.file cannot reach them.
    if [ "$docs_comment" = "1" ]; then
        scopes+=( "https://www.googleapis.com/auth/drive" )
    fi

    if [ "${#scopes[@]}" -eq 0 ]; then
        _google_error "Google account '$alias' has no enabled service scopes"
        return 1
    fi

    if [ -n "$no_browser" ]; then
        _google_oauth_helper auth "$credentials_path" "$token_path" "${scopes[@]}" "$no_browser"
    else
        _google_oauth_helper auth "$credentials_path" "$token_path" "${scopes[@]}"
    fi
}

_google_access_token() {
    local alias="$1" credentials_path token_path
    _google_account_exists "$alias" || { _google_error "Unknown Google account alias: $alias"; return 1; }
    credentials_path="$(_google_account_path "$alias" '.credentials_path // "google-credentials.json"')" || return 1
    token_path="$(_google_account_path "$alias" '.token_path')" || { _google_error "Google account '$alias' needs token_path"; return 1; }
    if [ ! -f "$token_path" ]; then
        _google_error "Google token file does not exist for alias '$alias': $token_path"
        _google_say "NEXT: run authorize-google/scripts/authorize auth $alias" >&2
        return 1
    fi
    _google_oauth_helper access-token "$credentials_path" "$token_path"
}

_google_get_url() {
    local alias="$1"
    local url="$2"
    local token
    shift 2
    token="$(_google_access_token "$alias")" || return 1
    curl -fsS --get "$url" \
        -H "Authorization: Bearer ${token}" \
        "$@"
}

