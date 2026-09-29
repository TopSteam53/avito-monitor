"""Сборка ролика: фон по фразам → склейка → субтитры, ник канала, озвучка и музыка."""

import random
import subprocess
from pathlib import Path

import config
import footage
from voice import Voiceover, Word

WHITE, YELLOW = "&H00FFFFFF&", "&H0000E5FF&"  # в ASS цвета записываются как BGR


def _ffmpeg(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, cwd=cwd)


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").upper()


def _chunks(words: list[Word], max_words: int = 3, max_chars: int = 16) -> list[list[Word]]:
    """Режем речь на короткие куски по 1-3 слова; кусок не переходит через границу фразы."""
    chunks: list[list[Word]] = []
    for w in words:
        if not any(c.isalnum() for c in w.text):
            continue
        cur = chunks[-1] if chunks else None
        if (cur and cur[-1].segment == w.segment and len(cur) < max_words
                and len(" ".join(x.text for x in cur + [w])) <= max_chars):
            cur.append(w)
        else:
            chunks.append([w])
    return chunks


def write_captions(vo: Voiceover, path: Path) -> Path:
    handle = config.telegram_handle()
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {config.WIDTH}",
        f"PlayResY: {config.HEIGHT}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{config.FONT},96,{WHITE},{WHITE},&H00000000&,&H99000000&,"
        "-1,0,0,0,100,100,0,0,1,7,3,2,90,90,720,1",
        f"Style: Tag,{config.FONT},54,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H99000000&,"
        "-1,0,0,0,100,100,0,0,1,4,2,8,60,60,210,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if handle:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(vo.duration)},Tag,,0,0,0,,{_clean(handle).lower()}")

    chunks = _chunks(vo.words)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else vo.duration
        # Держим кусок на экране ещё 0.35 с после последнего слова, но не дольше начала следующего.
        chunk_end = min(chunk[-1].end + 0.35, next_start)
        for wi, word in enumerate(chunk):
            start = word.start
            end = chunk[wi + 1].start if wi + 1 < len(chunk) else chunk_end
            if end <= start:
                continue
            text = " ".join(
                f"{{\\c{YELLOW}}}{_clean(w.text)}{{\\c{WHITE}}}" if j == wi else _clean(w.text)
                for j, w in enumerate(chunk)
            )
            pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{pop}{text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _segment(index: int, clip: Path | None, duration: float, out: Path) -> Path:
    fit = (f"scale={config.WIDTH}:{config.HEIGHT}:force_original_aspect_ratio=increase,"
           f"crop={config.WIDTH}:{config.HEIGHT},setsar=1,fps={config.FPS}")
    source = ["-stream_loop", "-1", "-i", str(clip)] if clip else footage.gradient_source(index)
    _ffmpeg(*source, "-t", f"{duration:.3f}",
            "-vf", f"{fit},eq=brightness=-0.06:saturation=1.1,format=yuv420p",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out))
    return out


def render(vo: Voiceover, clips: list[Path | None], workdir: Path, out: Path) -> Path:
    segments = [
        _segment(i, clip, end - start, workdir / f"seg_{i:02d}.mp4")
        for i, (clip, (start, end)) in enumerate(zip(clips, vo.segment_times))
    ]
    concat_list = workdir / "segments.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in segments))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", concat_list.name, "-c", "copy", "background.mp4", cwd=workdir)
    write_captions(vo, workdir / "captions.ass")

    inputs = ["-i", "background.mp4", "-i", str(vo.path.resolve())]
    tracks = sorted(p for ext in ("mp3", "m4a", "wav") for p in config.MUSIC_DIR.glob(f"*.{ext}"))
    if tracks:
        inputs += ["-stream_loop", "-1", "-i", str(random.choice(tracks).resolve())]
        fade = max(vo.duration - 1.5, 0)
        audio = (f"[2:a]volume={config.MUSIC_VOLUME_DB}dB,afade=t=out:st={fade:.2f}:d=1.5[m];"
                 f"[1:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
    else:
        audio = "[1:a]loudnorm=I=-14:TP=-1.5[a]"

    _ffmpeg(*inputs,
            "-filter_complex", f"[0:v]ass=captions.ass[v];{audio}",
            "-map", "[v]", "-map", "[a]", "-t", f"{vo.duration:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "5M", "-bufsize", "10M",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-movflags", "+faststart", str(out.resolve()),
            cwd=workdir)
    return out
