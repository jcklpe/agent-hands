#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
source "$SKILL/scripts/content.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_GMAIL_AUDIT_LOG="$WORK/audit.jsonl"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect_fail() { if "$@" > "$WORK/out" 2> "$WORK/err"; then fail "unexpected success: $*"; fi; }
_gmail_require_enabled() { [ "$1" = example ]; }
_google_account_email() { printf 'person@example.com'; }
printf 'hello\000\377' > "$WORK/source.bin"
printf 'Hello there,\nPlease review this draft.\n' > "$WORK/body.txt"
"$GOOGLE_PYTHON" - "$WORK" <<'PY'
import base64,json,sys
from pathlib import Path
p=Path(sys.argv[1]); data=base64.urlsafe_b64encode((p/'source.bin').read_bytes()).decode()
(p/'message.json').write_text(json.dumps({'id':'m1','threadId':'t1','payload':{'headers':[{'name':'Subject','value':'Agreement'},{'name':'Message-ID','value':'<original@example.com>'}],'parts':[{'partId':'1','filename':'../../unsafe.bin','mimeType':'application/octet-stream','body':{'size':7,'attachmentId':'external'}},{'partId':'2','filename':'inline.bin','body':{'size':7,'data':data}}]}}))
(p/'external.json').write_text(json.dumps({'size':7,'data':data}))
PY
_gmail_get() {
    printf '%s\n' "$2" >> "$WORK/reads"
    case "$2" in
        */messages/m1) cat "$WORK/message.json" ;;
        */attachments/external) cat "$WORK/external.json" ;;
        */profile) printf '{"emailAddress":"%s"}' "${PROFILE_EMAIL:-person@example.com}" ;;
        */drafts/d1)
            [ "${FAIL_READBACK:-0}" = 0 ] || return 1
            jq --arg id "${READBACK_ID:-d1}" --arg message "${READBACK_MESSAGE:-md1}" --arg thread "${READBACK_THREAD:-${CREATED_THREAD:-t1}}" --arg tamper "${TAMPER_READBACK:-}" '{id:$id,message:{id:$message,threadId:$thread,labelIds:(["DRAFT"] + (if $tamper == "sent" then ["SENT"] else [] end)),raw:(if $tamper == "body" then "U3ViamVjdDogV3JvbmdcclxuXHJcbkNoYW5nZWQ" else .message.raw end)}}' "$WORK/draft-request.json" ;;
        *) return 1 ;;
    esac
}
_gmail_send() {
    [ "$1:$3" = "POST:${_GMAIL_API}/drafts" ] || fail 'unexpected write endpoint'
    printf '%s' "$4" > "$WORK/draft-request.json"
    printf 'created\n' >> "$WORK/writes"
    jq -cn --arg thread "${CREATED_THREAD:-t1}" '{id:"d1",message:{id:"md1",threadId:$thread}}'
}
_gmail_attachments example --message m1 --json > "$WORK/list.json"
jq -e 'length == 2 and .[0].filename == "../../unsafe.bin"' "$WORK/list.json" >/dev/null || fail 'attachment listing preserves metadata'
_gmail_download_attachment example --message m1 --part 1 --output "$WORK/external.bin"
cmp "$WORK/source.bin" "$WORK/external.bin" || fail 'external binary bytes differ'
_gmail_download_attachment example --message m1 --part 2 --output "$WORK/inline.bin"
cmp "$WORK/source.bin" "$WORK/inline.bin" || fail 'embedded binary bytes differ'
[ "$(stat -f %Lp "$WORK/external.bin" 2>/dev/null || stat -c %a "$WORK/external.bin")" = 600 ] || fail 'attachment output permissions'
expect_fail _gmail_download_attachment example --message m1 --part 1 --output "$WORK/external.bin"
expect_fail _gmail_download_attachment example --message m1 --part missing --output "$WORK/missing.bin"
[ ! -e "$WORK/missing.bin" ] || fail 'missing attachment created output'
ln -s "$WORK/source.bin" "$WORK/link.bin"
expect_fail _gmail_download_attachment example --message m1 --part 1 --output "$WORK/link.bin" --overwrite
printf '{"size":7,"data":"!!!"}' > "$WORK/external.json"
expect_fail _gmail_download_attachment example --message m1 --part 1 --output "$WORK/external.bin" --overwrite
cmp "$WORK/source.bin" "$WORK/external.bin" || fail 'failed decode replaced previous output'
printf '{"size":2,"data":"aGk"}' > "$WORK/external.json"
expect_fail _gmail_download_attachment example --message m1 --part 1 --output "$WORK/wrongsize.bin"
[ ! -e "$WORK/wrongsize.bin" ] || fail 'wrong-size response created output'

_gmail_create_draft example --to recipient@example.com --body-file "$WORK/body.txt" --reply-to-message m1 --attach "$WORK/source.bin" > "$WORK/preview"
grep -F 'DRY RUN' "$WORK/preview" >/dev/null || fail 'draft preview missing'
[ ! -e "$WORK/writes" ] || fail 'preview wrote remotely'
expect_fail _gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute
grep -F -- '--allow-draft-write' "$WORK/err" >/dev/null || fail 'action-time opt-in remedy missing'
[ ! -e "$WORK/writes" ] || fail 'missing opt-in wrote remotely'
PROFILE_EMAIL=other@example.com
expect_fail _gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write
[ ! -e "$WORK/writes" ] || fail 'wrong mailbox wrote remotely'
unset PROFILE_EMAIL
expect_fail _gmail_create_draft example --to $'recipient@example.com\r\nBcc: other@example.com' --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write
[ ! -e "$WORK/writes" ] || fail 'header injection wrote remotely'
expect_fail _gmail_create_draft example --to recipient@example.com --subject Wrong --body-file "$WORK/body.txt" --reply-to-message m1 --execute --allow-draft-write
_gmail_create_draft example --to recipient@example.com --cc cc@example.com --bcc bcc@example.com --body-file "$WORK/body.txt" --reply-to-message m1 --attach "$WORK/source.bin" --execute --allow-draft-write > "$WORK/created"
grep -F 'content confirmed by readback' "$WORK/created" >/dev/null || fail 'draft readback missing'
grep -Fx 'Review: https://mail.google.com/mail/u/?authuser=person%40example.com#drafts/t1' "$WORK/created" >/dev/null || fail 'draft review link must use encoded account and returned thread ID'
grep -Fx 'Drafts folder: https://mail.google.com/mail/u/?authuser=person%40example.com#drafts' "$WORK/created" >/dev/null || fail 'draft folder fallback missing'
"$GOOGLE_PYTHON" - "$WORK/draft-request.json" <<'PY'
import base64,json,sys
from email import policy
from email.parser import BytesParser
r=json.load(open(sys.argv[1])); raw=r['message']['raw']; m=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
assert r['message']['threadId']=='t1'
assert m['In-Reply-To']=='<original@example.com>'
assert m['Subject']=='Re: Agreement'
assert len(list(m.iter_attachments()))==1
PY
jq -e '.action == "create-draft" and .verified' "$GOOGLE_GMAIL_AUDIT_LOG" >/dev/null || fail 'private draft audit missing'
FAIL_READBACK=1
expect_fail _gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write
grep -F 'Do not create it again' "$WORK/err" >/dev/null || fail 'uncertain outcome recovery missing'
[ "$(wc -l < "$WORK/writes" | tr -d ' ')" = 2 ] || fail 'draft creation was retried'
unset FAIL_READBACK

##- New drafts have no reply headers/thread request; links use the server-returned thread.
CREATED_THREAD=t-new
_gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write > "$WORK/new-draft"
jq -e '.message | has("threadId") | not' "$WORK/draft-request.json" >/dev/null || fail 'new draft inherited a reply thread'
grep -Fx 'Review: https://mail.google.com/mail/u/?authuser=person%40example.com#drafts/t-new' "$WORK/new-draft" >/dev/null || fail 'new draft link ignored returned thread ID'
unset CREATED_THREAD

##- A success response and its readback must agree on draft/message/thread identity and content.
for corruption in id message body sent; do
    case "$corruption" in id) READBACK_ID=wrong ;; message) READBACK_MESSAGE=wrong ;; *) TAMPER_READBACK="$corruption" ;; esac
    expect_fail _gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write
    grep -F 'Do not create it again' "$WORK/err" >/dev/null || fail 'corrupt readback lacked recovery guidance'
    unset READBACK_ID READBACK_MESSAGE TAMPER_READBACK
done
CREATED_THREAD=t-wrong
READBACK_THREAD=t1
expect_fail _gmail_create_draft example --to recipient@example.com --body-file "$WORK/body.txt" --reply-to-message m1 --execute --allow-draft-write
unset CREATED_THREAD READBACK_THREAD
CREATED_THREAD=t-new
READBACK_THREAD=t-wrong
expect_fail _gmail_create_draft example --to recipient@example.com --subject Review --body-file "$WORK/body.txt" --execute --allow-draft-write
unset CREATED_THREAD READBACK_THREAD

##- Real transport must refuse both Gmail send endpoints before requesting a token or calling curl.
source "$SKILL/scripts/operations.sh"
_google_access_token() { printf 'called\n' >> "$WORK/token-called"; printf 'secret'; }
curl() { printf 'called\n' >> "$WORK/curl-called"; return 1; }
expect_fail _gmail_send POST example "${_GMAIL_API}/messages/send" '{}'
expect_fail _gmail_send POST example "${_GMAIL_API}/drafts/send" '{}'
[ ! -e "$WORK/token-called" ] && [ ! -e "$WORK/curl-called" ] || fail 'send endpoint reached transport'
if bash "$SKILL/scripts/gmail" send example > "$WORK/out" 2> "$WORK/err"; then fail 'CLI exposes send'; fi
printf 'Gmail attachment and manual-draft checks passed\n'
