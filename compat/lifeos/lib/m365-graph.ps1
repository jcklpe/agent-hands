[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Mode, [Parameter(Mandatory=$true)][string]$RequestPath)
& (Join-Path $PSScriptRoot "../../../skills/authorize-microsoft/scripts/graph.ps1") -Mode $Mode -RequestPath $RequestPath
exit $LASTEXITCODE
