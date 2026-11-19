"""A tiny stdio MCP server for tests: echo, add, slow, crash; logs a non-JSON line first."""
import json
import sys
import time

print('fake server starting (not json)', flush=True)
TOOLS = [
    {'name': 'echo', 'description': 'Echo text', 'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}},
    {'name': 'add', 'description': 'Add numbers', 'inputSchema': {'type': 'object', 'properties': {'a': {'type': 'number'}, 'b': {'type': 'number'}}, 'required': ['a', 'b']}},
    {'name': 'slow', 'description': 'Sleeps', 'inputSchema': {'type': 'object'}},
    {'name': 'crash', 'description': 'Exits', 'inputSchema': {'type': 'object'}},
]
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    method, ident, params = message['method'], message['id'], message.get('params') or {}
    if method == 'initialize':
        result = {'protocolVersion': params['protocolVersion'], 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fake', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        name, args = params['name'], params['arguments']
        if name == 'crash':
            sys.exit(3)
        if name == 'slow':
            time.sleep(30)
        # A server-initiated request Neura must refuse, then the answer.
        print(json.dumps({'jsonrpc': '2.0', 'id': 'srv-1', 'method': 'sampling/createMessage', 'params': {}}), flush=True)
        sys.stdin.readline()
        text = args['text'] if name == 'echo' else str(args['a'] + args['b'])
        result = {'content': [{'type': 'text', 'text': text}, {'type': 'image', 'data': 'x'}]}
    else:
        print(json.dumps({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'unknown'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': result}), flush=True)
