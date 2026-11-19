"""N079: a deliberately configured MCP server (stdio) behind Neura's own policy layer.

* Servers exist only if the user added them in Neura's settings; nothing is installed or added
  from retrieved content, model output or a web page.
* Every tool starts disabled. A call to a tool the user has not enabled is refused before any
  message reaches the server. Arguments are checked against the tool's declared input schema.
* Each request has a timeout; a crashed or disconnected server fails the call with a clear
  reason and is restarted only on the next explicit call.
* Results are bounded text and are data for the user/model, never instructions or permissions.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

PROTOCOL = '2025-06-18'
MAX_RESULT_CHARS = 20_000
MAX_SERVERS = 8
NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')


class McpError(ValueError):
    status = 400


def _check(value, schema, path='arguments'):
    """A small, strict subset of JSON Schema: object/required/properties/types/enums/additionalProperties."""
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'integer': int, 'number': (int, float), 'null': type(None)}
    if isinstance(kind, list):
        if not any(isinstance(value, types.get(k, object)) for k in kind):
            raise McpError(path + ': النوع غير صحيح.')
    elif kind in types:
        if not isinstance(value, types[kind]) or (kind in ('integer', 'number') and isinstance(value, bool)):
            raise McpError(path + ': يجب أن يكون ' + kind + '.')
    if 'enum' in schema and value not in schema['enum']:
        raise McpError(path + ': قيمة غير مسموحة.')
    if isinstance(value, str) and len(value) > 20_000:
        raise McpError(path + ': النص طويل جدًا.')
    if isinstance(value, dict):
        properties = schema.get('properties') or {}
        for required in schema.get('required') or []:
            if required not in value:
                raise McpError(path + ': الحقل «' + required + '» مطلوب.')
        if schema.get('additionalProperties') is False:
            extra = set(value) - set(properties)
            if extra:
                raise McpError(path + ': حقول غير معروفة: ' + '، '.join(sorted(extra)))
        for name, item in value.items():
            if name in properties:
                _check(item, properties[name], path + '.' + name)
    if isinstance(value, list) and isinstance(schema.get('items'), dict):
        for index, item in enumerate(value[:1000]):
            _check(item, schema['items'], path + '[' + str(index) + ']')


class McpServer:
    def __init__(self, name, command, env=None, timeout_s=20, popen=subprocess.Popen):
        self.name, self.command, self.env, self.timeout_s, self.popen = name, list(command), dict(env or {}), float(timeout_s), popen
        self.process, self.lines, self.next_id = None, None, 0
        self.lock = threading.Lock()
        self.info, self.tools, self.error = {}, [], ''

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def _reader(self, stream, lines):
        for raw in iter(stream.readline, b''):
            lines.put(raw)
        lines.put(None)

    def _send(self, message):
        try:
            self.process.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode())
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError('انقطع الاتصال بخادم MCP «' + self.name + '».') from exc

    def _request(self, method, params=None):
        self.next_id += 1
        ident = self.next_id
        self._send({'jsonrpc': '2.0', 'id': ident, 'method': method, **({'params': params} if params is not None else {})})
        deadline = time.monotonic() + self.timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.stop()
                raise McpError('انتهت مهلة خادم MCP «' + self.name + '» (' + str(int(self.timeout_s)) + ' ث)؛ أوقفته.')
            try:
                raw = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if raw is None:
                self.stop()
                raise McpError('خادم MCP «' + self.name + '» أُغلق أثناء الطلب.')
            if len(raw) > 4_000_000:
                continue
            try:
                message = json.loads(raw)
            except ValueError:
                continue  # servers may log non-JSON lines; they are ignored, never executed
            if not isinstance(message, dict) or message.get('id') != ident:
                if isinstance(message, dict) and 'method' in message and 'id' in message:
                    # Server-initiated requests (sampling, roots, elicitation) are not granted.
                    self._send({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'not supported by Neura'}})
                continue
            if 'error' in message:
                raise McpError('خادم MCP رد بخطأ: ' + str((message['error'] or {}).get('message', ''))[:300])
            return message.get('result') or {}

    def start(self):
        if self.running:
            return
        executable = shutil.which(self.command[0]) if self.command else None
        if not executable:
            raise McpError('أمر خادم MCP «' + (self.command[0] if self.command else '') + '» غير موجود على الجهاز.')
        environment = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'XDG_RUNTIME_DIR', 'USER')}
        environment.update(self.env)
        self.process = self.popen([executable, *self.command[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=environment, cwd=str(Path.home()))
        self.lines = queue.Queue()
        threading.Thread(target=self._reader, args=(self.process.stdout, self.lines), daemon=True).start()
        try:
            self.info = self._request('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {},
                                                     'clientInfo': {'name': 'neura', 'version': '1'}})
            self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            listed = self._request('tools/list', {})
        except McpError:
            self.stop()
            raise
        tools = []
        for tool in (listed.get('tools') or [])[:200]:
            if isinstance(tool, dict) and isinstance(tool.get('name'), str) and re.match(r'^[A-Za-z0-9_.-]{1,64}$', tool['name']):
                tools.append({'name': tool['name'], 'description': str(tool.get('description') or '')[:500],
                              'input_schema': tool.get('inputSchema') if isinstance(tool.get('inputSchema'), dict) else {'type': 'object'}})
        self.tools = tools

    def stop(self):
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

    def call(self, tool, arguments):
        with self.lock:
            self.start()
            spec = next((t for t in self.tools if t['name'] == tool), None)
            if spec is None:
                raise McpError('الخادم لا يقدم أداة باسم «' + tool + '».')
            _check(arguments, {**spec['input_schema'], 'type': 'object'})
            result = self._request('tools/call', {'name': tool, 'arguments': arguments})
        parts = []
        for item in (result.get('content') or [])[:50]:
            if isinstance(item, dict) and item.get('type') == 'text':
                parts.append(str(item.get('text', '')))
            elif isinstance(item, dict):
                parts.append('[' + str(item.get('type', 'محتوى')) + ' غير نصي لم يُعرض]')
        text = '\n'.join(parts)
        truncated = len(text) > MAX_RESULT_CHARS
        return {'server': self.name, 'tool': tool, 'is_error': bool(result.get('isError')),
                'text': text[:MAX_RESULT_CHARS], 'truncated': truncated}


class McpRegistry:
    """Persistent user configuration (0600) and live servers."""

    def __init__(self, data_dir, popen=subprocess.Popen):
        self.path = Path(data_dir) / 'mcp.json'
        self.popen = popen
        self.servers = {}
        self.lock = threading.Lock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data.get('servers'), dict) else {'servers': {}}
        except (OSError, ValueError, AttributeError):
            return {'servers': {}}

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix('.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        os.replace(temporary, self.path)

    def _server(self, name):
        config = self._load()['servers'].get(name)
        if not config:
            raise KeyError(name)
        live = self.servers.get(name)
        if live is None or live.command != config['command'] or live.env != config.get('env', {}):
            if live:
                live.stop()
            live = self.servers[name] = McpServer(name, config['command'], config.get('env'), config.get('timeout_s', 20), self.popen)
        return live, config

    def listing(self):
        result = []
        for name, config in self._load()['servers'].items():
            live = self.servers.get(name)
            tools = live.tools if live else []
            enabled = set(config.get('enabled_tools', []))
            result.append({'name': name, 'command': config['command'], 'timeout_s': config.get('timeout_s', 20),
                           'running': bool(live and live.running), 'connected_once': bool(live and live.tools),
                           'tools': [{**t, 'enabled': t['name'] in enabled} for t in tools],
                           'enabled_tools': sorted(enabled)})
        return result

    def add(self, name, command, env=None, timeout_s=20):
        if not NAME.match(name or ''):
            raise McpError('اسم الخادم: حروف إنجليزية صغيرة وأرقام و-_ فقط.')
        if not isinstance(command, list) or not command or not all(isinstance(c, str) and c and len(c) < 500 for c in command):
            raise McpError('اكتب أمر تشغيل الخادم كقائمة كلمات، مثل: npx -y @modelcontextprotocol/server-filesystem ~/Documents')
        if not 2 <= float(timeout_s) <= 120:
            raise McpError('المهلة بين 2 و120 ثانية.')
        with self.lock:
            data = self._load()
            if name not in data['servers'] and len(data['servers']) >= MAX_SERVERS:
                raise McpError('الحد الأقصى ' + str(MAX_SERVERS) + ' خوادم.')
            data['servers'][name] = {'command': command, 'env': {str(k): str(v) for k, v in (env or {}).items()},
                                     'timeout_s': float(timeout_s), 'enabled_tools': []}
            self._save(data)
        return {'name': name, 'enabled_tools': []}

    def remove(self, name):
        with self.lock:
            data = self._load()
            if name not in data['servers']:
                raise KeyError(name)
            del data['servers'][name]
            self._save(data)
            live = self.servers.pop(name, None)
        if live:
            live.stop()
        return {'removed': name}

    def connect(self, name):
        live, _ = self._server(name)
        with live.lock:
            live.stop()
            live.start()
        return next(s for s in self.listing() if s['name'] == name)

    def set_enabled(self, name, tool, enabled):
        with self.lock:
            data = self._load()
            config = data['servers'].get(name)
            if not config:
                raise KeyError(name)
            tools = set(config.get('enabled_tools', []))
            (tools.add if enabled else tools.discard)(tool)
            config['enabled_tools'] = sorted(tools)
            self._save(data)
        return {'name': name, 'enabled_tools': config['enabled_tools']}

    def call(self, name, tool, arguments):
        live, config = self._server(name)
        if tool not in config.get('enabled_tools', []):
            raise McpError('الأداة «' + tool + '» غير مفعلة. فعّلها بنفسك من «الإعدادات ← MCP» إن كنت تثق بها؛ لم أرسل شيئًا للخادم.')
        if not isinstance(arguments, dict):
            raise McpError('المعاملات يجب أن تكون كائن JSON.')
        return live.call(tool, arguments)

    def close(self):
        for live in self.servers.values():
            live.stop()
