"""Автопилот YouTube-канала: тема → сценарий → озвучка → видео → публикация.

    python youtube/main.py                  # сделать и опубликовать ролик
    python youtube/main.py --no-upload      # только сделать ролик (он будет в youtube/out/)
    python youtube/main.py --topic "Sora 2"  # задать тему вручную
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import config
import footage
import publish
import render
import voice
import writer

log = logging.getLogger("autopilot")


def load_history() -> list[dict]:
    if config.HISTORY_FILE.exists():
        return json.loads(config.HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def build_description(script: writer.VideoScript) -> str:
    parts = [script.description.strip()]
    if config.TELEGRAM_URL:
        parts.append(f"👉 Ещё больше нейросетей в Telegram: {config.TELEGRAM_URL}")
    parts.append("#нейросети #ии #shorts")
    return "\n\n".join(parts)


def strip_brackets(text: str) -> str:
    """YouTube не принимает < и > в заголовке и описании."""
    return text.replace("<", "").replace(">", "")


def fit_tags(tags: list[str], limit: int = 450) -> list[str]:
    """YouTube ограничивает суммарную длину тегов 500 символами."""
    out, total = [], 0
    for tag in (t.strip().replace("#", "") for t in tags):
        if tag and total + len(tag) + 3 <= limit:
            out.append(tag)
            total += len(tag) + 3
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="не загружать на YouTube")
    parser.add_argument("--topic", default=os.getenv("VIDEO_TOPIC", ""), help="тема ролика")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    if not config.TELEGRAM_URL:
        log.warning("TELEGRAM_URL не задан — в ролике не будет ссылки на Telegram")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    workdir = config.OUT_DIR / stamp
    workdir.mkdir(parents=True, exist_ok=True)
    history = load_history()

    log.info("Ищу тему…")
    brief = writer.research([h["topic"] for h in history], args.topic)
    (workdir / "brief.md").write_text(brief, encoding="utf-8")

    log.info("Пишу сценарий…")
    script = writer.write_script(brief)
    title = strip_brackets(script.title).strip()[:95]
    description = strip_brackets(build_description(script))
    tags = fit_tags(script.tags)
    (workdir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    log.info("Тема: %s | %s", script.topic, title)

    log.info("Озвучиваю…")
    vo = voice.make_voiceover([s.text for s in script.segments], workdir)
    log.info("Длительность: %.1f с", vo.duration)

    log.info("Подбираю видео…")
    clips = footage.fetch_clips([s.visual_query for s in script.segments], workdir)

    log.info("Собираю ролик…")
    video = render.render(vo, clips, workdir, config.OUT_DIR / f"{stamp}.mp4")
    post_text = f"{title}\n\n{description}\n\nТеги: {', '.join(tags)}"
    (config.OUT_DIR / f"{stamp}.txt").write_text(post_text, encoding="utf-8")
    log.info("Готово: %s", video)

    video_id = None
    if args.no_upload:
        log.info("Загрузка на YouTube пропущена (--no-upload)")
    elif publish.youtube_enabled():
        video_id = publish.upload_youtube(video, title, description, tags)
        log.info("Загружено: https://youtube.com/shorts/%s", video_id)
    else:
        log.info("Ключи YouTube не заданы — ролик не загружен")

    history.append({"date": stamp, "topic": script.topic, "title": title, "video_id": video_id})
    config.HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if publish.telegram_enabled():
        link = f"\n\nhttps://youtube.com/shorts/{video_id}" if video_id else ""
        publish.send_telegram(video, post_text + link)
        log.info("Ролик отправлен в Telegram")


if __name__ == "__main__":
    main()
