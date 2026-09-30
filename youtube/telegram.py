"""Доставка в Telegram через Telethon: бот может отправлять файлы до 2 ГБ (обычный Bot API — только 50 МБ)."""

import asyncio
import os
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_API_ID", "TELEGRAM_API_HASH")


def enabled() -> bool:
    return all(os.getenv(k) for k in KEYS)


class Message:
    """Что отправить: текст, файл (без сжатия) или альбом картинок."""

    def __init__(self, text: str = "", file: Path | None = None, album: list[Path] | None = None):
        self.text, self.file, self.album = text, file, album


def _chat_id() -> int | str:
    raw = os.environ["TELEGRAM_CHAT_ID"].strip()
    return int(raw) if raw.lstrip("-").isdigit() else raw


async def _send(messages: list[Message]) -> None:
    client = TelegramClient(StringSession(), int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    await client.start(bot_token=os.environ["TELEGRAM_BOT_TOKEN"])
    try:
        chat = await client.get_input_entity(_chat_id())
        for m in messages:
            if m.album:
                await client.send_file(chat, m.album, caption=m.text or None, parse_mode=None)
            elif m.file:
                await client.send_file(chat, m.file, caption=m.text[:1000] or None,
                                       force_document=True, parse_mode=None)
            else:
                for i in range(0, len(m.text), 4000):
                    await client.send_message(chat, m.text[i:i + 4000], parse_mode=None, link_preview=False)
    finally:
        await client.disconnect()


def send(messages: list[Message]) -> None:
    asyncio.run(_send(messages))
