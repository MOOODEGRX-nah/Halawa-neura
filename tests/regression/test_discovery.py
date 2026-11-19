"""N103: API clients discover the running engine safely; Telegram stays a remote-safe client."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.channels.telegram_gateway import TelegramGateway
from src.core.discovery import ENDPOINT, DiscoveryError, clear_endpoint, discover, write_endpoint


def test_endpoint_is_private_and_verified_by_instance(tmp_path, monkeypatch):
    monkeypatch.delenv('NEURA_API_URL', raising=False)
    write_endpoint(tmp_path, 40123, 'abc', pid=os.getpid())
    assert (tmp_path / ENDPOINT).stat().st_mode & 0o777 == 0o600
    assert 'token' not in (tmp_path / ENDPOINT).read_text()
    assert discover(tmp_path, health=lambda url: {'instance_id': 'abc'}) == 'http://127.0.0.1:40123'
    with pytest.raises(DiscoveryError, match='برنامج آخر'):
        discover(tmp_path, health=lambda url: {'instance_id': 'other'})
    def down(url):
        raise OSError('refused')
    with pytest.raises(DiscoveryError, match='لا يستجيب'):
        discover(tmp_path, health=down)
    with pytest.raises(DiscoveryError, match='قديم'):
        discover(tmp_path, health=lambda url: {'instance_id': 'abc'}, alive=lambda pid: False)


def test_missing_corrupt_exposed_and_cleared_endpoints(tmp_path, monkeypatch):
    monkeypatch.delenv('NEURA_API_URL', raising=False)
    with pytest.raises(DiscoveryError, match='غير مشغّل'):
        discover(tmp_path)
    (tmp_path / ENDPOINT).write_text('{bad')
    (tmp_path / ENDPOINT).chmod(0o600)
    with pytest.raises(DiscoveryError, match='تالف'):
        discover(tmp_path)
    write_endpoint(tmp_path, 40123, 'abc')
    (tmp_path / ENDPOINT).chmod(0o644)
    with pytest.raises(DiscoveryError, match='مكشوف'):
        discover(tmp_path, health=lambda url: {'instance_id': 'abc'})
    (tmp_path / ENDPOINT).chmod(0o600)
    clear_endpoint(tmp_path, 'someone-else')
    assert (tmp_path / ENDPOINT).exists()
    clear_endpoint(tmp_path, 'abc')
    assert not (tmp_path / ENDPOINT).exists()


def test_override_must_be_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv('NEURA_API_URL', 'http://192.168.1.5:8000')
    with pytest.raises(DiscoveryError):
        discover(tmp_path)
    monkeypatch.setenv('NEURA_API_URL', 'http://127.0.0.1:9999/')
    assert discover(tmp_path) == 'http://127.0.0.1:9999'


def update(user_id=999, text='Hello'):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), effective_chat=SimpleNamespace(id=123),
                           message=SimpleNamespace(text=text, reply_text=AsyncMock()))


def gateway(client, **extra):
    return TelegramGateway('fake', 999, data_dir='/nonexistent', api_token='token', client=client, locate=lambda: 'http://127.0.0.1:41000', **extra)


def test_telegram_assistant_requests_skip_the_model():
    client = SimpleNamespace(post=AsyncMock(return_value=httpx.Response(200, json={'kind': 'assistant', 'message': 'الساعة 9:00'})))
    message = update(text='كم الساعة')
    asyncio.run(gateway(client).handle_message(message, None))
    assert client.post.await_count == 1 and client.post.call_args.args[0] == 'http://127.0.0.1:41000/assistant/remote'
    message.message.reply_text.assert_awaited_once_with('الساعة 9:00')


def test_telegram_discovery_failure_is_reported_without_requests():
    def locate():
        raise DiscoveryError('Neura غير مشغّل الآن؛ افتح التطبيق أولًا.')
    client = SimpleNamespace(post=AsyncMock())
    message = update()
    asyncio.run(TelegramGateway('fake', 999, data_dir='/x', api_token='t', client=client, locate=locate).handle_message(message, None))
    client.post.assert_not_awaited()
    assert 'غير مشغّل' in message.message.reply_text.call_args.args[0]


def test_telegram_refuses_non_loopback_api():
    with pytest.raises(ValueError):
        TelegramGateway('fake', 999, data_dir='/x', api_url='http://10.0.0.2:8000', api_token='t')


def test_remote_channel_allows_personal_requests_and_refuses_device_actions(tmp_path):
    from src.core.assistant import Assistant
    assistant = Assistant(tmp_path)
    assert assistant.remote('كم الساعة')['kind'] == 'assistant'
    assert assistant.remote('احسب 2+3')['message'].find('5') >= 0
    saved = assistant.remote('تذكر أن لوني المفضل أزرق')
    assert saved['result']['status'] == 'done'
    refused = assistant.remote('نظم مجلد التنزيلات')
    assert refused['result']['status'] == 'unavailable' and 'من قناة بعيدة' in refused['message']
    assert assistant.remote('اكتب لي قصيدة')['kind'] == 'chat'
    assistant.remote('تذكر أن لوني المفضل أخضر')
    asked = assistant.remote('امسح كل الذاكرة')
    assert asked['kind'] != 'clarification' and '_options' not in asked
