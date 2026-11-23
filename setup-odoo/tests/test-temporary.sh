#!/usr/bin/env bash
# Synthetic transport only; never loads a real account or contacts Odoo.
set -eu
ODOO_AUTH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ODOO_AUTH_DIR/scripts/client.sh"
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/odoo-lifecycle-test.XXXXXX")"
fixture_root="$(cd "$fixture_root" && pwd -P)"
trap 'rm -rf "$fixture_root"' EXIT
mkdir "$fixture_root/tmp"
export TMPDIR="$fixture_root/tmp"
_odoo_account_exists() { return 0; }
_odoo_base_url() { printf 'https://example.invalid'; }
_odoo_api_key() { printf 'synthetic-secret'; }
_odoo_account_value() { printf 'synthetic-db'; }
curl() {
    printf '%s\n' "$@" > "$fixture_root/args"
    cat > "$fixture_root/headers"
    [ "${mode:-success}" != failure ] || return 7
    local out=''
    while [ "$#" -gt 0 ]; do
        if [ "$1" = -o ]; then out="$2"; shift; fi
        shift
    done
    printf '{"ok":true}' > "$out"
    printf '200'
}
_odoo_http example /json/2/project/read '{"synthetic":"body"}' > "$fixture_root/result"
[ "$(cat "$fixture_root/result")" = '{"ok":true}' ]
! grep -F 'synthetic-secret' "$fixture_root/args"
! grep -F '{"synthetic"' "$fixture_root/args"
grep -F 'Authorization: bearer synthetic-secret' "$fixture_root/headers" >/dev/null
[ -z "$(compgen -G "$fixture_root/tmp/odoo-work.*" || true)" ]
mode=failure
if _odoo_http example /json/2/project/read '{}' > "$fixture_root/result" 2> "$fixture_root/error"; then echo 'FAIL: failed request reported success'; exit 1; fi
[ -z "$(compgen -G "$fixture_root/tmp/odoo-work.*" || true)" ]
! grep -F 'synthetic-secret' "$fixture_root/error"
mkdir "$fixture_root/checkout" "$fixture_root/checkout/.git"
if TMPDIR="$fixture_root/checkout" _odoo_http example /json/2/project/read '{}' > "$fixture_root/result" 2> "$fixture_root/error"; then echo 'FAIL: checkout temp accepted'; exit 1; fi
printf 'Odoo success/failure cleanup, private body/header staging and unsafe-temp checks passed\n'
