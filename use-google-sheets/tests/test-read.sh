#!/usr/bin/env bash
set -eu
GOOGLE_SHEETS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$GOOGLE_SHEETS_DIR/../setup-google-services/scripts/client.sh"
source "$GOOGLE_SHEETS_DIR/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export TMPDIR="$WORK/temp" GOOGLE_CONFIG_DIR="$WORK" GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}"
jq '.accounts[0].docs.enabled=false | .accounts[0].sheets.enabled=true' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/google-accounts.json"
[ "$(_google_account_scopes example)" = 'https://www.googleapis.com/auth/spreadsheets.readonly' ]
_google_get_url() {
    printf '%s\n' "$2" >> "$WORK/requests"
    case "$2" in
        */values/*)
            [ "${FAIL_VALUES:-0}" = 0 ] || return 1
            cat "$GOOGLE_SHEETS_DIR/tests/fixtures/sheet-values.json" ;;
        *) cat "$GOOGLE_SHEETS_DIR/tests/fixtures/sheet-meta.json" ;;
    esac
}
_google_sheets_read example https://docs.google.com/spreadsheets/d/synthetic-sheet/edit > "$WORK/result"
grep -F '# Google Sheet - Test Sheet' "$WORK/result" >/dev/null
grep -F 'Account alias: `example`' "$WORK/result" >/dev/null
grep -F '| Name | Role | Link |' "$WORK/result" >/dev/null
grep -F '| Taylor | Designer | notes \| context |' "$WORK/result" >/dev/null
"$GOOGLE_PYTHON" - "$WORK/requests" <<'PY'
from pathlib import Path
import sys
from urllib.parse import unquote
request = Path(sys.argv[1]).read_text().splitlines()[-1]
assert unquote(request).endswith("/values/'People'!A1:Z200"), request
PY
_google_sheets_read example synthetic-sheet --range "'Apostrophe''s Tab'!B2:D4" > "$WORK/result"
"$GOOGLE_PYTHON" - "$WORK/requests" <<'PY'
from pathlib import Path
import sys
from urllib.parse import unquote
request = Path(sys.argv[1]).read_text().splitlines()[-1]
assert unquote(request).endswith("/values/'Apostrophe''s Tab'!B2:D4"), request
PY
if FAIL_VALUES=1 _google_sheets_read example synthetic-sheet > "$WORK/failed"; then exit 1; fi
[ ! -s "$WORK/failed" ]
for residual in "$WORK/temp"/google-sheets.*; do [ ! -e "$residual" ] || exit 1; done
if _google_sheets_read example 'https://example.com/wrong' > /dev/null 2>&1; then exit 1; fi
printf '%s\n' 'Sheets fixtures, range routing, failed-read handling, scopes, and cleanup passed'
