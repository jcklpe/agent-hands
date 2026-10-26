#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
EVENT_OUT="$WORK/event"; ALL_DAY_OUT="$WORK/allday"; CONTACT_OUT="$WORK/contact"
"$PYTHON" "$SKILL/scripts/write.py" contact \
    --display-name "Ada Lovelace" \
    --email "ada@example.com" \
    --company "Analytical Engines" \
    --notes "Research contact" > "$CONTACT_OUT"
jq -e '.displayName == "Ada Lovelace" and .emailAddresses[0].address == "ada@example.com" and .companyName == "Analytical Engines"' "$CONTACT_OUT" >/dev/null
