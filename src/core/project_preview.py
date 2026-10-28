"""Capability-scoped static snapshots on a separate loopback origin; no app state."""
import mimetypes
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from src.core.project_files import ProjectError, Conflict, safe_path


class PreviewServer:
    def __init__(self, store):
        self.store = store
        self.server = None
        self.thread = None
        self.entries = {}
        self.lock = threading.RLock()

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server.server_port}' if self.server else None

    def start(self):
        with self.lock:
            if self.server:
                return
            owner = self
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_): pass
                def do_GET(self): owner.serve(self)
                def do_HEAD(self): owner.serve(self, head=True)
                def do_POST(self): self.send_error(405)
            self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            self.server.daemon_threads = True
            self.thread = threading.Thread(target=self.server.serve_forever, name='neura-static-preview', daemon=True)
            self.thread.start()

    def issue(self, project_id, app_origin, expected_revision):
        project = self.store.get(project_id)
        if project['project_revision'] != expected_revision or project['source_freshness'] != 'current':
            raise Conflict('تغير المشروع؛ أعد تحميله قبل المعاينة')
        if not project['preview']['supported']:
            raise ProjectError(project['preview'].get('reason') or 'هذا النوع لا يدعم المعاينة المباشرة')
        files = self.store.committed_files(project_id)
        assets = set(project['preview']['assets'])
        self.start()
        capability = secrets.token_hex(24)
        with self.lock:
            self.entries = {k:v for k,v in self.entries.items() if v['expires'] > time.monotonic()}
            while len(self.entries) >= 32:
                self.entries.pop(next(iter(self.entries)))
            self.entries[capability] = {'project_id': project_id, 'revision': expected_revision,
                'files': {p: (files[p].encode('utf-8') if isinstance(files[p],str) else files[p]) for p in assets},
                'app_origin': app_origin, 'expires': time.monotonic() + 7200}
        prefix = self.origin + '/p/' + capability + '/'
        return {'project_id': project_id, 'revision': expected_revision, 'origin': self.origin,
                'url': prefix + project['entry_point'], 'sandbox': 'allow-scripts',
                'external_resources': project['preview'].get('external_resources', []),
                'restrictions': ['opaque_origin', 'no_network', 'no_storage', 'no_forms', 'no_native_bridge'],
                'external_browser_supported': False}

    def serve(self, handler, head=False):
        origin=self.origin
        if not origin:handler.send_error(503);return
        parsed = urlsplit(handler.path)
        match = re.fullmatch(r'/p/([a-f0-9]{48})/(.+)', parsed.path)
        if handler.headers.get('Host') != origin.removeprefix('http://') or not match:
            handler.send_error(404); return
        capability, encoded = match.groups()
        try:
            path = unquote(encoded, errors='strict')
            safe_path(path)
        except (ProjectError, UnicodeError):
            handler.send_error(404); return
        with self.lock:
            entry = self.entries.get(capability)
            if not entry or entry['expires'] <= time.monotonic() or path not in entry['files']:
                handler.send_error(404); return
            data = entry['files'][path]
        prefix = origin + '/p/' + capability + '/'
        policy = ("default-src 'none'; script-src 'unsafe-inline' " + prefix + "; style-src 'unsafe-inline' " + prefix +
                  "; img-src data: " + prefix + '; font-src ' + prefix + '; media-src ' + prefix +
                  "; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; "
                  "form-action 'none'; base-uri 'none'; sandbox allow-scripts; frame-ancestors " + entry['app_origin'])
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        handler.send_response(200)
        handler.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') or path.endswith(('.js', '.svg')) else ''))
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Content-Security-Policy', policy)
        handler.send_header('X-Content-Type-Options', 'nosniff')
        # Only public capability assets use wildcard CORS. There are no app
        # cookies/tokens/credentialed endpoints here; opaque-origin modules/fonts need it.
        handler.send_header('Access-Control-Allow-Origin','*')
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Referrer-Policy', 'no-referrer')
        handler.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), clipboard-read=(), clipboard-write=(), payment=(), usb=()')
        handler.end_headers()
        if not head:
            try: handler.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass

    def stop(self):
        with self.lock:
            server, self.server = self.server, None
            self.entries.clear()
        if server:
            server.shutdown()
            server.server_close()
            self.thread.join(timeout=2)
