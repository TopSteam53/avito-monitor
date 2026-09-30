"""Монтаж: по сцене — «живая» картинка (движение камеры) или говорящая Ева, сверху субтитры и ник канала."""

import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config
from voice import Voiceover, Word

WHITE, YELLOW = "&H00FFFFFF&", "&H0000E5FF&"  # в ASS цвета записываются как BGR
ZOOM = 0.15  # насколько камера наезжает/отъезжает за сцену

# Выражения zoompan: on — номер кадра, N — всего кадров в сцене.
MOTIONS = {
    "zoom_in": (f"1+{ZOOM}*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "zoom_out": (f"1+{ZOOM}-{ZOOM}*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "pan_left": (f"1+{ZOOM}", "(iw-iw/zoom)*(1-on/N)", "ih/2-(ih/zoom/2)"),
    "pan_right": (f"1+{ZOOM}", "(iw-iw/zoom)*on/N", "ih/2-(ih/zoom/2)"),
    "pan_up": (f"1+{ZOOM}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/N)"),
    "pan_down": (f"1+{ZOOM}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/N"),
}


@dataclass
class SceneMedia:
    image: Path | None
    motion: str = "zoom_in"
    talk_video: Path | None = None  # если есть — Ева говорит в кадре (оживлённый портрет)
    frames_3d: Path | None = None  # если есть — Ева говорит в кадре (3D, PNG с прозрачным фоном)
    background: Path | None = None  # фон под 3D-Еву


def ffmpeg(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, cwd=cwd)


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").upper()


def _chunks(words: list[Word], max_words: int = 3, max_chars: int = 16) -> list[list[Word]]:
    """Режем речь на короткие куски по 1-3 слова; кусок не переходит через границу сцены."""
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
        f"Style: Cap,{config.FONT},92,{WHITE},{WHITE},&H00000000&,&H99000000&,"
        "-1,0,0,0,100,100,0,0,1,7,3,2,90,90,560,1",
        f"Style: Tag,{config.FONT},50,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H99000000&,"
        "-1,0,0,0,100,100,0,0,1,4,2,8,60,60,190,1",
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
            end = chunk[wi + 1].start if wi + 1 < len(chunk) else chunk_end
            if end <= word.start:
                continue
            text = " ".join(
                f"{{\\c{YELLOW}}}{_clean(w.text)}{{\\c{WHITE}}}" if j == wi else _clean(w.text)
                for j, w in enumerate(chunk)
            )
            pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(word.start)},{_ts(end)},Cap,,0,0,0,,{pop}{text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


_ENCODE = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
_FIT = (f"scale={config.WIDTH}:{config.HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={config.WIDTH}:{config.HEIGHT},setsar=1")


def _story_clip(image: Path, motion: str, duration: float, out: Path) -> Path:
    frames = max(1, round(duration * config.FPS))
    z, x, y = (e.replace("N", str(frames)) for e in MOTIONS.get(motion, MOTIONS["zoom_in"]))
    w2, h2 = config.WIDTH * 2, config.HEIGHT * 2  # увеличиваем заранее, чтобы движение было плавным
    vf = (f"scale={w2}:{h2}:force_original_aspect_ratio=increase:flags=lanczos,crop={w2}:{h2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={config.WIDTH}x{config.HEIGHT}:fps={config.FPS},"
          "setsar=1")
    ffmpeg("-i", str(image), "-vf", vf, "-frames:v", str(frames), *_ENCODE, str(out))
    return out


def _talk_clip(video: Path, duration: float, out: Path) -> Path:
    """Говорящая Ева; если видео короче сцены (пауза), держим последний кадр."""
    vf = f"{_FIT},fps={config.FPS},tpad=stop_mode=clone:stop_duration={duration:.3f}"
    ffmpeg("-i", str(video), "-vf", vf, "-t", f"{duration:.3f}", *_ENCODE, str(out))
    return out


def talk3d_clip(frames: Path, background: Path | None, duration: float, out: Path) -> Path:
    """3D-Ева (кадры 12 к/с с прозрачным фоном) поверх слегка размытого фона."""
    bg = (["-loop", "1", "-i", str(background)] if background else
          ["-f", "lavfi", "-i", f"color=c=0x1e1433:s={config.WIDTH}x{config.HEIGHT}"])
    graph = (f"[0:v]{_FIT},boxblur=3:1[bg];"
             f"[1:v]scale={config.WIDTH}:{config.HEIGHT}:flags=lanczos[eva];"
             f"[bg][eva]overlay=shortest=1,fps={config.FPS},"
             f"tpad=stop_mode=clone:stop_duration={duration:.3f}[v]")
    ffmpeg(*bg, "-framerate", str(config.RENDER_3D_FPS), "-i", str(frames / "frame_%04d.png"),
            "-filter_complex", graph, "-map", "[v]", "-t", f"{duration:.3f}", *_ENCODE, str(out))
    return out


def render(vo: Voiceover, media: list[SceneMedia], workdir: Path, out: Path) -> Path:
    clips = []
    for i, (m, (start, end)) in enumerate(zip(media, vo.segment_times)):
        clip = workdir / f"clip_{i:02d}.mp4"
        if m.frames_3d:
            talk3d_clip(m.frames_3d, m.background, end - start, clip)
        elif m.talk_video:
            _talk_clip(m.talk_video, end - start, clip)
        else:
            _story_clip(m.image, m.motion, end - start, clip)
        clips.append(clip)
    (workdir / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    write_captions(vo, workdir / "captions.ass")

    inputs = ["-f", "concat", "-safe", "0", "-i", "clips.txt", "-i", str(vo.path.resolve())]
    tracks = sorted(p for ext in ("mp3", "m4a", "wav") for p in config.MUSIC_DIR.glob(f"*.{ext}"))
    if tracks:
        inputs += ["-stream_loop", "-1", "-i", str(random.choice(tracks).resolve())]
        fade = max(vo.duration - 3, 0)
        audio = (f"[2:a]volume={config.MUSIC_VOLUME_DB}dB,afade=t=out:st={fade:.2f}:d=3[m];"
                 f"[1:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
    else:
        audio = "[1:a]loudnorm=I=-14:TP=-1.5[a]"

    ffmpeg(*inputs,
            "-filter_complex", f"[0:v]ass=captions.ass[v];{audio}",
            "-map", "[v]", "-map", "[a]", "-t", f"{vo.duration:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "8M", "-bufsize", "16M",
            "-pix_fmt", "yuv420p", "-r", str(config.FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart", str(out.resolve()),
            cwd=workdir)
    return out
