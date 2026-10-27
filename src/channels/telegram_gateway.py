"""Telegram is an HTTP client of the existing API; it never loads weights."""
import asyncio
import os
from pathlib import Path
import httpx
from src.runtime import Settings


def split_telegram(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)] or ['لا يوجد رد.']


class TelegramGateway:
    def __init__(self, bot_token, allowed_user_id, *, api_url='http://127.0.0.1:8000', api_token=None, client=None):
        self.bot_token = bot_token
        self.allowed_user_id = int(allowed_user_id)
        self.api_url = api_url.rstrip('/')
        if self.api_url not in ('http://127.0.0.1:8000', 'http://localhost:8000'):
            raise ValueError('Telegram must use the local Neura API on port 8000')
        if api_token is None:
            settings = Settings()
            api_token = settings.token or (settings.data_dir / '.api-token').read_text().strip()
        self.api_token = api_token
        self.client = client
        self.histories = {}
        self.app = None

    async def start(self, update, context):
        if not update.effective_user or update.effective_user.id != self.allowed_user_id:
            return
        await update.message.reply_text('أهلاً بك. أستخدم خادم Neura المحلي. /reset لمسح سياق المحادثة.')

    async def reset(self, update, context):
        if update.effective_user and update.effective_user.id == self.allowed_user_id:
            self.histories.pop(update.effective_chat.id, None)
            await update.message.reply_text('تم مسح سياق المحادثة.')

    async def handle_message(self, update, context):
        if not update.effective_user or update.effective_user.id != self.allowed_user_id or not update.message:
            return
        text = update.message.text or ''
        if not text.strip():
            return
        chat_id = update.effective_chat.id
        history = self.histories.get(chat_id, [])[-38:]
        messages = history + [{'role': 'user', 'content': text}]
        try:
            async def complete(client):
                return await client.post(self.api_url + '/v1/chat/completions',
                    headers={'X-Neura-Token': self.api_token}, json={'messages': messages, 'stream': False})
            if self.client:
                response = await complete(self.client)
            else:
                async with httpx.AsyncClient(timeout=200, trust_env=False) as client:
                    response = await complete(client)
            if response.is_error:
                raise RuntimeError(response.json().get('error', {}).get('message', 'API unavailable'))
            answer = response.json()['choices'][0]['message']['content']
            self.histories[chat_id] = (messages + [{'role':'assistant','content':answer}])[-40:]
            for part in split_telegram(answer):
                await update.message.reply_text(part)
        except Exception as exc:
            await update.message.reply_text('تعذّرت المعالجة: ' + str(exc)[:500])

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
