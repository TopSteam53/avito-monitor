"""Кастинг Евы: генерирует варианты внешности или утверждает выбранный.

    python youtube/casting.py                        # 4 новых варианта → persona/candidates/ и в Telegram
    python youtube/casting.py --wishes "рыжее каре"  # то же, с пожеланиями
    python youtube/casting.py --pick 2               # утвердить вариант 2 → persona/eva.png
"""

import argparse
import logging
import shutil

import config
import telegram
import visuals

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pick", type=int, help="номер утверждаемого варианта")
    parser.add_argument("--wishes", default="", help="пожелания к внешности")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if args.pick:
        pick(args.pick)
    else:
        generate(args.wishes)


if __name__ == "__main__":
    main()
