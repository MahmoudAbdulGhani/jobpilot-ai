"""Run UI checks against the existing local Docker database, never deployment credentials.

Usage from the repository: backend/.venv/Scripts/python frontend/scripts/local-ui-checks.py [Playwright arguments]
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
container = json.loads(subprocess.check_output(['docker', 'inspect', 'jobpilot-db']))[0]
values = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
binding = container['NetworkSettings']['Ports']['5432/tcp'][0]
if binding['HostIp'] not in ('127.0.0.1', '::1'):
    raise SystemExit('Expected a loopback-only local PostgreSQL container.')
env = {**os.environ, 'ENVIRONMENT': 'local', 'POSTGRES_HOST': '127.0.0.1',
       'POSTGRES_PORT': binding['HostPort'], 'POSTGRES_USER': values['POSTGRES_USER'],
       'POSTGRES_PASSWORD': values['POSTGRES_PASSWORD'], 'POSTGRES_DB': 'jobpilot_test',
       'POSTGRES_TEST_DB': 'jobpilot_test', 'SECRET_KEY': secrets.token_urlsafe(48),
       'POSTGRES_SSLMODE': 'disable', 'JIRA_ENABLED': 'false'}
psql = ['docker', 'exec', 'jobpilot-db', 'psql', '-U', values['POSTGRES_USER'], '-d', 'postgres', '-Atc']
exists = subprocess.check_output(psql + ["SELECT 1 FROM pg_database WHERE datname = 'jobpilot_test'"]).strip()
if not exists:
    subprocess.run(['docker', 'exec', 'jobpilot-db', 'createdb', '-U', values['POSTGRES_USER'], 'jobpilot_test'], check=True)
subprocess.run([str(ROOT / 'backend/.venv/Scripts/python.exe'), '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'backend', env=env, check=True)
result = subprocess.run(['npx.cmd', 'playwright', 'test', *sys.argv[1:]], cwd=ROOT / 'frontend', env=env)
sys.exit(result.returncode)
