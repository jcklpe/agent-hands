#!/usr/bin/env bash
##- Odoo account access, request pacing, and bounded transport support. No project or vault dependency.


_odoo_say() { printf '%s\n' "$*"; }
_odoo_error() { printf 'ERROR: %s\n' "$*" >&2; }
_odoo_check_command() { command -v "$1" >/dev/null 2>&1; }
_odoo_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

_odoo_resolve_path() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$(_odoo_config_dir)" "$1" ;;
    esac
}

# Parse provider configuration as literal data. Never source it, eval values, or expand command substitutions.
_odoo_load_env() {
    local config line key value present
    if [ -n "${ODOO_ENV_FILE:-}" ]; then
        config="$(_odoo_resolve_path "$ODOO_ENV_FILE")"
        [ -f "$config" ] || { _odoo_error 'The selected ODOO_ENV_FILE does not exist'; return 1; }
    else
        config="$(_odoo_config_dir)/.env"
        [ -f "$config" ] || return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_odoo_trim "$line")"
        case "$line" in ''|\#*) continue ;; export\ *) line="${line#export }" ;; esac
        case "$line" in *=*) ;; *) _odoo_error 'Invalid Odoo env assignment'; return 1 ;; esac
        key="$(_odoo_trim "${line%%=*}")"
        case "$key" in *[!A-Za-z0-9_]*|ODOO_ENV_FILE|ODOO_CONFIG_DIR|ODOO_AUTH_DIR) _odoo_error 'Invalid Odoo env key'; return 1 ;; ODOO_[A-Za-z_]*) ;; *) _odoo_error 'Use ODOO_* keys in the Odoo env file'; return 1 ;; esac
        value="$(_odoo_trim "${line#*=}")"
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _odoo_error 'Unclosed quote in Odoo env file'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _odoo_error 'Unclosed quote in Odoo env file'; return 1 ;; esac ;;
        esac
        present="${!key+x}"
        [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

_odoo_accounts_path() {
    _odoo_resolve_path "${ODOO_ACCOUNTS_PATH:-odoo-accounts.json}"
}

_odoo_accounts_ready() {
    local config
    config="$(_odoo_accounts_path)"
    _odoo_check_command jq >/dev/null || { _odoo_error "jq is required"; return 1; }
    _odoo_check_command curl >/dev/null || { _odoo_error "curl is required"; return 1; }
    if [ ! -f "$config" ]; then
        _odoo_error "Odoo account config does not exist: $config"
        _odoo_say "NEXT: cp ${ODOO_AUTH_DIR}/odoo-accounts.example.json $config"
        return 1
    fi
    jq -e '.accounts | type == "array"' "$config" >/dev/null 2>&1 || { _odoo_error "Odoo account config must contain an accounts array"; return 1; }
}

_odoo_account_exists() {
    local alias="$1"
    _odoo_accounts_ready || return 1
    jq -e --arg alias "$alias" 'any(.accounts[]?; .alias == $alias)' "$(_odoo_accounts_path)" >/dev/null
}

_odoo_account_value() {
    local alias="$1" filter="$2"
    jq -er --arg alias "$alias" "(.accounts[]? | select(.alias == \$alias) | ${filter}) // empty" "$(_odoo_accounts_path)"
}

_odoo_accounts_list() {
    _odoo_accounts_ready || return 1
    jq -r '(.accounts // [])[] | "- " + (.alias // "missing-alias") + " | url: " + (.base_url // "missing-url") + " | database: " + (.database // "(host-routed)") + " | key env: " + (.api_key_env // "missing")' "$(_odoo_accounts_path)"
}

_odoo_base_url() {
    local alias="$1" value
    value="$(_odoo_account_value "$alias" '.base_url')" || { _odoo_error "Odoo alias '$alias' needs base_url"; return 1; }
    case "$value" in https://*) ;; *) _odoo_error "Odoo base_url must use https://"; return 1 ;; esac
    printf '%s\n' "${value%/}"
}

_odoo_api_key() {
    local alias="$1" key_env value
    key_env="$(_odoo_account_value "$alias" '.api_key_env')" || { _odoo_error "Odoo alias '$alias' needs api_key_env"; return 1; }
    case "$key_env" in ''|[0-9]*|*[!A-Za-z0-9_]*) _odoo_error "Invalid Odoo api_key_env for alias '$alias'"; return 1 ;; esac
    value="${!key_env:-}"
    [ -n "$value" ] || { _odoo_error "$key_env is not set"; return 1; }
    printf '%s' "$value"
}

_odoo_request_state_path() {
    _odoo_resolve_path "${ODOO_REQUEST_STATE_PATH:-odoo-last-request}"
}

_odoo_wait_for_request_slot() {
    local interval="${ODOO_MIN_REQUEST_INTERVAL_SECONDS:-5}" state now last elapsed wait_seconds state_dir
    case "$interval" in ''|*[!0-9]*) _odoo_error "ODOO_MIN_REQUEST_INTERVAL_SECONDS must be a non-negative integer"; return 1 ;; esac
    [ "$interval" -le 300 ] || { _odoo_error "ODOO_MIN_REQUEST_INTERVAL_SECONDS must not exceed 300"; return 1; }
    [ "$interval" -gt 0 ] || return 0

    state="$(_odoo_request_state_path)" || return 1
    state_dir="${state%/*}"
    [ "$state_dir" = "$state" ] || mkdir -p "$state_dir" || return 1
    now="$(date +%s)" || return 1
    if [ -f "$state" ]; then
        IFS= read -r last < "$state" || last=""
        case "$last" in
            ''|*[!0-9]*) ;;
            *)
                elapsed=$((now - last))
                if [ "$elapsed" -lt "$interval" ]; then
                    wait_seconds=$((interval - elapsed))
                    sleep "$wait_seconds" || return 1
                fi
                ;;
        esac
    fi
    date +%s > "$state"
}

_odoo_http() {
    local alias="$1" path="$2" body="$3" base key database response http_code message
    _odoo_account_exists "$alias" || { _odoo_error "Unknown Odoo account alias: $alias"; return 1; }
    base="$(_odoo_base_url "$alias")" || return 1
    key="$(_odoo_api_key "$alias")" || return 1
    database="$(_odoo_account_value "$alias" '.database')" || database=""
    response="$(mktemp "${TMPDIR:-/tmp}/odoo-response.XXXXXX")" || return 1
    if [ -n "$database" ]; then
        http_code="$(curl -sS -o "$response" -w '%{http_code}' -X POST "${base}${path}" -H "Authorization: bearer ${key}" -H 'Content-Type: application/json; charset=utf-8' -H "X-Odoo-Database: ${database}" -H 'User-Agent: bounded-odoo-cli/1.0' --data-binary "$body")" || { rm -f "$response"; _odoo_error "Odoo request failed before receiving a response"; return 1; }
    else
        http_code="$(curl -sS -o "$response" -w '%{http_code}' -X POST "${base}${path}" -H "Authorization: bearer ${key}" -H 'Content-Type: application/json; charset=utf-8' -H 'User-Agent: bounded-odoo-cli/1.0' --data-binary "$body")" || { rm -f "$response"; _odoo_error "Odoo request failed before receiving a response"; return 1; }
    fi
    case "$http_code" in
        2??) cat "$response"; rm -f "$response" ;;
        *)
            message="$(jq -r '.message // .error.message // .error.data.message // empty' "$response" 2>/dev/null)"
            [ -n "$message" ] || message="Odoo returned HTTP $http_code"
            rm -f "$response"
            _odoo_error "$message"
            return 1
            ;;
    esac
}

_odoo_call() {
    local alias="$1" model="$2" method="$3" body="$4"
    _odoo_wait_for_request_slot || return 1
    _odoo_http "$alias" "/json/2/${model}/${method}" "$body"
}

# Keep existing private storage independent from the relocated provider source.
_odoo_config_dir() {
    if [ -n "${ODOO_CONFIG_DIR:-}" ]; then printf '%s\n' "$ODOO_CONFIG_DIR"; return; fi
    local previous="${ODOO_AUTH_DIR}/../authorize-odoo"
    if [ -f "$previous/.env" ] || [ -f "$previous/odoo-accounts.json" ]; then
        (cd "$previous" && pwd)
    else printf '%s\n' "$ODOO_AUTH_DIR"; fi
}
