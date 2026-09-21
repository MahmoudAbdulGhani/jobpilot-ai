#Requires -Version 5.1
<#
.SYNOPSIS
    Run setup-owner against the Supabase production database.
.DESCRIPTION
    Sets temporary process-scoped environment variables only.
    Never edits .env files. Prompts for owner email and password interactively.
    Passwords are never echoed to the screen or logged.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- Safety gate: confirm target is not local ---
$pgHost = [System.Environment]::GetEnvironmentVariable("POSTGRES_HOST")
if ($pgHost -match '^(127\.0\.0\.1|localhost)$' -or $pgHost -match ':5433') {
    throw "Refused: POSTGRES_HOST points to a local database ($pgHost). Set POSTGRES_HOST to the Supabase host first."
}

# --- Required production variables (read from current environment, never .env) ---
$required = @("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "SECRET_KEY", "JOBPILOT_APP_URL", "JOBPILOT_STORAGE_URL", "JOBPILOT_STORAGE_BUCKET", "JOBPILOT_STORAGE_KEY")
$missing = $required | Where-Object { -not [System.Environment]::GetEnvironmentVariable($_) }
if ($missing) {
    throw "Missing required environment variables: $($missing -join ', '). Set them in the process environment before running."
}

# --- Set transient process-scoped overrides (never written to disk) ---
[System.Environment]::SetEnvironmentVariable("ENVIRONMENT", "production", "Process")
[System.Environment]::SetEnvironmentVariable("AUTH_COOKIE_SECURE", "true", "Process")
[System.Environment]::SetEnvironmentVariable("POSTGRES_SSLMODE", "verify-full", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_STORAGE", "supabase", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_REGISTRATION", "invite-only", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_ACCOUNT_MAIL_TRANSPORT", "disabled", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_DEBUG", "false", "Process")
[System.Environment]::SetEnvironmentVariable("E2E_TEST_MODE", "false", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_AI_TEST_PROVIDER", "false", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_MAILBOX_TEST_PROVIDER", "false", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_DISCOVERY_TEST_PROVIDER", "false", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_VOICE_TEST_PROVIDER", "false", "Process")
[System.Environment]::SetEnvironmentVariable("JOBPILOT_DIGEST_MAIL_TRANSPORT", "disabled", "Process")

Write-Host "Target: $pgHost / $([System.Environment]::GetEnvironmentVariable('POSTGRES_DB'))" -ForegroundColor Cyan
Write-Host "Running setup-owner (owner email and password will be prompted)..." -ForegroundColor Cyan

& python -m app.cli setup-owner
