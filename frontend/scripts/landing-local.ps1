param([ValidateSet('build', 'start')][string]$Action = 'build')

# Process-local verification configuration; never reads or writes environment files.
$env:JOBPILOT_DEPLOYMENT = 'local'
$env:NEXT_PUBLIC_API_URL = '/api'
$env:NEXT_TELEMETRY_DISABLED = '1'
if ($Action -eq 'start') {
  rtk npm run start -- --port 3025
} else {
  rtk npm run build
}
exit $LASTEXITCODE
