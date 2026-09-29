"""Настройки автопилота. Всё, что можно менять без правки кода, берётся из переменных окружения
(в GitHub: Settings → Secrets and variables → Actions)."""

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    # GitHub Actions передаёт незаданные переменные пустой строкой — тогда берём значение по умолчанию.
    return os.getenv(name) or default


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"
HISTORY_FILE = ROOT / "history.json"
MUSIC_DIR = ROOT / "assets" / "music"

# --- Канал ---
CHANNEL_NAME = _env("CHANNEL_NAME", "Нейросети за минуту")
TELEGRAM_URL = _env("TELEGRAM_URL", "")  # например https://t.me/my_ai_channel

# --- Claude ---
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")

# --- Озвучка (edge-tts) ---
VOICE = _env("TTS_VOICE", "ru-RU-DmitryNeural")  # или ru-RU-SvetlanaNeural
VOICE_RATE = _env("TTS_RATE", "+12%")
SEGMENT_PAUSE = 0.18  # пауза между фразами, сек

# --- Видео ---
WIDTH, HEIGHT, FPS = 1080, 1920, 30
FONT = _env("CAPTION_FONT", "Montserrat")  # если шрифта нет, libass возьмёт системный
MUSIC_VOLUME_DB = -22

# --- YouTube ---
PRIVACY_STATUS = _env("YOUTUBE_PRIVACY", "public")  # public | unlisted | private
CATEGORY_ID = "28"  # Science & Technology


def telegram_handle() -> str:
    """https://t.me/name → @name (для надписи на видео)."""
    url = TELEGRAM_URL.rstrip("/")
    if "t.me/" in url:
        return "@" + url.split("t.me/", 1)[1].split("/")[0]
    return url
