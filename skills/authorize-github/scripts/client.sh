#!/usr/bin/env bash
##- GitHub account/configuration and narrow shared response helpers; gh owns authentication.
_github_say() { printf '%s\n' "$*"; }
_github_error() { printf 'ERROR: %s\n' "$*" >&2; }
_github_warn() { printf 'WARN: %s\n' "$*" >&2; }
_github_trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }
_github_repos_config() {
    case "${GITHUB_REPOS_PATH:-github-repos.json}" in
        /*) printf '%s\n' "$GITHUB_REPOS_PATH" ;;
        *) printf '%s/%s\n' "${GITHUB_CONFIG_DIR:-$GITHUB_AUTH_DIR}" "${GITHUB_REPOS_PATH:-github-repos.json}" ;;
    esac
}
_github_ready() {
    command -v gh >/dev/null 2>&1 || { _github_error 'gh is required'; return 1; }
    command -v jq >/dev/null 2>&1 || { _github_error 'jq is required'; return 1; }
    gh auth status >/dev/null 2>&1 || { _github_error 'GitHub CLI authentication failed; review the selected gh account'; return 1; }
}
_github_config_ready() {
    local config
    config="$(_github_repos_config)"
    [ -f "$config" ] || { _github_error 'Repository aliases require github-repos.json; use the adjacent example'; return 1; }
    jq -e '
        (.repos | type == "array") and
        ([.repos[].alias] | length == (unique | length)) and
        all(.repos[]; (.alias | type == "string" and test("^[A-Za-z0-9_-]+$")) and
            (.owner | type == "string" and test("^[A-Za-z0-9_-]+$")) and
            (.repo | type == "string" and test("^[A-Za-z0-9_.-]+$") and . != "." and . != "..") and
            ((.project_owner // .owner) | type == "string" and test("^[A-Za-z0-9_-]+$")) and
            all((.projects // [])[]; (.number | type == "number" and . > 0 and floor == .) and
                ((.name // ("project-" + (.number|tostring))) | type == "string" and test("^[A-Za-z0-9_-]+$"))))
    ' "$config" >/dev/null 2>&1 || { _github_error 'Invalid repository config: use unique simple aliases, owner/repo names, and positive project numbers with simple export names'; return 1; }
}
_github_render_file() {
    if [ -n "${GITHUB_PYTHON:-}" ]; then "$GITHUB_PYTHON" "$@"
    elif command -v uv >/dev/null 2>&1; then uv run --project "$GITHUB_USE_DIR" python "$@"
    else _github_error 'Install uv or set GITHUB_PYTHON to a compatible Python 3.11+ executable'; return 1
    fi
}
_github_render_items() { _github_render_file "${GITHUB_AUTH_DIR}/scripts/render_items.py" "$@"; }

_github_load_env() {
    local config line key value present
    config="${GITHUB_ENV_FILE:-${GITHUB_CONFIG_DIR:-$GITHUB_AUTH_DIR}/.env}"
    if [ ! -f "$config" ]; then
        [ -z "${GITHUB_ENV_FILE:-}" ] && return 0
        _github_error 'Selected GITHUB_ENV_FILE does not exist'; return 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(_github_trim "$line")"
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in *=*) ;; *) _github_error 'Invalid GitHub env assignment'; return 1 ;; esac
        key="$(_github_trim "${line%%=*}")"; value="$(_github_trim "${line#*=}")"
        case "$key" in GITHUB_REPOS_PATH|GH_TOKEN|GH_HOST) ;; *) _github_error 'Unsupported GitHub configuration key'; return 1 ;; esac
        case "$value" in
            \"*) case "$value" in *\") value="${value#\"}"; value="${value%\"}" ;; *) _github_error 'Unclosed configuration quote'; return 1 ;; esac ;;
            \'*) case "$value" in *\') value="${value#\'}"; value="${value%\'}" ;; *) _github_error 'Unclosed configuration quote'; return 1 ;; esac ;;
        esac
        present="${!key+x}"; [ -n "$present" ] || export "$key=$value"
    done < "$config"
}

_github_repo_entry() {
    local alias="$1" entry
    _github_config_ready || return 1
    entry="$(jq -c --arg a "$alias" '.repos[] | select(.alias == $a)' "$(_github_repos_config)")" || return 1
    [ -n "$entry" ] || { _github_error "No repo configured with alias: $alias"; return 1; }
    printf '%s\n' "$entry"
}

_github_resolve_repo() {
    local arg="$1" entry
    case "$arg" in
        */*)
            printf '%s\n' "$arg" | grep -Eq '^[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+$' || { _github_error 'Expected OWNER/REPO'; return 1; }
            case "${arg#*/}" in .|..) _github_error 'Invalid repository name'; return 1 ;; esac
            printf '%s\n' "$arg"; return 0 ;;
    esac
    entry="$(_github_repo_entry "$arg")" || return 1
    printf '%s/%s\n' "$(printf '%s' "$entry" | jq -r '.owner')" "$(printf '%s' "$entry" | jq -r '.repo')"
}

_github_list_repos() {
    _github_config_ready || return 1
    jq -r '.repos[] | "\(.alias) | \(.owner)/\(.repo) | issues:\(.issues // true) prs:\(.prs // false) discussions:\(.discussions // false) projects:\((.projects // []) | length)"' "$(_github_repos_config)"
}

_github_export_begin() {
    local destination="$1"
    [ -n "$destination" ] || { _github_error 'export requires --output DIRECTORY'; return 1; }
    mkdir -p "$destination" || return 1
    GITHUB_EXPORT_DESTINATION="$destination"
    GITHUB_EXPORT_PENDING=""
    GITHUB_EXPORT_WORK="$(mktemp -d "${destination}/.github-export.XXXXXX")" || return 1
    mkdir "$GITHUB_EXPORT_WORK/new" "$GITHUB_EXPORT_WORK/previous" || return 1
    trap '_github_export_cleanup' EXIT
    trap 'exit 130' HUP INT TERM
}

# Publish only this capability's named artifacts after all retrieval/rendering succeeds. Each replacement has a recovery copy; publication across several artifacts is not a transaction.
_github_publish_export() {
    local destination="$1" name
    shift
    for name in "$@"; do
        [ ! -L "$destination/$name" ] || { _github_error "Refusing to replace symlink: $name"; return 1; }
        GITHUB_EXPORT_PENDING="$name"
        if [ -e "$destination/$name" ]; then mv "$destination/$name" "$GITHUB_EXPORT_WORK/previous/$name" || return 1; fi
        if [ -e "$GITHUB_EXPORT_WORK/new/$name" ]; then
            if ! mv "$GITHUB_EXPORT_WORK/new/$name" "$destination/$name"; then
                if [ -e "$GITHUB_EXPORT_WORK/previous/$name" ]; then
                    mv "$GITHUB_EXPORT_WORK/previous/$name" "$destination/$name" || { trap - EXIT; _github_error "Restore failed; recovery files retained at $GITHUB_EXPORT_WORK"; return 1; }
                fi
                _github_error 'Publication failed; inspect the destination before retrying'; return 1
            fi
        fi
        GITHUB_EXPORT_PENDING=""
    done
    _github_say "Updated $destination"
}


_github_export_cleanup() {
    local name="${GITHUB_EXPORT_PENDING:-}"
    if [ -n "$name" ] && [ -e "$GITHUB_EXPORT_WORK/previous/$name" ] && [ ! -e "$GITHUB_EXPORT_DESTINATION/$name" ]; then
        if ! mv "$GITHUB_EXPORT_WORK/previous/$name" "$GITHUB_EXPORT_DESTINATION/$name"; then
            _github_error "Restore failed; recovery files retained at $GITHUB_EXPORT_WORK"
            return 1
        fi
    fi
    rm -rf "$GITHUB_EXPORT_WORK"
}
