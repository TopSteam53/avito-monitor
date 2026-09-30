"""3D-Ева: считаем губы по кадрам и запускаем рендер в Blender (blender/eva_render.py) отдельным процессом."""

import json
import subprocess
import sys
from pathlib import Path

import config
import lipsync
from voice import Voiceover, Word

SCRIPT = config.ROOT / "blender" / "eva_render.py"


def _run(job: dict, job_file: Path) -> None:
    job_file.write_text(json.dumps(job), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), str(job_file)], check=True)


def render_reference(out: Path) -> Path:
    """Портрет 3D-Евы — по нему генератор рисует её в остальных кадрах и на превью."""
    _run({"model": str(config.MODEL_3D), "still": str(out), "width": 1080, "height": 1920},
         out.with_suffix(".json"))
    return out


def render_talks(vo: Voiceover, scenes: list[int], emotions: dict[int, str], workdir: Path) -> dict[int, Path]:
    """Рендерит говорящую Еву для сцен scenes; возвращает папки с кадрами (PNG с прозрачным фоном)."""
    width, height = config.RENDER_3D_SIZE
    jobs = []
    for i in scenes:
        start, end = vo.segment_times[i]
        words = [Word(w.text, w.start - start, w.end - start) for w in vo.words if w.segment == i]
        jobs.append({
            "out_dir": str(workdir / f"eva3d_{i:02d}"),
            "emotion": emotions.get(i, "neutral"),
            "seed": i,
            "frames": lipsync.mouth_track(words, vo.parts[i], end - start, fps=config.RENDER_3D_FPS, seed=i),
        })
    _run({"model": str(config.MODEL_3D), "width": width, "height": height, "fps": config.RENDER_3D_FPS,
          "scenes": jobs}, workdir / "eva3d_job.json")
    return {i: Path(job["out_dir"]) for i, job in zip(scenes, jobs)}
