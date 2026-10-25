#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-google/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
b64() { printf '%s' "$1" | "$GOOGLE_PYTHON" -c 'import base64,sys; print(base64.urlsafe_b64encode(sys.stdin.buffer.read()).decode().rstrip("="))'; }
##- Gmail renderer
STYLE_HTML='<html><head><title>Promo 97678_TEMP</title><style>/* RESET */ body { margin: 0; }</style></head><body><p>Card offer inside.</p><script>track()</script></body></html>'
PLAIN_HTML='<html><head><style type="text/css">.mbi_box { border: solid 1px; }</style></head><body><p>Your claim was denied.</p></body></html>'
cat > "${WORK}/gmail.json" <<EOF
{"messages": [
  {"id": "m1", "threadId": "t1", "labelIds": ["INBOX"], "payload": {"mimeType": "multipart/alternative",
    "headers": [{"name": "Subject", "value": "Style promo"}, {"name": "From", "value": "promo@example.com"}, {"name": "Date", "value": "Tue, 29 Sep 2026 10:00:00 +0000"},
                {"name": "List-Unsubscribe", "value": "<https://example.com/u/1>,\n <mailto:unsub@example.com>"}, {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"}],
    "parts": [{"mimeType": "text/html", "body": {"data": "$(b64 "$STYLE_HTML")"}}]}},
  {"id": "m2", "threadId": "t2", "labelIds": ["INBOX"], "payload": {"mimeType": "text/plain",
    "headers": [{"name": "Subject", "value": "Denial notice"}, {"name": "From", "value": "notices@example.com"}, {"name": "Date", "value": "Mon, 28 Sep 2026 10:00:00 +0000"}],
    "body": {"data": "$(b64 "$PLAIN_HTML")"}}},
  {"id": "m3", "threadId": "t3", "labelIds": ["INBOX"], "payload": {"mimeType": "text/plain",
    "headers": [{"name": "Subject", "value": "Plain note"}, {"name": "From", "value": "friend@example.com"}, {"name": "Date", "value": "Sun, 27 Sep 2026 10:00:00 +0000"}],
    "body": {"data": "$(b64 'Plain text with <angle> words stays as is.')"}}}
]}
EOF
"$GOOGLE_PYTHON" "$SKILL/scripts/render.py" example person@example.com "in:inbox" 150 8000 "2026-09-30 00:00:00 UTC" "${WORK}/gmail.json" > "${WORK}/gmail.md"
grep -F "Card offer inside." "${WORK}/gmail.md" >/dev/null || fail "HTML body text renders"
grep -F -e "RESET" -e "margin: 0" -e "track()" -e "97678_TEMP" "${WORK}/gmail.md" >/dev/null && fail "style, script, and title content must not render"
grep -F "Your claim was denied." "${WORK}/gmail.md" >/dev/null || fail "HTML inside a text/plain part renders as text"
grep -F ".mbi_box" "${WORK}/gmail.md" >/dev/null && fail "CSS inside a text/plain HTML part must not render"
grep -F "Plain text with <angle> words stays as is." "${WORK}/gmail.md" >/dev/null || fail "ordinary plain text is untouched"
grep -F -- "- Link: https://mail.google.com/mail/u/?authuser=person@example.com#all/t1" "${WORK}/gmail.md" >/dev/null || fail "Gmail web link"
grep -F -- "- Unsubscribe: <https://example.com/u/1>, <mailto:unsub@example.com> (one-click supported)" "${WORK}/gmail.md" >/dev/null || fail "Gmail unsubscribe header with one-click flag"
[ "$(grep -c -- '- Unsubscribe:' "${WORK}/gmail.md")" -eq 1 ] || fail "unsubscribe line only when the header exists"

##- Gmail rate-limit backoff
_google_access_token() { printf 'token\n'; }
sleep() { printf 'slept %s\n' "$1" >> "${WORK}/sleeps.log"; }
CALLS="${WORK}/calls"
printf '0\n' > "$CALLS"
# Stub curl: fail the first two calls with a rate limit, then succeed. Writes the body to the -o file and prints the status like -w.
curl() {
    local out="" n
    while [ "$#" -gt 0 ]; do case "$1" in -o) out="$2"; shift 2 ;; *) shift ;; esac; done
    n=$(( $(cat "$CALLS") + 1 )); printf '%s\n' "$n" > "$CALLS"
    if [ "$n" -le "${RATE_LIMITED_CALLS:-2}" ]; then
        printf '%s' '{"error":{"code":403,"message":"Quota exceeded for Total Query Cost","errors":[{"reason":"rateLimitExceeded"}]}}' > "$out"; printf '403'
    else
        printf '%s' '{"messages":[{"id":"ok"}]}' > "$out"; printf '200'
    fi
}
RATE_LIMITED_CALLS=2
[ "$(_gmail_get example https://gmail.example/list 2>/dev/null | jq -r '.messages[0].id')" = "ok" ] || fail "retries through rate limits"
[ "$(grep -c slept "${WORK}/sleeps.log")" -eq 2 ] || fail "backs off once per rate-limited attempt"
grep -F "slept 4" "${WORK}/sleeps.log" >/dev/null || fail "backoff doubles"

printf '0\n' > "$CALLS"
RATE_LIMITED_CALLS=99
GOOGLE_GMAIL_MAX_RETRIES=2
if _gmail_get example https://gmail.example/list > "${WORK}/out.txt" 2> "${WORK}/err.txt"; then fail "gives up after max retries"; fi
[ -s "${WORK}/out.txt" ] && fail "nothing on stdout after a failure"
grep -F "rateLimitExceeded" "${WORK}/err.txt" >/dev/null || fail "names Google's reason"
grep -F "Quota exceeded for Total Query Cost" "${WORK}/err.txt" >/dev/null || fail "surfaces Google's message"
grep -F "NEXT:" "${WORK}/err.txt" >/dev/null || fail "names a remedy"
unset GOOGLE_GMAIL_MAX_RETRIES

printf '0\n' > "$CALLS"
curl() {
    local out=""
    while [ "$#" -gt 0 ]; do case "$1" in -o) out="$2"; shift 2 ;; *) shift ;; esac; done
    printf '%s' '{"error":{"code":403,"message":"Request had insufficient authentication scopes.","errors":[{"reason":"insufficientPermissions"}]}}' > "$out"; printf '403'
}
: > "${WORK}/sleeps.log"
if _gmail_get example https://gmail.example/list > /dev/null 2> "${WORK}/err.txt"; then fail "non-rate-limit 403 fails"; fi
[ -s "${WORK}/sleeps.log" ] && fail "non-rate-limit errors are not retried"
grep -F "authorize-google/scripts/authorize auth example" "${WORK}/err.txt" >/dev/null || fail "scope errors point at re-auth"

printf 'Gmail transport and rich-body rendering checks passed\n'
