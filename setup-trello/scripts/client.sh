#!/usr/bin/env bash
##- Trello credentials and bounded HTTP access; no personal workspace dependency.
_trello_say() { printf '%s\n' "$*"; }
_trello_error() { printf 'ERROR: %s\n' "$*" >&2; }
_trello_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }
_trello_check_command() { command -v "$1" >/dev/null 2>&1; }
_trello_require_var() { [ -n "${!1:-}" ] || { _trello_error "$1 is not set"; return 1; }; }

# Parse provider configuration as literal data. Never source it, eval values, or expand command substitutions.
_trello_load_env() {
    local config line key value present
    if [ -n "${TRELLO_ENV_FILE:-}" ]; then
        config="$TRELLO_ENV_FILE"
        [ -f "$config" ] || { _trello_error 'The selected TRELLO_ENV_FILE does not exist'; return 1; }
    else
        config="$(_trello_config_dir)/.env"
        [ -f "$config" ] || return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_trello_trim "$line")"
        case "$line" in ''|\#*) continue ;; export\ *) line="${line#export }" ;; esac
        case "$line" in *=*) ;; *) _trello_error 'Invalid Trello env assignment'; return 1 ;; esac
        key="$(_trello_trim "${line%%=*}")"
        case "$key" in *[!A-Za-z0-9_]*|TRELLO_ENV_FILE|TRELLO_CONFIG_DIR|TRELLO_AUTH_DIR) _trello_error 'Invalid Trello env key'; return 1 ;; TRELLO_[A-Za-z_]*) ;; *) _trello_error 'Use TRELLO_* keys in the Trello env file'; return 1 ;; esac
        value="$(_trello_trim "${line#*=}")"
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _trello_error 'Unclosed quote in Trello env file'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _trello_error 'Unclosed quote in Trello env file'; return 1 ;; esac ;;
        esac
        present="${!key+x}"
        [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

_trello_ready() {
    _trello_require_var TRELLO_API_KEY || return 1
    _trello_require_var TRELLO_TOKEN || return 1
    _trello_check_command curl >/dev/null || { _trello_error "curl is required"; return 1; }
    _trello_check_command jq >/dev/null || { _trello_error "jq is required"; return 1; }
    return 0
}

_trello_get_http() {
    local endpoint="$1"
    shift
    curl -fsS --get "https://api.trello.com/1${endpoint}" \
        --data-urlencode "key=${TRELLO_API_KEY}" \
        --data-urlencode "token=${TRELLO_TOKEN}" \
        "$@"
}

_trello_write_ready() {
    _trello_require_var TRELLO_API_KEY || return 1
    _trello_require_var TRELLO_WRITE_TOKEN || return 1
    _trello_check_command curl >/dev/null || { _trello_error "curl is required"; return 1; }
    _trello_check_command jq >/dev/null || { _trello_error "jq is required"; return 1; }
    return 0
}

_trello_write_http() {
    local method="$1"
    local endpoint="$2"
    shift 2
    curl -fsS -X "$method" "https://api.trello.com/1${endpoint}" \
        --data-urlencode "key=${TRELLO_API_KEY}" \
        --data-urlencode "token=${TRELLO_WRITE_TOKEN}" \
        "$@"
}


# Keep existing private storage independent from the relocated provider source.
_trello_config_dir() {
    if [ -n "${TRELLO_CONFIG_DIR:-}" ]; then printf '%s\n' "$TRELLO_CONFIG_DIR"; return; fi
    local previous="${TRELLO_AUTH_DIR}/../authorize-trello"
    if [ -f "$previous/.env" ]; then
        (cd "$previous" && pwd)
    else printf '%s\n' "$TRELLO_AUTH_DIR"; fi
}

# Direct operation builders cannot accidentally bypass the preview controller.
_trello_get() { _trello_get_http "$@"; }
_trello_write() { _trello_error "Use the Trello command entrypoint and --execute; direct writes are disabled"; return 1; }
