"""Превью 1280×720: картинка с Евой + крупный текст с обводкой на затемнённой стороне."""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config

SIZE = (1280, 720)
YELLOW, WHITE = (255, 229, 0), (255, 255, 255)


def _font_file() -> str:
    for pattern in (f"{config.FONT}:black", f"{config.FONT}:bold", "DejaVu Sans:bold"):
        path = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True).stdout
        if path:
            return path
    raise RuntimeError("Не найден шрифт для превью")


def _lines(text: str) -> list[str]:
    """По два слова в строке, чтобы текст был крупным."""
    words = text.upper().split()
    return [" ".join(words[i:i + 2]) for i in range(0, len(words), 2)] or [""]


def make_thumbnail(image: Path, text: str, side: str, out: Path) -> Path:
    img = ImageOps.fit(Image.open(image).convert("RGB"), SIZE, Image.LANCZOS)
    width, height = SIZE

    # Затемняем сторону с текстом плавным градиентом.
    mask = Image.new("L", SIZE)
    for x in range(width):
        dist = x if side == "left" else width - 1 - x
        mask.paste(max(0, int(210 * (1 - dist / (width * 0.6)))), (x, 0, x + 1, height))
    img = Image.composite(Image.new("RGB", SIZE, (0, 0, 0)), img, mask)

    box_w, box_h = int(width * 0.5), int(height * 0.8)
    lines = _lines(text)
    font_file = _font_file()
    draw = ImageDraw.Draw(img)
    size = 160
    while size > 40:
        font = ImageFont.truetype(font_file, size)
        widths = [draw.textbbox((0, 0), line, font=font, stroke_width=8)[2] for line in lines]
        if max(widths) <= box_w and len(lines) * size * 1.1 <= box_h:
            break
        size -= 6

    y = (height - len(lines) * size * 1.1) / 2
    for i, (line, line_w) in enumerate(zip(lines, widths)):
        x = 50 if side == "left" else width - 50 - line_w
        draw.text((x, y), line, font=font, fill=YELLOW if i % 2 == 0 else WHITE,
                  stroke_width=8, stroke_fill=(0, 0, 0))
        y += size * 1.1

    img.save(out, "JPEG", quality=92)
    return out
