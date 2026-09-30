"""Картинки и оживление лица через fal.ai (нужен ключ FAL_KEY)."""

import logging
import time
from pathlib import Path

import fal_client
import requests

import config

log = logging.getLogger(__name__)

EVA_PREFIX = ("The character from the reference image is Eva. Keep her face, hairstyle, hair colour, eyes "
              "and outfit exactly as in the reference. ")
PHOTO_STYLE = (" Cinematic photo, evening, soft neon purple and cyan accents, soft rim light, shallow depth of "
               "field, no text, no logos, no watermark.")
ANIME_STYLE = (" Anime style matching the reference: VTuber look, clean cel shading, crisp line art, vibrant "
               "colours, evening light with neon purple and cyan accents, no text, no logos, no watermark.")


def style() -> str:
    return ANIME_STYLE if config.use_3d() else PHOTO_STYLE


_uploaded: dict[Path, str] = {}


def _retry(fn, attempts: int = 3):
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # у fal бывают временные сбои очереди и сети
            if attempt == attempts:
                raise
            log.warning("fal: попытка %d не удалась (%s), повторяю", attempt, e)
            time.sleep(10 * attempt)


def _upload(path: Path) -> str:
    if path not in _uploaded:
        _uploaded[path] = _retry(lambda: fal_client.upload_file(path))
    return _uploaded[path]


def _download(url: str, path: Path) -> Path:
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    return path


def _media_urls(result: dict, key: str) -> list[str]:
    value = result.get(key)
    items = value if isinstance(value, list) else [value]
    urls = [item["url"] for item in items if isinstance(item, dict) and item.get("url")]
    if not urls:
        raise RuntimeError(f"fal вернул неожиданный ответ: {str(result)[:300]}")
    return urls


def generate_images(prompt: str, out_stem: Path, *, with_eva: bool, aspect: str = "9:16",
                    count: int = 1, reference: Path | None = None) -> list[Path]:
    """Генерирует картинки. С with_eva лицо берётся с эталона (эндпоинт /edit)."""
    args = {
        "prompt": prompt + style(),
        "aspect_ratio": aspect,
        "num_images": count,
        "resolution": config.IMAGE_RESOLUTION,
        "output_format": "png",
    }
    app = config.IMAGE_MODEL
    if with_eva:
        app += "/edit"
        args["prompt"] = EVA_PREFIX + args["prompt"]
        args["image_urls"] = [_upload(reference or config.REFERENCE_IMAGE)]
    result = _retry(lambda: fal_client.subscribe(app, arguments=args))
    return [_download(url, out_stem.with_name(f"{out_stem.name}_{i}.png"))
            for i, url in enumerate(_media_urls(result, "images"))]


def lipsync(image: Path, audio: Path, out: Path) -> Path:
    """Оживляет портрет: губы и мимика под озвучку."""
    args = {"image_url": _upload(image), "audio_url": _upload(audio)}
    if config.LIPSYNC_MODEL.startswith("veed/fabric"):
        args["resolution"] = config.LIPSYNC_RESOLUTION
    result = _retry(lambda: fal_client.subscribe(config.LIPSYNC_MODEL, arguments=args))
    return _download(_media_urls(result, "video")[0], out)
