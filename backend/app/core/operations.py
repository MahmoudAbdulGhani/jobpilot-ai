import logging
import time
import uuid
from starlette.responses import JSONResponse

logger = logging.getLogger('jobpilot.operations')


class RequestSafety:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex  # Never trust a caller's log/correlation value.
        started, status, sent = time.monotonic(), 500, False
        async def safe_send(message):
            nonlocal status, sent
            if message['type'] == 'http.response.start':
                status, sent = message['status'], True
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-request-id', request_id.encode()), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'cache-control', b'no-store')]
            await send(message)
        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            status = 500
            if not sent:
                await JSONResponse({'detail':'Request could not be completed','request_id':request_id}, status_code=500)(scope, receive, safe_send)
        finally:
            # No path, query, headers, bodies, identities or exception strings.
            route = getattr(scope.get('route'), 'name', 'unmatched')
            logger.info('request id=%s route=%s status=%s duration_ms=%s', request_id, route, status, round((time.monotonic()-started)*1000))


def production_logging():
    logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)
    class SafeOnly(logging.Filter):
        def filter(self, record): return record.name == 'jobpilot.operations' and not record.exc_info
    for handler in logging.getLogger().handlers: handler.addFilter(SafeOnly())
    for name in ('uvicorn.access','uvicorn.error','httpx','httpcore','openai','sqlalchemy.engine'):
        item = logging.getLogger(name)
        item.handlers.clear()
        item.propagate = True
