#!/usr/bin/env bash
# Offline current Task chat routing, recovery, editing and explicit legacy reads.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-microsoft-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
M365_PYTHON="${M365_PYTHON:-python3}"
WORK="$(mktemp -d)"
WORK="$(cd "$WORK" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
M365_PLANNER_AUDIT_LOG="$WORK/audit.jsonl"; export M365_PLANNER_AUDIT_LOG
refute() { if "$@"; then printf 'Expected failure: %s\n' "$*" >&2; exit 1; fi; }
_m365_require_enabled() { :; }
_m365_planner_require_plan_allowed() { [ "$2" = plan-1 ] && [ "$PLAN_ALLOWED" -eq 1 ]; }
_m365_planner_require_write() { [ "$WRITE_ENABLED" -eq 1 ]; }
_m365_auth_provider() { printf graph-powershell; }
_m365_powershell_auth() { printf '%s' '{"effective_scopes":["Group.Read.All"]}'; }
_m365_graph_base() { printf https://graph.microsoft.com/v1.0; }
_m365_account_value() { printf 11111111-2222-3333-4444-555555555555; }
_m365_planner_my_id() { printf user-1; }
_m365_planner_audit_path() { printf '%s' "$M365_PLANNER_AUDIT_LOG"; }
_m365_planner_audit_append() { cat >> "$M365_PLANNER_AUDIT_LOG"; }
reset_fixture() {
    rm -rf "$WORK/planner-task-chat" "$WORK/planner-comments"
    printf '%s' '{"id":"task-1","planId":"plan-1","title":"Fixture","bucketId":"park","percentComplete":0,"assignments":{"user-1":{}},"appliedCategories":{"category2":true},"conversationThreadId":"legacy-thread","@odata.etag":"etag"}' > "$WORK/task"
    printf '%s' '{"value":[]}' > "$WORK/messages"
    : > "$WORK/writes"
    WRITE_ENABLED=1 PLAN_ALLOWED=1 FAIL_WRITE=0 FAIL_READ=0 FAIL_READ_AFTER=0 STRIP_LINKS=0 WRONG_PARENT=0 GENERIC_404=0 POLLING=0 BAD_NEXT=0
}
_m365_get() {
    case "$2" in
        */planner/tasks/task-1) cat "$WORK/task" ;;
        */planner/tasks/task-1/messages*)
            [ "$FAIL_READ" -eq 0 ] || return 1
            if [ "$FAIL_READ_AFTER" -eq 1 ] && [ -s "$WORK/writes" ]; then return 1; fi
            if [ "$GENERIC_404" -eq 1 ]; then printf 'NotFound: endpoint unavailable\n' >&2; return 1; fi
            if [ "$(jq '.value|length' "$WORK/messages")" -eq 0 ]; then printf 'Graph: Task task-1 does not have an associated chat thread. Create a message on the task first to initialize the thread\n' >&2; return 1; fi
            if [ "$BAD_NEXT" -eq 1 ]; then jq '. + {"@odata.nextLink":"https://attacker.invalid/messages"}' "$WORK/messages"
            elif [ "$POLLING" -eq 1 ]; then
                case "$2" in *\?*) printf '%s' '{"value":[],"@odata.nextLink":"https://graph.microsoft.com/beta/planner/tasks/task-1/messages?$skiptoken=cursor"}' ;;
                *) jq '. + {"@odata.nextLink":"https://graph.microsoft.com/beta/planner/tasks/task-1/messages?$skiptoken=cursor"}' "$WORK/messages" ;; esac
            else cat "$WORK/messages"; fi ;;
        */planner/plans/plan-1) printf '%s' '{"container":{"type":"group","containerId":"group-1"}}' ;;
        */groups/group-1/threads/legacy-thread/posts) printf '%s' '{"value":[{"id":"old-post","body":{"contentType":"text","content":"Earlier comment"}}]}' ;;
        *) printf 'Unexpected GET %s\n' "$2" >&2; return 1 ;;
    esac
}
_m365_write() {
    printf '%s %s\n' "$1" "$3" >> "$WORK/writes"
    [ "$FAIL_WRITE" -ne 1 ] || return 1
    case "$1 $3" in
        'POST https://graph.microsoft.com/beta/planner/tasks/task-1/messages')
            count="$(jq '.value|length' "$WORK/messages")"; next_id="msg-$((count+1))"
            item="$(printf '%s' "$4" | jq --arg id "$next_id" '{id:$id,parentEntityId:"task-1",content:.content,createdBy:{user:{id:"user-1"}},mentions:[]}')" ;;
        'PATCH https://graph.microsoft.com/beta/planner/tasks/task-1/messages/msg-1')
            item="$(jq --argjson p "$4" '.value[]|select(.id=="msg-1")|.content=$p.content' "$WORK/messages")"
            jq '.value|=map(select(.id!="msg-1"))' "$WORK/messages" > "$WORK/next"; mv "$WORK/next" "$WORK/messages" ;;
        *) printf 'Forbidden unexpected write %s %s\n' "$1" "$3" >&2; return 1 ;;
    esac
    if [ "$STRIP_LINKS" -eq 1 ]; then item="$(printf '%s' "$item"|jq '.content="<p>Review Shared notes</p>"')"; fi
    if [ "$WRONG_PARENT" -eq 1 ]; then item="$(printf '%s' "$item"|jq '.parentEntityId="other-task"')"; fi
    jq --argjson p "$item" '.value += [$p]' "$WORK/messages" > "$WORK/next"; mv "$WORK/next" "$WORK/messages"
    [ "$FAIL_WRITE" -ne 2 ] || return 1
    printf '%s' "$item"
}
printf 'Review [Shared notes](https://example.test/notes?a=1&b=2)\n' > "$WORK/comment"
printf 'Review [Shared notes](https://example.test/other)\n' > "$WORK/other"
reset_fixture
_m365_planner_dispatch comments example --task task-1 --json | jq -e '.route=="task-chat" and .messages==[]' >/dev/null
_m365_planner_dispatch comments example --task task-1 --legacy --json | jq -e '.route=="legacy-group" and .posts[0].id=="old-post"' >/dev/null
out="$(_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment")"
printf '%s' "$out" | grep -q 'DRY RUN'
[ ! -s "$WORK/writes" ]
WRITE_ENABLED=0
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
WRITE_ENABLED=1 PLAN_ALLOWED=0
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
PLAN_ALLOWED=1
refute _m365_planner_dispatch comment example --task task-1 --legacy --file "$WORK/comment" --execute >/dev/null 2>&1
[ ! -s "$WORK/writes" ]
out="$(_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute)"
printf '%s' "$out" | grep -q 'Actual Task chat message confirmed'
[ "$(wc -l < "$WORK/writes"|tr -d ' ')" = 1 ]
grep -F 'https://planner.cloud.microsoft/ui/web/plan/plan-1/view/board/task/task-1?tid=11111111-2222-3333-4444-555555555555' <(_m365_planner_dispatch comments example --task task-1) >/dev/null
jq -e '.conversationThreadId=="legacy-thread" and .appliedCategories.category2 and .percentComplete==0 and .assignments["user-1"]=={}' "$WORK/task" >/dev/null
jq -e '.value[0].content|contains("<a href=\"https://example.test/notes?a=1&amp;b=2\">Shared notes</a>")' "$WORK/messages" >/dev/null
out="$(_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute)"
printf '%s' "$out" | grep -q 'No change'
[ "$(wc -l < "$WORK/writes"|tr -d ' ')" = 1 ]
# A same-label/different-destination link is a different message.
_m365_planner_dispatch comment example --task task-1 --file "$WORK/other" --execute >/dev/null
[ "$(wc -l < "$WORK/writes"|tr -d ' ')" = 2 ]
POLLING=1
_m365_planner_dispatch comments example --task task-1 --json | jq -e '.messages|length==2' >/dev/null
POLLING=0 BAD_NEXT=1
refute _m365_planner_dispatch comments example --task task-1 --json >/dev/null 2>&1
BAD_NEXT=0
# Guarded edit replaces exactly one existing own message, never creates another.
prior="$(cat "$WORK/messages"|_m365_planner_python "$SKILL/scripts/comments.py" hash msg-1)"
out="$(_m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other")"
printf '%s' "$out" | grep -q 'current fingerprint'
refute _m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 stale --execute >/dev/null 2>&1
_m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 "$prior" --execute >/dev/null
[ "$(grep -c '^POST' "$WORK/writes")" = 2 ]
[ "$(grep -c '^PATCH' "$WORK/writes")" = 1 ]
[ "$(jq '.value|length' "$WORK/messages")" = 2 ]
reset_fixture
FAIL_READ_AFTER=1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
FAIL_READ_AFTER=0
out="$(_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute)"
printf '%s' "$out" | grep -q 'No change'
[ "$(grep -c '^POST' "$WORK/writes")" = 1 ]
reset_fixture
FAIL_WRITE=2
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
FAIL_WRITE=0
out="$(_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute)"
printf '%s' "$out" | grep -q 'No change'
[ "$(grep -c '^POST' "$WORK/writes")" = 1 ]
reset_fixture
FAIL_WRITE=1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
FAIL_WRITE=0
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/other" --execute >/dev/null 2>&1
[ "$(grep -c '^POST' "$WORK/writes")" = 1 ]
reset_fixture
GENERIC_404=1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
[ ! -s "$WORK/writes" ]
reset_fixture
WRONG_PARENT=1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
reset_fixture
STRIP_LINKS=1
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
STRIP_LINKS=0
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
[ "$(grep -c '^POST' "$WORK/writes")" = 1 ]
printf '  \n' > "$WORK/blank"
refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/blank" --execute >/dev/null 2>&1
# Editing never crosses authorship/mention boundaries, and ambiguous applied edits recover in place.
reset_fixture
(
    _m365_planner_chat_journal() { return 1; }
    refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
    [ ! -s "$WORK/writes" ]
)
reset_fixture
(
    mkdir() {
        command mkdir "$@" || return
        case "$1" in *.lock) printf '%s' '{"value":[{"id":"peer","parentEntityId":"task-1","content":"Concurrent message","createdBy":{"user":{"id":"peer"}},"mentions":[]}]}' > "$WORK/messages" ;; esac
    }
    refute _m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null 2>&1
    [ ! -s "$WORK/writes" ]
)
reset_fixture
_m365_planner_dispatch comment example --task task-1 --file "$WORK/comment" --execute >/dev/null
prior="$(cat "$WORK/messages"|_m365_planner_python "$SKILL/scripts/comments.py" hash msg-1)"
jq '.value[0].createdBy.user.id="other-user"' "$WORK/messages" > "$WORK/next"; mv "$WORK/next" "$WORK/messages"
refute _m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 "$prior" --execute >/dev/null 2>&1
jq '.value[0].createdBy.user.id="user-1"|.value[0].mentions=[{mentioned:"other-user"}]' "$WORK/messages" > "$WORK/next"; mv "$WORK/next" "$WORK/messages"
refute _m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 "$prior" --execute >/dev/null 2>&1
jq '.value[0].mentions=[]' "$WORK/messages" > "$WORK/next"; mv "$WORK/next" "$WORK/messages"
FAIL_WRITE=2
refute _m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 "$prior" --execute >/dev/null 2>&1
FAIL_WRITE=0
out="$(_m365_planner_dispatch edit-comment example --task task-1 --message msg-1 --file "$WORK/other" --expected-sha256 "$prior" --execute)"
printf '%s' "$out" | grep -q 'No change'
[ "$(grep -c '^PATCH' "$WORK/writes")" = 1 ]
[ "$(jq '.value|length' "$WORK/messages")" = 1 ]
# organizations aliases use the already-authorized SDK tenant for current account-specific URLs.
(
    _m365_account_value() { printf organizations; }
    _m365_powershell_auth() { printf '%s' '{"tenant_id":"11111111-2222-3333-4444-555555555555"}'; }
    [ "$(_m365_planner_tenant example)" = 11111111-2222-3333-4444-555555555555 ]
)
printf 'Planner Task chat offline command tests passed\n'
