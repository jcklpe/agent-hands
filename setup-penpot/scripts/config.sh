#!/usr/bin/env bash
# Shared Penpot configuration helpers for declared consumers. Sourcing reads nothing and contacts no server.
PENPOT_SETUP_DIR="${PENPOT_SETUP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

_penpot_error() { printf 'penpot: %s\n' "$1" >&2; }
_penpot_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

_penpot_config_dir() { printf '%s' "${PENPOT_CONFIG_DIR:-$PENPOT_SETUP_DIR}"; }

_penpot_resolve_path() {
    case "$1" in /*) printf '%s' "$1" ;; *) printf '%s/%s' "$(_penpot_config_dir)" "$1" ;; esac
}

# Prints the env file in use, or nothing when no file applies.
_penpot_env_path() {
    local config
    if [ -n "${PENPOT_ENV_FILE:-}" ]; then
        _penpot_resolve_path "$PENPOT_ENV_FILE"
    else
        config="$(_penpot_config_dir)/.env"
        [ -f "$config" ] && printf '%s' "$config"
    fi
    return 0
}

_penpot_load_env() {
    local config line key value present
    config="$(_penpot_env_path)"
    if [ -n "${PENPOT_ENV_FILE:-}" ] && [ ! -f "$config" ]; then
        _penpot_error 'The selected PENPOT_ENV_FILE does not exist'
        return 1
    fi
    [ -n "$config" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_penpot_trim "$line")"
        case "$line" in ''|\#*) continue ;; export\ *) line="${line#export }" ;; esac
        case "$line" in *=*) ;; *) _penpot_error 'Invalid Penpot env assignment'; return 1 ;; esac
        key="$(_penpot_trim "${line%%=*}")"
        case "$key" in *[!A-Za-z0-9_]*|PENPOT_ENV_FILE|PENPOT_CONFIG_DIR|PENPOT_SETUP_DIR|PENPOT_PYTHON) _penpot_error 'Invalid Penpot env key'; return 1 ;; PENPOT_[A-Za-z_]*) ;; *) _penpot_error 'Use PENPOT_* keys in the Penpot env file'; return 1 ;; esac
        value="$(_penpot_trim "${line#*=}")"
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _penpot_error 'Unclosed quote in Penpot env file'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _penpot_error 'Unclosed quote in Penpot env file'; return 1 ;; esac ;;
        esac
        present="${!key+x}"
        [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

# Prints the host part of a URL; the host is not secret.
_penpot_url_host() {
    local rest="${1#*://}"
    rest="${rest%%[/?#]*}"
    rest="${rest##*@}"
    case "$rest" in \[*) rest="${rest%%]*}]" ;; *) rest="${rest%%:*}" ;; esac
    printf '%s' "$rest"
}

# Validates PENPOT_MCP_SERVER_URL and prints it for capture by a consumer. Never echo the result to a terminal or log.
_penpot_server_url() {
    local url="${PENPOT_MCP_SERVER_URL:-}" host query token
    [ -n "$url" ] || { _penpot_error 'PENPOT_MCP_SERVER_URL is not configured; see the setup-penpot skill'; return 1; }
    case "$url" in *[[:space:]]*) _penpot_error 'PENPOT_MCP_SERVER_URL must not contain whitespace'; return 1 ;; esac
    host="$(_penpot_url_host "$url")"
    case "$url" in
        https://*) ;;
        http://*)
            case "$host" in 127.0.0.1|localhost|\[::1\]) ;; *) _penpot_error 'PENPOT_MCP_SERVER_URL must use HTTPS except for a loopback server'; return 1 ;; esac ;;
        *) _penpot_error 'PENPOT_MCP_SERVER_URL must be an HTTPS URL'; return 1 ;;
    esac
    [ -n "$host" ] || { _penpot_error 'PENPOT_MCP_SERVER_URL has no host'; return 1; }
    case "$url" in
        https://*)
            query="${url#*\?}"
            [ "$query" != "$url" ] || query=''
            token="$(printf '%s' "$query" | tr '&' '\n' | sed -n 's/^userToken=//p' | head -n 1)"
            [ -n "$token" ] || { _penpot_error 'PENPOT_MCP_SERVER_URL has no userToken; copy the full server URL from Penpot'; return 1; }
            ;;
    esac
    printf '%s' "$url"
}

# Prints the octal permission bits of a file on GNU or BSD systems.
_penpot_file_mode() {
    stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null
}

_penpot_python() {
    local project="$1"
    shift
    if [ -n "${PENPOT_PYTHON:-}" ]; then "$PENPOT_PYTHON" "$@"
    elif command -v uv >/dev/null 2>&1; then uv run --project "$project" --locked --quiet python "$@"
    else _penpot_error 'Install uv or set PENPOT_PYTHON to a Python 3.11+ executable with the use-penpot dependencies'; return 1
    fi
}
