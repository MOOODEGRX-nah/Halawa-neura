"""The local API boundary must forward client disconnects to handlers.

Found by the RX 580 matrix (2026-11-17): with the former @app.middleware('http') wrapper,
request.is_disconnected() never became true, so an abandoned request waiting for protected
resources stayed queued until its deadline and later took the single model slot.
"""
import asyncio
import json
from src.backend.api import LocalBoundary


class Preview:
    origin = 'http://127.0.0.1:9999'


def scope(path='/chat/x', method='POST', token='t'):
    return {'type': 'http', 'method': method, 'path': path, 'raw_path': path.encode(), 'query_string': b'', 'scheme': 'http',
            'server': ('127.0.0.1', 8000), 'client': ('127.0.0.1', 5), 'root_path': '',
            'headers': [(b'host', b'127.0.0.1:8000'), (b'x-neura-token', token.encode()), (b'content-type', b'application/json')]}


def test_disconnect_reaches_handler_after_body_replay():
    seen = {}
    async def handler(scope, receive, send):
        from starlette.requests import Request
        request = Request(scope, receive)
        seen['body'] = await request.body()
        for _ in range(50):
            if await request.is_disconnected():
                seen['disconnected'] = True; break
            await asyncio.sleep(0.01)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []}); await send({'type': 'http.response.body', 'body': b''})
    import time
    messages = [{'type': 'http.request', 'body': b'{"a":1}', 'more_body': False}]; closed_at = time.monotonic() + 0.05
    async def receive():
        # Like uvicorn: before the client closes, receive() blocks; afterwards it returns at once.
        if messages: return messages.pop(0)
        if time.monotonic() < closed_at: await asyncio.sleep(3600)
        return {'type': 'http.disconnect'}
    sent = []
    async def send(m): sent.append(m)
    asyncio.run(LocalBoundary(handler, token='t', preview=Preview())(scope(), receive, send))
    assert seen == {'body': b'{"a":1}', 'disconnected': True}
    headers = dict(sent[0]['headers'])
    assert headers[b'x-content-type-options'] == b'nosniff' and headers[b'cache-control'] == b'no-store'
    assert headers[b'content-security-policy'].decode().endswith("frame-ancestors 'none'; frame-src http://127.0.0.1:9999")


def test_boundary_still_rejects_bad_token_cross_site_and_large_bodies():
    async def handler(scope, receive, send): raise AssertionError('must not reach the app')
    def run(sc, messages):
        sent = []
        async def receive(): return messages.pop(0) if messages else {'type': 'http.disconnect'}
        async def send(m): sent.append(m)
        asyncio.run(LocalBoundary(handler, token='t', preview=Preview())(sc, receive, send))
        return sent[0]['status'], json.loads(sent[1]['body'])['error']['type']
    assert run(scope(token='bad'), []) == (403, 'authentication_required')
    cross = scope(); cross['headers'] = cross['headers'] + [(b'sec-fetch-site', b'cross-site')]
    assert run(cross, []) == (403, 'origin_denied')
    foreign = scope(); foreign['headers'] = foreign['headers'] + [(b'origin', b'http://evil.example')]
    assert run(foreign, []) == (403, 'origin_denied')
    big = [{'type': 'http.request', 'body': b'x' * 13_000_001, 'more_body': True}, {'type': 'http.request', 'body': b'x' * 13_000_001, 'more_body': False}]
    assert run(scope(), big) == (413, 'request_too_large')
