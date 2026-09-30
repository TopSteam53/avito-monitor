"""Губы под речь: по словам с таймингами (из озвучки) и громкости голоса считаем форму рта на каждый кадр.

Русский читается почти как пишется, поэтому гласная буква сразу даёт форму рта:
а/я → A, о/ё → O, у/ю → U, и/ы → I, е/э → E, а м/б/п смыкают губы. Громкость голоса управляет тем,
насколько широко открыт рот, а в паузах он закрывается.
"""

import array
import random
import subprocess
from pathlib import Path

from voice import Word

SHAPES = ("A", "I", "U", "E", "O")
VOWELS = {
    **dict.fromkeys("ая", "A"), **dict.fromkeys("оё", "O"), **dict.fromkeys("ую", "U"),
    **dict.fromkeys("иы", "I"), **dict.fromkeys("еэ", "E"),
    # латиница — для названий вроде ChatGPT
    "a": "A", "o": "O", "u": "U", "i": "I", "y": "I", "e": "E",
}
CLOSED = set("мбпmbp")
SAMPLE_RATE = 16000
SILENCE = 0.12  # громкость (от пиковой), ниже которой рот закрыт
MAX_OPEN = 0.9  # 1.0 у VRoid — это рот нараспашку


def loudness(audio: Path, fps: float, frames: int) -> list[float]:
    """Громкость голоса на каждый кадр, 0..1 (1 — почти пиковая)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    samples = array.array("h", raw)
    hop = SAMPLE_RATE / fps
    env = []
    for f in range(frames):
        chunk = samples[int(f * hop):int((f + 1) * hop)]
        env.append((sum(s * s for s in chunk) / len(chunk)) ** 0.5 if chunk else 0.0)
    peak = sorted(env)[int(len(env) * 0.95)] if env else 0.0
    return [min(1.0, e / peak) if peak else 0.0 for e in env]


def _letters(words: list[Word]) -> list[tuple[float, float, str | None]]:
    """(начало, конец, форма) на каждую букву; гласные звучат дольше согласных.
    Форма: A/I/U/E/O, "X" — губы сомкнуты, None — прочая согласная."""
    out = []
    for w in words:
        letters = [c for c in w.text.lower() if c.isalpha()]
        weights = [1.0 if c in VOWELS else 0.45 for c in letters]
        t, total = w.start, sum(weights)
        for c, weight in zip(letters, weights):
            d = (w.end - w.start) * weight / total
            out.append((t, t + d, VOWELS.get(c) or ("X" if c in CLOSED else None)))
            t += d
    return out


def _target(letters, t0: float, t1: float) -> dict[str, float]:
    """Какая форма рта главная в кадре [t0, t1)."""
    overlap: dict[str | None, float] = {}
    for a, b, shape in letters:
        if b > t0 and a < t1:
            overlap[shape] = overlap.get(shape, 0.0) + min(b, t1) - max(a, t0)
    if not overlap:
        return {}
    # Сомкнутые губы (м, б, п) заметны глазу, поэтому им приоритет даже перед гласной.
    if overlap.get("X", 0.0) >= 0.35 * (t1 - t0):
        return {}
    vowels = {s: v for s, v in overlap.items() if s in SHAPES}
    if vowels and max(vowels.values()) >= 0.3 * (t1 - t0):
        return {max(vowels, key=vowels.get): 1.0}
    return {"I": 0.3}  # согласная — рот чуть приоткрыт


def mouth_track(words: list[Word], audio: Path, duration: float, fps: float = 12, seed: int = 0) -> list[dict]:
    """Кадры анимации лица: веса форм рта A/I/U/E/O и моргание (blink), всё в диапазоне 0..1.
    Время слов — от начала аудиофайла."""
    frames = max(1, round(duration * fps))
    env = loudness(audio, fps, frames)
    letters = _letters(words)
    rng = random.Random(seed)
    next_blink = rng.uniform(1.0, 3.0)
    blink_frames: dict[int, float] = {}
    while next_blink < duration:
        f = int(next_blink * fps)
        blink_frames[f], blink_frames[f + 1] = 1.0, 0.4
        next_blink += rng.uniform(2.5, 5.5)

    current = dict.fromkeys(SHAPES, 0.0)
    track = []
    for f in range(frames):
        t0, t1 = f / fps, (f + 1) / fps
        gain = 0.0 if env[f] < SILENCE else (0.45 + 0.55 * env[f]) * MAX_OPEN
        target = _target(letters, t0, t1)
        # Сглаживание: рот перетекает из формы в форму, а закрывается быстро, чтобы «м» и «п» были видны.
        keep = 0.35 if target and gain else 0.1
        for s in SHAPES:
            current[s] = keep * current[s] + (1 - keep) * target.get(s, 0.0) * gain
        track.append({**{s: round(v, 3) for s, v in current.items()}, "blink": blink_frames.get(f, 0.0)})
    return track
