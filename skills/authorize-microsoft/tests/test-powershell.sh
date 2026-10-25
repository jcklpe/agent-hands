#!/usr/bin/env bash
set -eu
AUTH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v pwsh >/dev/null || { printf 'SKIP: PowerShell is unavailable\n'; exit 0; }
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/modules/Microsoft.Graph.Authentication"
cat > "$WORK/modules/Microsoft.Graph.Authentication/Microsoft.Graph.Authentication.psm1" <<'PS'
function Connect-MgGraph { param($Scopes,$ContextScope,$NoWelcome,$TenantId,$UseDeviceCode) }
function Get-MgContext { [pscustomobject]@{ Account='person@example.com'; TenantId='synthetic-tenant'; ClientId='synthetic-client'; Scopes=@('User.Read') } }
function Invoke-MgGraphRequest {
    param($Method,$Uri,$OutputType,$Headers,$Body,$ContentType)
    Set-Content -LiteralPath $env:TEST_REQUEST_MARKER -Value $Uri
    '{"id":"synthetic-user"}'
}
function Set-MgRequestContext { param($MaxRetry) Set-Content -LiteralPath $env:TEST_RETRY_MARKER -Value $MaxRetry }
Export-ModuleMember -Function Connect-MgGraph,Get-MgContext,Invoke-MgGraphRequest,Set-MgRequestContext
PS
jq -n '{tenant:"organizations",scopes:["User.Read"],expected_account:"different@example.com",headers:{},method:"GET",uri:"https://graph.microsoft.com/v1.0/me",body:""}' > "$WORK/request.json"
cat > "$WORK/run.ps1" <<'PS'
param([string]$ScriptPath,[string]$RequestPath)
$ErrorActionPreference = 'Stop'
# Import the exact fixture and intercept module loading so installed SDKs cannot be used.
$fixture = Join-Path $PSScriptRoot 'modules/Microsoft.Graph.Authentication/Microsoft.Graph.Authentication.psm1'
Microsoft.PowerShell.Core\Import-Module $fixture -Force
function Import-Module { param($Name) if ($Name -ne 'Microsoft.Graph.Authentication') { throw 'Unexpected module request' } }
if ((Get-Command Connect-MgGraph).Module.Path -ne $fixture) { throw 'Synthetic Graph module is not active' }
& $ScriptPath -Mode request -RequestPath $RequestPath
exit $LASTEXITCODE
PS
export TEST_REQUEST_MARKER="$WORK/request-sent"
export TEST_RETRY_MARKER="$WORK/retry"
run_fixture() { pwsh -NoLogo -NoProfile -File "$WORK/run.ps1" -ScriptPath "$AUTH/scripts/graph.ps1" -RequestPath "$1"; }
if run_fixture "$WORK/request.json" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected identity acceptance\n' >&2; exit 1; fi
grep -F 'does not match' "$WORK/error" >/dev/null || { cat "$WORK/error" >&2; exit 1; }
[ ! -e "$TEST_REQUEST_MARKER" ]
jq '.expected_account="person@example.com"' "$WORK/request.json" > "$WORK/matched.json"
run_fixture "$WORK/matched.json" > "$WORK/out"
jq -e '.id == "synthetic-user"' "$WORK/out" >/dev/null
[ -e "$TEST_REQUEST_MARKER" ]
rm "$TEST_REQUEST_MARKER"
jq '.uri="https://attacker.invalid/me"' "$WORK/matched.json" > "$WORK/invalid.json"
if run_fixture "$WORK/invalid.json" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected endpoint acceptance\n' >&2; exit 1; fi
[ ! -e "$TEST_REQUEST_MARKER" ]
jq '.method="POST" | .uri="https://graph.microsoft.com/v1.0/$batch" | .body="{}"' "$WORK/matched.json" > "$WORK/mutation.json"
run_fixture "$WORK/mutation.json" > "$WORK/out"
[ "$(tr -d '\r\n' < "$TEST_RETRY_MARKER")" = 0 ]
printf '%s\n' 'PowerShell identity and endpoint checks passed with a synthetic module; no account access'
