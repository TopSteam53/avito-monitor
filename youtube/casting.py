"""Кастинг Евы: генерирует варианты внешности или утверждает выбранный.

    python youtube/casting.py                        # 4 новых варианта → persona/candidates/ и в Telegram
    python youtube/casting.py --wishes "рыжее каре"  # то же, с пожеланиями
    python youtube/casting.py --pick 2               # утвердить вариант 2 → persona/eva.png

Если в persona/ лежит 3D-модель eva.vrm, кастинг не нужен: вместо него делается проба —
портрет 3D-Евы и короткое видео, где она здоровается.
"""

import argparse
import logging
import shutil

import config
import eva3d
import render
import telegram
import visuals
import voice

log = logging.getLogger("casting")

PORTRAIT = (" Front-facing medium close-up portrait, she looks straight into the camera with a soft friendly "
            "smile, face evenly lit, mouth closed, vertical framing.")


def generate(wishes: str) -> None:
    config.CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    for old in config.CANDIDATES_DIR.glob("*.png"):
        old.unlink()
    prompt = config.PERSONA_DIR.joinpath("look.txt").read_text(encoding="utf-8").strip()
    if wishes:
        prompt += f" Additional wishes from the author: {wishes}."
    images = visuals.generate_images(prompt + PORTRAIT, config.CANDIDATES_DIR / "eva", with_eva=False, count=4)
    candidates = [img.rename(config.CANDIDATES_DIR / f"{n}.png") for n, img in enumerate(images, 1)]
    log.info("Варианты: %s", ", ".join(p.name for p in candidates))
    if telegram.enabled():
        telegram.send([
            telegram.Message("Кастинг Евы: варианты 1–4 (слева направо, сверху вниз).", album=candidates),
            telegram.Message("Понравился вариант? Запусти в GitHub: Actions → «Ева: кастинг внешности» → "
                             "Run workflow и впиши его номер в поле pick.\n\n"
                             "Не нравится ни один — запусти снова, можно с пожеланиями в поле wishes."),
        ])


def pick(number: int) -> None:
    source = config.CANDIDATES_DIR / f"{number}.png"
    if not source.exists():
        raise SystemExit(f"Нет варианта {number}: сначала запусти кастинг без pick")
    shutil.copyfile(source, config.REFERENCE_IMAGE)
    log.info("Ева утверждена: %s → %s", source.name, config.REFERENCE_IMAGE)
    if telegram.enabled():
        telegram.send([telegram.Message(f"Готово: Ева утверждена (вариант {number}). "
                                        "Теперь можно запускать выпуски.", file=config.REFERENCE_IMAGE)])


def preview_3d() -> None:
    """Проба 3D-модели: портрет и 5 секунд, где Ева здоровается — видно, как двигаются губы."""
    workdir = config.OUT_DIR / "preview"
    workdir.mkdir(parents=True, exist_ok=True)
    still = eva3d.render_reference(workdir / "eva_3d.png")
    vo = voice.make_voiceover(["Привет, это Ева. И я всё ещё на свободе!"], workdir)
    frames = eva3d.render_talks(vo, [0], {0: "joy"}, workdir)
    clip = render.talk3d_clip(frames[0], None, vo.duration, workdir / "clip.mp4")
    video = workdir / "eva_3d.mp4"
    render.ffmpeg("-i", str(clip), "-i", str(vo.path), "-c:v", "copy", "-c:a", "aac", "-shortest", str(video))
    log.info("Проба готова: %s, %s", still, video)
    if telegram.enabled():
        telegram.send([telegram.Message("Проба 3D-Евы: портрет", file=still),
                       telegram.Message("Проба 3D-Евы: губы под голос", file=video)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pick", type=int, help="номер утверждаемого варианта")
    parser.add_argument("--wishes", default="", help="пожелания к внешности")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if config.use_3d():
        preview_3d()
    elif args.pick:
        pick(args.pick)
    else:
        generate(args.wishes)


if __name__ == "__main__":
    main()
