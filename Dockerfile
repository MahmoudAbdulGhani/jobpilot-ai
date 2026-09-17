FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ENVIRONMENT=production
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/requirements-production.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-production.txt && useradd --create-home --uid 10001 jobpilot
COPY backend/app ./app
RUN pip install --no-cache-dir --no-deps .
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
USER jobpilot
EXPOSE 8000
CMD ["python", "-m", "app.production"]
