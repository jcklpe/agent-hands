#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WARN_OUT="$WORK/warnings"
export TZ=Etc/UTC
fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

##- Rung 3: the machine's zone must be a real IANA identifier, not an abbreviation.
# `date +%Z` would give CDT here, which Google rejects. Guard against a regression to it.
system_tz="$(_calendar_system_tz || true)"
[ -n "$system_tz" ] || fail "_calendar_system_tz returned nothing; no /etc/timezone, no /etc/localtime symlink, no \$TZ"
case "$system_tz" in
    [A-Z][A-Z]|[A-Z][A-Z][A-Z]|[A-Z][A-Z][A-Z][A-Z]|[A-Z][A-Z][A-Z][A-Z][A-Z])
        fail "_calendar_system_tz returned '${system_tz}', which looks like a zone abbreviation rather than an IANA name" ;;
esac

##- Rung 2: a successful metadata read wins, and is silent.
_calendar_get() { printf '{"timeZone": "Europe/Berlin"}'; }
got="$(_calendar_default_tz primary 2>"$WARN_OUT")"
[ "$got" = "Europe/Berlin" ] || fail "expected Europe/Berlin from the calendar lookup, got '${got}'"
[ ! -s "$WARN_OUT" ] || fail "the successful lookup path must not warn, but wrote: $(cat "$WARN_OUT")"

##- The calendar's zone must win over the machine's: a calendar pinned to another zone is
# legitimate (travel, shared calendars). Guard against the stub accidentally matching.
[ "$got" != "$system_tz" ] || fail "test is degenerate: pick a stub zone that differs from the machine zone"

##- A failed lookup must FAIL, not guess. Guessing writes a real event at the wrong hour.
_calendar_get() { return 1; }
if got="$(_calendar_default_tz primary 2>"$WARN_OUT")"; then
    fail "a failed metadata read must return nonzero, but it succeeded with '${got}'"
fi
[ -z "$got" ] || fail "a failed resolution must print no zone to stdout, got '${got}'"
grep -F -- "Refusing to guess" "$WARN_OUT" >/dev/null || fail "the failure must say it is refusing to guess"

##- The error must hand over the workaround, so a stop never blocks writing outright.
grep -F -- "--tz" "$WARN_OUT" >/dev/null || fail "the failure must tell the operator to pass --tz"
grep -F -- "$system_tz" "$WARN_OUT" >/dev/null || fail "the failure should suggest this machine's zone '${system_tz}' as the concrete value"

##- An empty timeZone field is a failed read, not a valid zone.
_calendar_get() { printf '{}'; }
if _calendar_default_tz primary >/dev/null 2>"$WARN_OUT"; then
    fail "an empty timeZone field must be treated as a failed read"
fi

##- With no machine zone to suggest, it still fails and still names an IANA example.
_calendar_get() { return 1; }
_calendar_system_tz() { return 1; }
if _calendar_default_tz primary >/dev/null 2>"$WARN_OUT"; then
    fail "no lookup and no machine zone must still fail"
fi
grep -F -- "America/Chicago" "$WARN_OUT" >/dev/null || fail "with no hint available, the error should still show an IANA-shaped example"
grep -F -- "CDT" "$WARN_OUT" >/dev/null || fail "the error should warn against abbreviations like CDT"

printf "Calendar timezone failure and remedy checks passed\n"
