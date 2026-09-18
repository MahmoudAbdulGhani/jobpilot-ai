<#
.SYNOPSIS
    Operator-run reachability + auth smoke test for the create-only Jira scaffold.

.DESCRIPTION
    This script proves two things FROM THE OPERATOR'S NETWORK (this CI box has
    no outbound internet, so the live check cannot run here):

      1. Your box can reach the Jira Cloud API.
      2. The API token in the gitignored local .env authenticates.

    It performs exactly ONE action per run -- a GET /rest/api/3/myself that
    returns only the authenticated account -- and creates nothing. It will
    NEVER create, update, delete, or list any issue; that is the create-only
    contract of the scaffold.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_jira.ps1

.OUTPUT
    Exit 0 with "JIRA_OK account=<email> site=<site-url>" when reachable and
    authenticated. Exit 1 with a specific reason otherwise (misconfigured,
    unreachable, unauthenticated).

.NOTES
    The API token is read from .env in the backend directory; it is never
    written by this scriptable, never echoed, and never committed.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$BackendDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
$EnvFile = Join-Path $BackendDir ".env"
$SiteKey = "JIRA_SITE_URL"
$EmailKey = "JIRA_USER_EMAIL"
$TokenKey = "JIRA_API_TOKEN"

function Read-EnvValue {
    param([string]$FilePath, [string]$Key)
    if (-not (Test-Path -LiteralPath $FilePath)) { return "" }
    $line = Get-Content -LiteralPath $FilePath | Where-Object { $_ -match "^$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim()
}

$Site = Read-EnvValue $EnvFile $SiteKey
$Email = Read-EnvValue $EnvFile $EmailKey
$Token = Read-EnvValue $EnvFile $TokenKey

# Bounded "not enabled by default" gate -- matches the scaffold: even the smoke
# test refuses to run unless JIRA_ENABLED+token present, so an ordinary deploy
# never opens a connection.
if (-not $Site -or -not $Email -or -not $Token) {
    Write-Error "JIRA smoke test skipped: JIRA_SITE_URL/JIRA_USER_EMAIL/JIRA_API_TOKEN must all be set in .env (integration is disabled otherwise). Nothing was sent to the network."
    exit 1
}

if ($Site -notmatch "^https?://") {
    Write-Error "JIRA_SITE_URL must start with http:// or https:// (got: $Site)"
    exit 1
}

$Uri = "$($Site.TrimEnd('/'))/rest/api/3/myself"
$Creds = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${Email}:${Token}"))
$Headers = @{ Authorization = "Basic $Creds" }

try {
    $Response = Invoke-RestMethod -Uri $Uri -Method Get -Headers $Headers -TimeoutSec 20
    Write-Output "JIRA_OK account=$($Response.accountId) site=$Site"
    exit 0
}
catch {
    $StatusCode = ""
    if ($_.Exception.Response) { $StatusCode = [int]$_.Exception.Response.StatusCode }
    Write-Error "JIRA_CHECK_FAILED status=$StatusCode reason=$($_.Exception.Message) -- rotate the token if it was ever pasted into a chat/transcript (standalone security note). Nothing was created."
    exit 1
}
