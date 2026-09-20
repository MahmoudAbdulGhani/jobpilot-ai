"""Read-only production configuration diagnostic.

Reports variable name, status (missing/present/invalid), and the validation
rule that failed.  Never prints values, secrets, paths, connection strings
or certificate contents.
"""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

REPORT: list[dict] = []


def add(variable: str, status: str, rule: str):
    REPORT.append({"variable": variable, "status": status, "rule": rule})


def env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    return v


def origin_ok(value: str) -> bool:
    u = urlsplit(value)
    try:
        port = u.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False
    return (
        u.scheme == "https"
        and bool(u.hostname)
        and u.hostname not in {"localhost", "127.0.0.1"}
        and not u.username
        and not u.password
        and not u.query
        and not u.fragment
        and u.path in ("", "/")
    )


def run():
    env_val = env("ENVIRONMENT")
    if env_val is None:
        add("ENVIRONMENT", "missing", "Required; must be 'production' for production mode")
        print_report()
        return
    if env_val != "production":
        add("ENVIRONMENT", "invalid", f"Must be 'production', got '{env_val}'")
        print_report()
        return
    add("ENVIRONMENT", "present", "OK")

    # --- SECRET_KEY ---
    sk = env("SECRET_KEY")
    if sk is None:
        add("SECRET_KEY", "missing", "Required; must be >= 32 characters, no weak words")
    elif len(sk) < 32:
        add("SECRET_KEY", "invalid", "Must be >= 32 characters")
    elif len(set(sk)) < 12:
        add("SECRET_KEY", "invalid", "Must have >= 12 distinct characters")
    elif any(w in sk.lower() for w in ("change-me", "changeme", "example", "test-secret")):
        add("SECRET_KEY", "invalid", "Contains a common weak word")
    else:
        add("SECRET_KEY", "present", "OK")

    # --- AUTH_COOKIE_SECURE ---
    v = env("AUTH_COOKIE_SECURE")
    if v is None:
        add("AUTH_COOKIE_SECURE", "missing", "Must be 'true' in production")
    elif v.lower() != "true":
        add("AUTH_COOKIE_SECURE", "invalid", "Must be 'true' in production")
    else:
        add("AUTH_COOKIE_SECURE", "present", "OK")

    # --- DEBUG / test providers ---
    for name in ("JOBPILOT_DEBUG", "E2E_TEST_MODE", "JOBPILOT_AI_TEST_PROVIDER",
                 "JOBPILOT_MAILBOX_TEST_PROVIDER", "JOBPILOT_DISCOVERY_TEST_PROVIDER",
                 "JOBPILOT_VOICE_TEST_PROVIDER"):
        v = env(name)
        if v is None:
            add(name, "present", "Default false; not set — OK")
        elif v.lower() == "true":
            add(name, "invalid", "Must not be true in production")
        else:
            add(name, "present", "OK")

    # --- Transport must not be 'test' ---
    for name in ("JOBPILOT_ACCOUNT_MAIL_TRANSPORT", "JOBPILOT_DIGEST_MAIL_TRANSPORT"):
        v = env(name)
        if v is not None and v == "test":
            add(name, "invalid", "Must not be 'test' in production")
        else:
            add(name, "present" if v else "present", "Default 'disabled' is OK" if not v else "OK")

    # --- APP URL + CORS ---
    app_url = env("JOBPILOT_APP_URL")
    if app_url is None:
        add("JOBPILOT_APP_URL", "missing", "Must be a valid HTTPS origin")
    elif not origin_ok(app_url):
        add("JOBPILOT_APP_URL", "invalid", "Must be a valid HTTPS origin (no credentials, no query, no fragment)")
    else:
        add("JOBPILOT_APP_URL", "present", "OK")

    cors = env("CORS_ORIGINS")
    if cors is None:
        add("CORS_ORIGINS", "missing", "Must contain exactly one entry matching JOBPILOT_APP_URL")
    else:
        parts = [p.strip() for p in cors.split(",") if p.strip()]
        if len(parts) != 1 or (app_url and parts[0] != app_url.rstrip("/")):
            add("CORS_ORIGINS", "invalid", "Must contain exactly one entry matching JOBPILOT_APP_URL")
        else:
            add("CORS_ORIGINS", "present", "OK")

    # --- ALLOWED_HOSTS ---
    hosts = env("ALLOWED_HOSTS")
    if hosts is None:
        add("ALLOWED_HOSTS", "missing", "Must be non-empty, no localhost/testserver, must include app hostname")
    else:
        parts = [h.strip() for h in hosts.split(",") if h.strip()]
        bad = [h for h in parts if not re.fullmatch(r"[a-zA-Z0-9.-]+", h) or h in {"localhost", "127.0.0.1", "testserver"}]
        hostname = urlsplit(app_url or "").hostname if app_url else None
        if not parts:
            add("ALLOWED_HOSTS", "invalid", "Must be non-empty")
        elif bad:
            add("ALLOWED_HOSTS", "invalid", f"Invalid entries: {bad}")
        elif hostname and hostname not in parts:
            add("ALLOWED_HOSTS", "invalid", f"Must include application hostname '{hostname}'")
        else:
            add("ALLOWED_HOSTS", "present", "OK")

    # --- Database ---
    for name in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        v = env(name)
        if v is None:
            add(name, "missing", "Required")
        elif v == "" and name != "POSTGRES_DB":
            add(name, "invalid", "Must not be empty")
        else:
            add(name, "present", "OK")

    pg_host = env("POSTGRES_HOST")
    if pg_host in ("localhost", "127.0.0.1", ""):
        add("POSTGRES_HOST", "invalid", "Must not be localhost, 127.0.0.1, or empty in production")

    pg_db = env("POSTGRES_DB")
    pg_test = env("POSTGRES_TEST_DB")
    if pg_db and pg_test and pg_db == pg_test:
        add("POSTGRES_DB", "invalid", "POSTGRES_DB must differ from POSTGRES_TEST_DB")

    sslmode = env("POSTGRES_SSLMODE")
    if sslmode is None:
        add("POSTGRES_SSLMODE", "missing", "Must be 'verify-full' in production")
    elif sslmode != "verify-full":
        add("POSTGRES_SSLMODE", "invalid", "Must be 'verify-full' in production")
    else:
        add("POSTGRES_SSLMODE", "present", "OK")

    sslrootcert = env("POSTGRES_SSLROOTCERT")
    if sslrootcert is None or sslrootcert == "":
        add("POSTGRES_SSLROOTCERT", "missing", "Must be non-empty and point to an existing CA file on disk")
    elif not Path(sslrootcert).is_file():
        add("POSTGRES_SSLROOTCERT", "invalid", "Path does not point to an existing file")
    else:
        add("POSTGRES_SSLROOTCERT", "present", "OK")

    # --- Proxy IPs ---
    proxy = env("JOBPILOT_PROXY_IPS")
    if proxy:
        from ipaddress import ip_network
        try:
            for entry in proxy.split(","):
                net = ip_network(entry.strip())
                if net.prefixlen < (8 if net.version == 4 else 32):
                    raise ValueError()
        except ValueError:
            add("JOBPILOT_PROXY_IPS", "invalid", "Must contain explicit IP addresses or CIDR networks")
        else:
            add("JOBPILOT_PROXY_IPS", "present", "OK")
    else:
        add("JOBPILOT_PROXY_IPS", "present", "Empty is OK (no proxy trust)")

    # --- Storage ---
    storage = env("JOBPILOT_STORAGE")
    if storage is None:
        add("JOBPILOT_STORAGE", "missing", "Must be 'supabase' in production")
    elif storage != "supabase":
        add("JOBPILOT_STORAGE", "invalid", "Must be 'supabase' in production")
    else:
        add("JOBPILOT_STORAGE", "present", "OK")

    storage_url = env("JOBPILOT_STORAGE_URL")
    if storage_url is None:
        add("JOBPILOT_STORAGE_URL", "missing", "Must be a valid HTTPS origin")
    elif not origin_ok(storage_url):
        add("JOBPILOT_STORAGE_URL", "invalid", "Must be a valid HTTPS origin")
    else:
        add("JOBPILOT_STORAGE_URL", "present", "OK")

    storage_key = env("JOBPILOT_STORAGE_KEY")
    if storage_key is None or storage_key == "":
        add("JOBPILOT_STORAGE_KEY", "missing", "Must be non-empty (Supabase service-role key)")
    else:
        add("JOBPILOT_STORAGE_KEY", "present", "OK")

    bucket = env("JOBPILOT_STORAGE_BUCKET")
    if bucket is None or bucket == "":
        add("JOBPILOT_STORAGE_BUCKET", "missing", "Must match [a-z0-9][a-z0-9-]{0,62}")
    elif not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", bucket):
        add("JOBPILOT_STORAGE_BUCKET", "invalid", "Must match [a-z0-9][a-z0-9-]{0,62}")
    else:
        add("JOBPILOT_STORAGE_BUCKET", "present", "OK")

    # --- Digest SMTP (only if enabled) ---
    digest_transport = env("JOBPILOT_DIGEST_MAIL_TRANSPORT")
    if digest_transport == "smtp":
        if not env("JOBPILOT_DIGEST_SMTP_HOST"):
            add("JOBPILOT_DIGEST_SMTP_HOST", "missing", "Required when digest SMTP is enabled")
        if not env("JOBPILOT_DIGEST_MAIL_FROM"):
            add("JOBPILOT_DIGEST_MAIL_FROM", "missing", "Required when digest SMTP is enabled")

    print_report()


def print_report():
    print("=" * 72)
    print("Production Configuration Diagnostic")
    print("=" * 72)
    print(f"{'VARIABLE':<40} {'STATUS':<10} RULE")
    print("-" * 72)
    for item in REPORT:
        print(f"{item['variable']:<40} {item['status']:<10} {item['rule']}")
    print("-" * 72)
    failures = [r for r in REPORT if r["status"] in ("missing", "invalid")]
    print(f"Total checks: {len(REPORT)}  |  Passed: {len(REPORT)-len(failures)}  |  Failed: {len(failures)}")
    if failures:
        print("\nBLOCKING FAILURES:")
        for f in failures:
            print(f"  {f['variable']}: {f['rule']}")
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    run()
