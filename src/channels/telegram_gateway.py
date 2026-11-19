"""Telegram is an HTTP client of the running Neura engine; it never loads weights (N103).

The engine address is discovered from the protected endpoint record and verified by instance id
on every message, so restarts on a new port just work and a stale/foreign port is refused.
Only the one allowed Telegram user is served. Assistant requests that are safe remotely
(reminders, memory, weather, time, calculations, reading/research) go through
``/assistant/remote``; anything that would act on the computer is refused there. Everything
else is ordinary chat. No message is ever sent unprompted.
"""
import os

import httpx

from src.core.discovery import DiscoveryError, discover, read_token


def split_telegram(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)] or ['لا يوجد رد.']


class TelegramGateway:
    def __init__(self, bot_token, allowed_user_id, *, data_dir=None, api_url=None, api_token=None, client=None, locate=None):
        self.bot_token = bot_token
        self.allowed_user_id = int(allowed_user_id)
        if data_dir is None:
            from src.desktop.paths import data_directory
            data_dir = data_directory()
        self.data_dir = data_dir
        if api_url is not None and not api_url.startswith(('http://127.0.0.1:', 'http://localhost:')):
            raise ValueError('Telegram must use the local Neura API on 127.0.0.1')
        self._locate = locate or ((lambda: api_url.rstrip('/')) if api_url else (lambda: discover(self.data_dir)))
        self._token = api_token
        self.client = client
        self.histories = {}
        self.app = None

    @property
    def api_token(self):
        return self._token or read_token(self.data_dir)

    def allowed(self, update):
        return bool(update.effective_user and update.effective_user.id == self.allowed_user_id)

    async def start(self, update, context):
        if self.allowed(update):
            await update.message.reply_text('أهلًا بك. أنا Neura على جهازك. أستطيع التذكير والطقس والوقت والحساب والذاكرة والتلخيص والمحادثة. '
                                            'أوامر فتح البرامج وتنظيم الملفات تعمل من الجهاز فقط. /reset لمسح سياق المحادثة.')

    async def reset(self, update, context):
        if self.allowed(update):
            self.histories.pop(update.effective_chat.id, None)
            await update.message.reply_text('تم مسح سياق المحادثة.')

    async def _post(self, path, payload, timeout):
        url = self._locate() + path
        headers = {'X-Neura-Token': self.api_token}
        if self.client:
            return await self.client.post(url, headers=headers, json=payload)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            return await client.post(url, headers=headers, json=payload)

    @staticmethod
    def _error(response):
        try:
            body = response.json()
            return (body.get('error') or {}).get('message') or body.get('detail') or 'المحرك رفض الطلب.'
        except ValueError:
            return 'المحرك رفض الطلب (' + str(response.status_code) + ').'

    async def answer(self, chat_id, text):
        assistant = await self._post('/assistant/remote', {'text': text, 'channel': 'telegram'}, 60)
        if assistant.is_error:
            raise RuntimeError(self._error(assistant))
        handled = assistant.json()
        if handled.get('kind') != 'chat':
            return handled.get('message') or (handled.get('result') or {}).get('message') or 'تم.'
        history = self.histories.get(chat_id, [])[-38:]
        messages = history + [{'role': 'user', 'content': text}]
        response = await self._post('/v1/chat/completions', {'messages': messages, 'stream': False}, 300)
        if response.is_error:
            raise RuntimeError(self._error(response))
        reply = response.json()['choices'][0]['message']['content']
        self.histories[chat_id] = (messages + [{'role': 'assistant', 'content': reply}])[-40:]
        return reply

    async def handle_message(self, update, context):
        if not self.allowed(update) or not update.message:
            return
        text = (update.message.text or '').strip()
        if not text:
            return
        try:
            reply = await self.answer(update.effective_chat.id, text)
        except DiscoveryError as exc:
            reply = str(exc)
        except Exception as exc:
            reply = 'تعذّرت المعالجة: ' + str(exc)[:500]
        for part in split_telegram(reply):
            await update.message.reply_text(part)

    def run(self):
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
        self.app = Application.builder().token(self.bot_token).build()
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('reset', self.reset))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.run_polling()

    def shutdown(self):
        self.histories.clear()


if __name__ == '__main__':
    TelegramGateway(os.environ['TELEGRAM_BOT_TOKEN'], int(os.environ['TELEGRAM_ALLOWED_USER_ID'])).run()
