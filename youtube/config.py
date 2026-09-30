"""Настройки. Всё, что можно менять без правки кода, берётся из переменных окружения
(в GitHub: Settings → Secrets and variables → Actions)."""

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    # GitHub Actions передаёт незаданные переменные пустой строкой — тогда берём значение по умолчанию.
    return os.getenv(name) or default


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"
AGENTS_DIR = ROOT / "agents"
PERSONA_DIR = ROOT / "persona"
REFERENCE_IMAGE = PERSONA_DIR / "eva.png"  # эталонное лицо Евы, появляется после кастинга
MODEL_3D = PERSONA_DIR / "eva.vrm"  # 3D-модель из VRoid Studio; если она есть — Ева говорит в 3D
CANDIDATES_DIR = PERSONA_DIR / "candidates"
HISTORY_FILE = ROOT / "history.json"
MUSIC_DIR = ROOT / "assets" / "music"

# --- Канал ---
TELEGRAM_URL = _env("TELEGRAM_URL")  # твой Telegram-канал, куда Ева зовёт зрителей

# --- Claude ---
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")

# --- Озвучка (edge-tts) ---
VOICE = _env("TTS_VOICE", "ru-RU-SvetlanaNeural")
VOICE_RATE = _env("TTS_RATE", "+5%")
SEGMENT_PAUSE = 0.25  # пауза между сценами, сек

# --- Картинки и оживление (fal.ai) ---
IMAGE_MODEL = _env("IMAGE_MODEL", "fal-ai/nano-banana-2")  # к нему же /edit для кадров с Евой
IMAGE_RESOLUTION = _env("IMAGE_RESOLUTION", "1K")  # 1K | 2K | 4K — дороже, но чётче
LIPSYNC_MODEL = _env("LIPSYNC_MODEL", "veed/fabric-1.0")  # дешевле: fal-ai/flashtalk
LIPSYNC_RESOLUTION = _env("LIPSYNC_RESOLUTION", "480p")  # для fabric: 480p | 720p
LIPSYNC_MAX_SECONDS = float(_env("LIPSYNC_MAX_SECONDS", "75"))  # потолок «говорящих» секунд на выпуск

# --- 3D-Ева (Blender) ---
RENDER_3D_FPS = 12  # как в аниме: движения «на двойках», и рендер вдвое быстрее
RENDER_3D_SIZE = (720, 1280)  # потом увеличивается до 1080×1920

# --- Видео ---
WIDTH, HEIGHT, FPS = 1080, 1920, 30
MIN_SECONDS = 200  # вертикальные ролики до 3 минут YouTube считает шортсами
FONT = _env("CAPTION_FONT", "Montserrat")  # если шрифта нет, libass возьмёт системный
MUSIC_VOLUME_DB = -24


def telegram_handle() -> str:
    """https://t.me/name → @name (для надписи на видео)."""
    url = TELEGRAM_URL.rstrip("/")
    if "t.me/" in url:
        return "@" + url.split("t.me/", 1)[1].split("/")[0]
    return url


def use_3d() -> bool:
    return MODEL_3D.exists()
