"""Server-only Supabase Storage REST adapter; no public or signed download URLs."""
import uuid
import httpx


class StorageUnavailable(Exception):
    def __init__(self): super().__init__("Private document storage is unavailable")


class SupabaseStore:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def request(self, method, path, **kwargs):
        s = self.settings
        try:
            with httpx.Client(base_url=s.JOBPILOT_STORAGE_URL.rstrip('/') + '/storage/v1/',
                              headers={"Authorization": "Bearer " + s.JOBPILOT_STORAGE_KEY,
                                       "apikey": s.JOBPILOT_STORAGE_KEY},
                              timeout=15, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream(method, path, **kwargs) as response:
                    limit = s.RESUME_MAX_SIZE_MB * 1024 * 1024
                    content = bytearray()
                    for part in response.iter_bytes():
                        content.extend(part)
                        if len(content) > limit: raise StorageUnavailable()
                    return httpx.Response(response.status_code, content=bytes(content))
        except Exception:
            raise StorageUnavailable() from None

    def private(self):
        # Check the configured bucket, never enumerate buckets or objects.
        response = self.request('GET', 'bucket/' + self.settings.JOBPILOT_STORAGE_BUCKET)
        try:
            metadata = response.json()
            if response.status_code != 200 or metadata.get('public') is not False:
                raise StorageUnavailable()
        except Exception:
            raise StorageUnavailable() from None

    def path(self, storage_id):
        return 'object/' + self.settings.JOBPILOT_STORAGE_BUCKET + '/resumes/' + str(uuid.UUID(str(storage_id)))

    def read(self, storage_id):
        self.private()
        response = self.request('GET', self.path(storage_id))
        if response.status_code == 404: return None
        if response.status_code != 200: raise StorageUnavailable()
        return response.content

    def write(self, storage_id, data):
        if len(data) > self.settings.RESUME_MAX_SIZE_MB * 1024 * 1024: raise StorageUnavailable()
        self.private()
        response = self.request('POST', self.path(storage_id), content=data,
                                headers={'Content-Type':'application/octet-stream','x-upsert':'false'})
        if response.status_code not in {200, 201}: raise StorageUnavailable()

    def delete(self, storage_id):
        self.private()
        response = self.request('DELETE', self.path(storage_id))
        if response.status_code not in {200, 204, 404}: raise StorageUnavailable()
