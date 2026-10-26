#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { printf "FAIL: %s\n" "$*" >&2; exit 1; }
cat > "${WORK}/m365.json" <<'EOF'
{"value": [
  {"id": "x1", "subject": "Newsletter", "receivedDateTime": "2026-09-29T10:00:00Z", "from": {"emailAddress": {"address": "news@example.com"}},
   "body": {"contentType": "html", "content": "<html><head><style>p { color: red; }</style></head><body><p>Hello readers.</p></body></html>"},
   "webLink": "https://outlook.office365.com/owa/?ItemID=x1",
   "internetMessageHeaders": [{"name": "List-Unsubscribe", "value": "<https://example.com/m365/u>"}, {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"}]},
  {"id": "x2", "subject": "Personal", "receivedDateTime": "2026-09-28T10:00:00Z", "from": {"emailAddress": {"address": "a@example.com"}},
   "body": {"contentType": "text", "content": "Hi."}, "internetMessageHeaders": [{"name": "Received", "value": "by mx"}]}
]}
EOF
"${M365_PYTHON:-python3}" "$SKILL/scripts/render.py" mail --alias fixture --email me@example.edu --refreshed now --days 30 --max-results 150 --body-limit 8000 --input "${WORK}/m365.json" > "${WORK}/m365.md"
grep -F "Hello readers." "${WORK}/m365.md" >/dev/null || fail "M365 HTML body renders"
grep -F "color: red" "${WORK}/m365.md" >/dev/null && fail "M365 style content must not render"
grep -F -- "- Unsubscribe: <https://example.com/m365/u> (one-click supported)" "${WORK}/m365.md" >/dev/null || fail "M365 unsubscribe header"
[ "$(grep -c -- '- Unsubscribe:' "${WORK}/m365.md")" -eq 1 ] || fail "M365 unsubscribe only when present"
grep -F "internetMessageHeaders" "$SKILL/scripts/operations.sh" >/dev/null || fail "M365 mail export requests internetMessageHeaders"

