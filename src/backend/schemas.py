"""Strict public request contracts; images are inline data only."""
import base64
import binascii
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TextPart(Contract):
    type: Literal['text']
    text: str = Field(max_length=100_000)


class ImageURL(Contract):
    url: str = Field(max_length=12_000_000)

    @model_validator(mode='after')
    def inline_only(self):
        try:
            prefix, encoded = self.url.split(',', 1)
            if prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
                raise ValueError('Use an inline PNG, JPEG or WebP image')
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 8_000_000 or not raw:
                raise ValueError('Image must be between 1 byte and 8 MB')
            matches = {'data:image/png;base64': raw.startswith(b'\x89PNG\r\n\x1a\n'),
                       'data:image/jpeg;base64': raw.startswith(b'\xff\xd8\xff'),
                       'data:image/webp;base64': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'}
            if not matches[prefix]:
                raise ValueError('Image bytes do not match MIME type')
        except (binascii.Error, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class ImagePart(Contract):
    type: Literal['image_url']
    image_url: ImageURL


class Message(Contract):
    role: Literal['system', 'user', 'assistant']
    content: str | list[TextPart | ImagePart]

    @model_validator(mode='after')
    def bounded(self):
        if isinstance(self.content, str):
            if len(self.content) > 100_000:
                raise ValueError('Message too large')
        elif not self.content or len(self.content) > 12:
            raise ValueError('Use between 1 and 12 content parts')
        elif self.role != 'user' and any(isinstance(p, ImagePart) for p in self.content):
            raise ValueError('Images are allowed only in user messages')
        return self


class Selection(Contract):
    tier: Literal['fast', 'daily', 'expert', 'vision', 'coder'] | None = None
    deep: bool = False


class ChatRequest(Contract):
    messages: list[Message] = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=120)
    tier: Literal['fast', 'daily', 'expert', 'vision', 'coder'] | None = None
    neura: Selection | None = None
    stream: bool = False
    max_tokens: int = Field(default=800, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)

    @model_validator(mode='after')
    def valid_conversation(self):
        if not any(m.role == 'user' for m in self.messages):
            raise ValueError('At least one user message is required')
        if self.messages[-1].role != 'user':
            raise ValueError('Conversation must end with a user message')
        total = sum(len(str(m.content)) for m in self.messages)
        if total > 24_000_000:
            raise ValueError('Conversation too large')
        last = self.messages[-1].content
        if isinstance(last, str) and not last.strip():
            raise ValueError('Empty user message')
        if isinstance(last, list) and not any(isinstance(p, ImagePart) or (isinstance(p, TextPart) and p.text.strip()) for p in last):
            raise ValueError('Empty user content parts')
        if self.tier and self.neura and self.neura.tier and self.tier != self.neura.tier:
            raise ValueError('Conflicting tier fields')
        return self

    def selected_tier(self):
        if self.neura and self.neura.deep:
            if self.tier not in (None, 'expert') or self.neura.tier not in (None, 'expert'):
                raise ValueError('Deep mode cannot be combined with a different tier')
            return 'expert'
        return self.tier or (self.neura.tier if self.neura else None)


class RouteRequest(Selection):
    text: str = Field(min_length=1, max_length=100_000)
    has_image: bool = False
    model: str | None = Field(default=None, max_length=120)


class VaultSave(Contract):
    session: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    messages: list[Message] = Field(max_length=128)


class ToolRequest(Contract):
    tool: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)


class PendingID(Contract):
    id: str = Field(max_length=100)


class TTSRequest(Contract):
    text: str = Field(min_length=1, max_length=10_000)
    lang: Literal['ar', 'en'] = 'ar'
