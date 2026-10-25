#!/usr/bin/env bash
##- Portable GitHub discussions operations.

_github_sync_discussions() {
    local owner="$1" repo="$2" dest="$3" nodes numbers n gh_err
    gh_err="$(mktemp)"
    nodes="$(gh api graphql -f owner="$owner" -f repo="$repo" -f query='
      query($owner:String!, $repo:String!) {
        repository(owner:$owner, name:$repo) {
          discussions(first:50, orderBy:{field:UPDATED_AT, direction:DESC}) {
            nodes {
              number title url body createdAt updatedAt isAnswered
              author { login }
              category { name }
              comments(first:50) {
                totalCount
                nodes {
                  body createdAt isAnswer
                  author { login }
                  replies(first:25) {
                    totalCount
                    nodes { body createdAt author { login } }
                  }
                }
              }
            }
          }
        }
      }' --jq ".data.repository.discussions.nodes" 2>"$gh_err")" || {
        _github_warn "Could not read discussions for $owner/$repo: $(tr '\n' ' ' < "$gh_err")"
        rm -f "$gh_err"; return 1; }
    rm -f "$gh_err"

    jq -e 'type == "array" and all(.[]; .number | type == "number" and . > 0 and floor == .)' <<< "$nodes" >/dev/null || { _github_error "Invalid discussions response"; return 1; }
    [ -n "$nodes" ] && [ "$nodes" != "null" ] && [ "$(printf '%s' "$nodes" | jq 'length')" -gt 0 ] || {
        rm -f "$dest/discussions.md"; rm -rf "$dest/discussions"
        _github_say "  discussions: 0 (skipped)" >&2; return 0; }

    printf '%s' "$nodes" \
        | jq '{items: [.[] | {number,title,url,body,createdAt,updatedAt,isAnswered,author,category,
                              commentCount: .comments.totalCount,
                              replyCount: ([.comments.nodes[]?.replies.totalCount] | add // 0)}]}' \
        | _github_render_discussions discussions --owner "$owner" --repo "$repo" > "$dest/discussions.md" || return 1

    rm -rf "$dest/discussions"
    mkdir -p "$dest/discussions" || return 1
    numbers="$(printf '%s' "$nodes" | jq -r '.[].number')"
    for n in $numbers; do
        printf '%s' "$nodes" | jq --argjson n "$n" 'map(select(.number == $n))[0]' \
            | _github_render_discussions discussion-detail --owner "$owner" --repo "$repo" \
            > "$dest/discussions/$n.md" || return 1
    done
    _github_say "  discussions: $(printf '%s' "$nodes" | jq 'length')" >&2
}

_github_render_discussions() { _github_render_file "${GITHUB_AUTH_DIR}/../use-github-discussions/scripts/render.py" "$@"; }

_github_export_discussions() (
    set -o pipefail
    local repo_arg="$1" destination="$2" repo
    _github_ready || return 1
    repo="$(_github_resolve_repo "$repo_arg")" || return 1
    _github_export_begin "$destination" || return 1
    _github_sync_discussions "${repo%/*}" "${repo#*/}" "$GITHUB_EXPORT_WORK/new" || return 1
    _github_publish_export "$destination" discussions.md discussions
)
