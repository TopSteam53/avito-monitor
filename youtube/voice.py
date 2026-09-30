"""Озвучка через edge-tts (бесплатные нейроголоса Microsoft) с таймингами каждого слова."""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import edge_tts

import config

TICKS = 10_000_000  # edge-tts отдаёт время в 100-наносекундных тиках


@dataclass
class Word:
    text: str
    start: float
    end: float
    segment: int = 0


@dataclass
class Voiceover:
    path: Path
    words: list[Word]
    segment_times: list[tuple[float, float]]  # начало и конец каждой фразы
    duration: float
    parts: list[Path]  # озвучка каждой фразы отдельным файлом


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


async def _synthesize(text: str, mp3: Path) -> list[Word]:
    communicate = edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS
                words.append(Word(chunk["text"], start, start + chunk["duration"] / TICKS))
    return words


def _synthesize_with_retry(text: str, mp3: Path, attempts: int = 3) -> list[Word]:
    for attempt in range(1, attempts + 1):
        try:
            return asyncio.run(_synthesize(text, mp3))
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)


def make_voiceover(phrases: list[str], workdir: Path) -> Voiceover:
    """Каждую фразу озвучиваем отдельно — так точно знаем, где она начинается в общей дорожке."""
    parts, words, times = [], [], []
    cursor = 0.0
    for i, phrase in enumerate(phrases):
        mp3 = workdir / f"voice_{i:02d}.mp3"
        phrase_words = _synthesize_with_retry(phrase, mp3)
        length = probe_duration(mp3) + config.SEGMENT_PAUSE
        words += [Word(w.text, w.start + cursor, w.end + cursor, i) for w in phrase_words]
        times.append((cursor, cursor + length))
        parts.append((mp3, length))
        cursor += length
    return Voiceover(_concat(parts, workdir / "voice.wav"), words, times, cursor, [p for p, _ in parts])


def _concat(parts: list[tuple[Path, float]], out: Path) -> Path:
    """Склеиваем фразы, подгоняя каждую ровно под её длину (с паузой), чтобы тайминги не уплывали."""
    inputs, filters = [], []
    for i, (mp3, length) in enumerate(parts):
        inputs += ["-i", str(mp3)]
        filters.append(f"[{i}:a]aresample=44100,apad=whole_dur={length:.3f},atrim=0:{length:.3f}[a{i}]")
    chain = "".join(f"[a{i}]" for i in range(len(parts)))
    filters.append(f"{chain}concat=n={len(parts)}:v=0:a=1[out]")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-ac", "2", str(out)],
        check=True,
    )
    return out
