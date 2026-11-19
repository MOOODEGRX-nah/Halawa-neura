"""N079: one user-configured MCP server through Neura's permission, timeout and validation layer."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.mcp_client import McpError, McpRegistry
from tests.regression.test_chat_dispatch import application

SERVER = [sys.executable, '-I', str(Path(__file__).resolve().parents[1] / 'fixtures' / 'fake_mcp_server.py')]
H = {'X-Neura-Token': 'test-token'}


@pytest.fixture
def registry(tmp_path):
    registry = McpRegistry(tmp_path)
    registry.add('fake', SERVER, timeout_s=3)
    yield registry
    registry.close()


def test_tools_start_disabled_and_unapproved_calls_never_reach_the_server(registry, tmp_path):
    assert (tmp_path / 'mcp.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(McpError, match='غير مفعلة'):
        registry.call('fake', 'echo', {'text': 'hi'})
    assert not registry.servers['fake'].running if 'fake' in registry.servers else True
    server = registry.connect('fake')
    assert [t['name'] for t in server['tools']] == ['echo', 'add', 'slow', 'crash']
    assert not any(t['enabled'] for t in server['tools'])


def test_enabled_tool_call_validates_arguments_and_bounds_results(registry):
    registry.set_enabled('fake', 'echo', True)
    registry.set_enabled('fake', 'add', True)
    result = registry.call('fake', 'echo', {'text': 'مرحبا'})
    assert result['text'].startswith('مرحبا') and 'غير نصي' in result['text'] and not result['is_error']
    assert registry.call('fake', 'add', {'a': 2, 'b': 3})['text'].startswith('5')
    for bad in [{}, {'text': 5}, {'text': 'x', 'extra': 1}]:
        with pytest.raises(McpError):
            registry.call('fake', 'echo', bad)
    with pytest.raises(McpError):
        registry.call('fake', 'add', {'a': True, 'b': 1})
    registry.set_enabled('fake', 'echo', False)
    with pytest.raises(McpError, match='غير مفعلة'):
        registry.call('fake', 'echo', {'text': 'x'})


def test_timeout_and_crash_fail_safely_and_recover_on_next_call(registry):
    for tool in ('slow', 'crash', 'echo'):
        registry.set_enabled('fake', tool, True)
    with pytest.raises(McpError, match='مهلة'):
        registry.call('fake', 'slow', {})
    assert not registry.servers['fake'].running
    with pytest.raises(McpError, match='أُغلق'):
        registry.call('fake', 'crash', {})
    assert registry.call('fake', 'echo', {'text': 'back'})['text'].startswith('back')


def test_bad_configuration_is_rejected(tmp_path):
    registry = McpRegistry(tmp_path)
    for name, command in [('Bad Name', ['x']), ('ok', []), ('ok', 'npx server')]:
        with pytest.raises(McpError):
            registry.add(name, command)
    registry.add('missing', ['definitely-not-a-real-command-xyz'])
    with pytest.raises(McpError, match='غير موجود'):
        registry.connect('missing')


def test_api_requires_token_and_round_trips(system):
    app, desktop, dispatch = application(system)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/mcp').status_code == 403
        assert client.post('/mcp/servers', json={'name': 'fake', 'command': SERVER, 'timeout_s': 5}, headers=H).status_code == 200
        assert client.post('/mcp/servers/fake/call', json={'tool': 'echo', 'arguments': {'text': 'x'}}, headers=H).status_code == 400
        connected = client.post('/mcp/servers/fake/connect', headers=H).json()
        assert len(connected['tools']) == 4
        client.post('/mcp/servers/fake/tools/echo', json={'enabled': True}, headers=H)
        called = client.post('/mcp/servers/fake/call', json={'tool': 'echo', 'arguments': {'text': 'yo'}}, headers=H).json()
        assert called['text'].startswith('yo')
        assert client.delete('/mcp/servers/fake', headers=H).status_code == 200
        assert client.get('/mcp', headers=H).json()['servers'] == []
    app.state.project_store.close()
