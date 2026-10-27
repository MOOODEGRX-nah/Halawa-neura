import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
from src.channels.telegram_gateway import TelegramGateway


def update(user_id=999):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),effective_chat=SimpleNamespace(id=123),
                           message=SimpleNamespace(text='Hello',reply_text=AsyncMock()))


def test_unauthorized_user_makes_no_http_request():
    client=SimpleNamespace(post=AsyncMock())
    gateway=TelegramGateway('fake',999,api_token='token',client=client)
    asyncio.run(gateway.handle_message(update(111),None))
    client.post.assert_not_awaited()
    assert not hasattr(gateway,'neura')


def test_authorized_user_uses_api_and_history():
    response=httpx.Response(200,json={'choices':[{'message':{'content':'Hello Sami'}}]})
    client=SimpleNamespace(post=AsyncMock(return_value=response))
    gateway=TelegramGateway('fake',999,api_token='token',client=client)
    message=update()
    asyncio.run(gateway.handle_message(message,None))
    assert client.post.call_args.kwargs['headers']['X-Neura-Token']=='token'
    assert len(gateway.histories[123])==2
    message.message.reply_text.assert_awaited_once_with('Hello Sami')
