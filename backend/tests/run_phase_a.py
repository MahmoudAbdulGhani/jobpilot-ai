"""Run offline tests without loading .env; --isolated uses fresh local databases.

Reads only PostgreSQL credentials from the named local Docker container into
the child process; redacts them from child output and changes no environment file.
--alembic-check checks schema drift without creating migration files.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def run(args, env, backend, password):
    # Failed assertions can contain database URLs: redact before displaying.
    process = subprocess.Popen(args, cwd=backend, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    from urllib.parse import quote_plus
    for line in process.stdout:
        print(line.replace(password, "[REDACTED]").replace(quote_plus(password), "[REDACTED]"), end="", flush=True)
    return process.wait()

if __name__ == "__main__":
    result = subprocess.run(["docker", "inspect", "jobpilot-db", "--format", "{{json .Config.Env}}"], capture_output=True, text=True, check=True)
    values = dict(item.split("=", 1) for item in json.loads(result.stdout) if "=" in item)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("JOBPILOT_", "POSTGRES_")) and key not in {"SECRET_KEY", "ENVIRONMENT", "E2E_TEST_MODE"}}
    env.update(ENVIRONMENT="test", SECRET_KEY="phase-a-offline-test-only-key-1234567890!",
               POSTGRES_HOST="127.0.0.1", POSTGRES_PORT="5433", POSTGRES_DB="jobpilot_test",
               POSTGRES_TEST_DB="jobpilot_test", POSTGRES_USER=values["POSTGRES_USER"],
               POSTGRES_PASSWORD=values["POSTGRES_PASSWORD"], JOBPILOT_TEST_PRESERVE_DB="1")
    backend = Path(__file__).resolve().parents[1]
    args = sys.argv[1:]
    isolated = "--isolated" in args
    check = "--alembic-check" in args
    args = [arg for arg in args if arg not in {"--isolated", "--alembic-check"}]
    created = []
    try:
        if isolated:
            suffix = uuid.uuid4().hex[:12]
            for key, name in [("POSTGRES_DB", f"jobpilot_phase_a_{suffix}"),
                              ("POSTGRES_TEST_DB", f"jobpilot_phase_a_{suffix}_test")]:
                subprocess.run(["docker", "exec", "jobpilot-db", "createdb", "-U", values["POSTGRES_USER"], name], check=True)
                created.append(name)
                env[key] = name
                migrate_env = dict(env, POSTGRES_DB=name)
                if run([sys.executable, "-m", "alembic", "upgrade", "head"], migrate_env, backend, values["POSTGRES_PASSWORD"]):
                    raise RuntimeError("Isolated test schema setup failed")
        if check:
            result = run([sys.executable, "-m", "alembic", "check"], env, backend, values["POSTGRES_PASSWORD"])
        else:
            result = run([sys.executable, "-m", "pytest", *args], env, backend, values["POSTGRES_PASSWORD"])
    finally:
        # Only databases successfully created by this invocation may be removed.
        for name in reversed(created):
            assert name.startswith("jobpilot_phase_a_") and name not in {"jobpilot", "jobpilot_test"}
            subprocess.run(["docker", "exec", "jobpilot-db", "dropdb", "-U", values["POSTGRES_USER"], name], check=True)
    sys.exit(result)
