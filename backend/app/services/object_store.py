"""Server-only Supabase Storage REST adapter; no public or signed download URLs."""
import logging
import uuid

import httpx

log = logging.getLogger(__name__)
# Suppress httpx INFO logs which include full request URLs (may contain bucket names).
logging.getLogger("httpx").setLevel(logging.WARNING)


class StorageUnavailable(Exception):
    def __init__(self, message="Private document storage is unavailable", *,
                 category=None, operation=None, http_status=None):
        super().__init__(message)
        self.category = category
        self.operation = operation
        self.http_status = http_status


def _safe_bucket_path(path):
    """Strip bucket name from paths to avoid logging bucket identifiers.

    Only logs the operation prefix (e.g. 'object/…/resumes/…' → 'object/**/resumes/…'
    or 'bucket/…' → 'bucket/**').
    """
    if path.startswith('object/'):
        parts = path.split('/')
        if len(parts) >= 2:
            return '/'.join(parts[:1] + ['**'] + parts[2:])
    if path.startswith('bucket/'):
        return 'bucket/**'
    return path


def _categorize(status_code, exc=None):
    """Classify a storage response into a safe diagnostic category string."""
    if exc is not None:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.ConnectError):
            return "connection_error"
        if isinstance(exc, httpx.TooManyRedirects):
            return "redirect_error"
        return f"exception:{type(exc).__name__}"
    if status_code is None:
        return "no_response"
    if status_code in (401, 403):
        return "auth_error"
    if status_code == 404:
        return "not_found"
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"


def _classify_400(body):
    """Classify a Supabase 400 response into a safe internal category.

    Matches only known sanitized phrases. Never exposes the raw body externally.
    Returns one of: invalid_path, invalid_content_type, file_size_rejected,
    bucket_policy, malformed_request, unknown.
    """
    if not body:
        return "unknown"
    text = body.lower()
    if "asset already exists" in text:
        return "invalid_path"
    if "content-type" in text or "mime" in text:
        return "invalid_content_type"
    if "file size" in text or "payload" in text or "too large" in text:
        return "file_size_rejected"
    if "bucket" in text and ("policy" in text or "permission" in text):
        return "bucket_policy"
    if "invalid" in text or "malformed" in text:
        return "malformed_request"
    return "unknown"


class SupabaseStore:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def request(self, method, path, **kwargs):
        s = self.settings
        base_url = s.JOBPILOT_STORAGE_URL.rstrip('/') + '/storage/v1/'
        safe_path = _safe_bucket_path(path)
        try:
            with httpx.Client(base_url=base_url,
                              headers={"Authorization": "Bearer " + s.JOBPILOT_STORAGE_KEY,
                                       "apikey": s.JOBPILOT_STORAGE_KEY},
                              timeout=15, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream(method, path, **kwargs) as response:
                    limit = s.RESUME_MAX_SIZE_MB * 1024 * 1024
                    content = bytearray()
                    for part in response.iter_bytes():
                        content.extend(part)
                        if len(content) > limit:
                            raise StorageUnavailable(category="response_too_large", operation=method, http_status=response.status_code)
                    status = response.status_code
                    log.warning("storage_request method=%s path=%s status=%d category=%s",
                                method, safe_path, status, _categorize(status))
                    return httpx.Response(status, content=bytes(content))
        except StorageUnavailable:
            raise
        except Exception as exc:
            cat = _categorize(None, exc)
            log.warning("storage_request method=%s path=%s category=%s error=%s",
                        method, safe_path, cat, type(exc).__name__)
            raise StorageUnavailable(category=cat, operation=method, http_status=None) from exc

    def private(self):
        """Verify the configured bucket exists and is private.

        Returns a diagnostic string on success; raises StorageUnavailable on failure.
        """
        bucket_path = 'bucket/' + self.settings.JOBPILOT_STORAGE_BUCKET
        response = self.request('GET', bucket_path)
        if response.status_code != 200:
            cat = _categorize(response.status_code)
            log.warning("storage_bucket_check status=%d category=%s", response.status_code, cat)
            raise StorageUnavailable(category=cat, operation="bucket_check", http_status=response.status_code)
        try:
            metadata = response.json()
        except Exception:
            log.warning("storage_bucket_check status=200 category=invalid_bucket_response")
            raise StorageUnavailable(category="invalid_bucket_response", operation="bucket_check", http_status=200)
        if metadata.get('public') is not False:
            log.warning("storage_bucket_check status=200 category=bucket_not_private")
            raise StorageUnavailable(category="bucket_not_private", operation="bucket_check", http_status=200)

    def path(self, storage_id):
        return 'object/' + self.settings.JOBPILOT_STORAGE_BUCKET + '/resumes/' + str(uuid.UUID(str(storage_id)))

    def read(self, storage_id):
        self.private()
        response = self.request('GET', self.path(storage_id))
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            cat = _categorize(response.status_code)
            log.warning("storage_read status=%d category=%s", response.status_code, cat)
            raise StorageUnavailable(category=cat, operation="read", http_status=response.status_code)
        return response.content

    def write(self, storage_id, data):
        if len(data) > self.settings.RESUME_MAX_SIZE_MB * 1024 * 1024:
            log.warning("storage_write category=file_too_large size=%d limit=%d",
                        len(data), self.settings.RESUME_MAX_SIZE_MB * 1024 * 1024)
            raise StorageUnavailable(category="file_too_large", operation="write", http_status=None)
        self.private()
        response = self.request('POST', self.path(storage_id), content=data,
                                headers={'Content-Type': 'application/octet-stream', 'x-upsert': 'false'})
        if response.status_code not in {200, 201}:
            if response.status_code == 400:
                try:
                    body = response.text
                except Exception:
                    body = ""
                cat = _classify_400(body)
            else:
                cat = _categorize(response.status_code)
            log.warning("storage_write status=%d category=%s", response.status_code, cat)
            raise StorageUnavailable(category=cat, operation="write", http_status=response.status_code)

    def delete(self, storage_id):
        self.private()
        response = self.request('DELETE', self.path(storage_id))
        if response.status_code not in {200, 204, 404}:
            cat = _categorize(response.status_code)
            log.warning("storage_delete status=%d category=%s", response.status_code, cat)
            raise StorageUnavailable(category=cat, operation="delete", http_status=response.status_code)
