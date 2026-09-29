"""Фоновое видео: стоковые ролики Pexels (бесплатно, нужен ключ) или анимированный градиент."""

import logging
import os
import random
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)

PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")
GRADIENTS = [
    ("0x0f0c29", "0x302b63", "0x24243e"),
    ("0x000428", "0x004e92", "0x001f3f"),
    ("0x1a002e", "0x6a00f4", "0x00b4d8"),
    ("0x0b0f19", "0x1b4332", "0x40916c"),
]


def _pick_file(video: dict) -> str | None:
    files = [f for f in video["video_files"] if f.get("file_type") == "video/mp4" and f.get("height")]
    # Нужно вертикальное видео не меньше 720 по ширине, но без 4K — его долго качать.
    good = [f for f in files if f["height"] > f["width"] and 720 <= f["width"] <= 1440]
    good.sort(key=lambda f: abs(f["width"] - config.WIDTH))
    return good[0]["link"] if good else None


def _search(query: str, used: set[int]) -> str | None:
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
        headers={"Authorization": PEXELS_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    videos = [v for v in resp.json().get("videos", []) if v["id"] not in used and v["duration"] >= 4]
    random.shuffle(videos)
    for video in videos:
        link = _pick_file(video)
        if link:
            used.add(video["id"])
            return link
    return None


def _download(url: str, path: Path) -> Path:
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    return path


def gradient_source(index: int) -> list[str]:
    """ffmpeg-источник с плавным градиентом — запасной фон, если стока нет."""
    c0, c1, c2 = GRADIENTS[index % len(GRADIENTS)]
    return ["-f", "lavfi", "-i",
            f"gradients=s={config.WIDTH}x{config.HEIGHT}:r={config.FPS}:c0={c0}:c1={c1}:c2={c2}"
            f":n=3:speed=0.02:seed={index}"]


def fetch_clips(queries: list[str], workdir: Path) -> list[Path | None]:
    """Для каждой фразы — путь к скачанному клипу или None (тогда будет градиент)."""
    if not PEXELS_KEY:
        log.warning("PEXELS_API_KEY не задан — фон будет градиентом")
        return [None] * len(queries)
    used: set[int] = set()
    clips: list[Path | None] = []
    for i, query in enumerate(queries):
        clip = None
        for q in (query, "artificial intelligence technology"):
            try:
                link = _search(q, used)
                if link:
                    clip = _download(link, workdir / f"clip_{i:02d}.mp4")
                    break
            except requests.RequestException as e:
                log.warning("Pexels: не удалось получить «%s»: %s", q, e)
        clips.append(clip)
    return clips
