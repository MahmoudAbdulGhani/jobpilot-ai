import json, urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/e2e/bootstrap",
    data=json.dumps(
        {"email": "probe-resume-e2e@jobpilot-test.com", "password": "Probe-Pass-2026!"}
    ).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=8) as response:
        print("BOOTSTRAP", response.status, response.read().decode()[:160])
except urllib.error.HTTPError as error:
    print("BOOTSTRAP_ERR", error.code, error.read().decode()[:160])
