"""Новый выпуск канала Евы: бриф → сценарий → озвучка → кадры → оживление → монтаж → превью → Telegram.

    python youtube/main.py                     # шоураннер сам выберет тему (первый выпуск — знакомство)
    python youtube/main.py --topic "Sora 2"    # тема от автора
    python youtube/main.py --no-telegram       # не отправлять в Telegram (всё будет в youtube/out/)
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import agents
import config
import eva3d
import render
import telegram
import thumbnail
import visuals
import voice

log = logging.getLogger("eva")

LIPSYNC_PRICE = {"480p": 0.08, "720p": 0.15}  # $ за секунду у veed/fabric-1.0
IMAGE_PRICE = 0.08


def load_history() -> list[dict]:
    if config.HISTORY_FILE.exists():
        return json.loads(config.HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def clean(text: str) -> str:
    """YouTube не принимает < и > в названии и описании."""
    return text.replace("<", "").replace(">", "").strip()


def timestamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters_text(meta: agents.Metadata, vo: voice.Voiceover) -> str:
    """Таймкоды для YouTube: первая глава с 0:00, минимум три главы, каждая не короче 10 секунд."""
    starts: dict[int, str] = {}
    for ch in sorted(meta.chapters, key=lambda c: c.scene):
        if 0 <= ch.scene < len(vo.segment_times):
            starts.setdefault(ch.scene, clean(ch.title))
    if 0 not in starts and starts:
        first = min(starts)
        starts[0] = starts.pop(first)
    lines, last = [], -10.0
    for scene, title in sorted(starts.items()):
        t = vo.segment_times[scene][0]
        if t - last >= 10:
            lines.append(f"{timestamp(t)} {title}")
            last = t
    return "\n".join(lines) if len(lines) >= 3 else ""


def build_description(meta: agents.Metadata, vo: voice.Voiceover) -> str:
    parts = [clean(meta.description)]
    chapters = chapters_text(meta, vo)
    if chapters:
        parts.append(chapters)
    if config.TELEGRAM_URL:
        parts.append(f"👉 Ещё больше нейросетей в Telegram: {config.TELEGRAM_URL}")
    parts.append("#нейросети #ии #ева")
    return "\n\n".join(parts)


def fit_tags(tags: list[str], limit: int = 450) -> list[str]:
    """YouTube ограничивает суммарную длину тегов 500 символами."""
    out, total = [], 0
    for tag in (clean(t).replace("#", "") for t in tags):
        if tag and total + len(tag) + 3 <= limit:
            out.append(tag)
            total += len(tag) + 3
    return out


def write_script(path, brief: str, episode: agents.Episode, plan: agents.ArtPlan) -> None:
    shots = {s.scene: s for s in plan.shots}
    lines = [f"# {episode.topic}", "", f"История: {episode.story_beat}", ""]
    for i, s in enumerate(episode.scenes):
        shot = shots.get(i)
        lines += [f"**[{i}] {'Ева в кадре' if s.kind == 'talk' else 'Кадр'}**", s.text]
        if shot:
            lines.append(f"_Картинка: {shot.prompt}_")
        lines.append("")
    lines += ["---", "## Бриф", brief]
    path.write_text("\n".join(lines), encoding="utf-8")


def make_script(brief: str, workdir) -> tuple[agents.Episode, voice.Voiceover]:
    """Сценарист пишет, редактор правит; если вышло короче MIN_SECONDS — редактор дописывает."""
    log.info("Сценарист пишет…")
    episode = agents.screenwriter(brief)
    log.info("Редактор правит…")
    episode = agents.editor(brief, episode)
    for _ in range(2):
        log.info("Озвучка: %d сцен…", len(episode.scenes))
        vo = voice.make_voiceover([s.text for s in episode.scenes], workdir)
        log.info("Длительность: %.0f с", vo.duration)
        if vo.duration >= config.MIN_SECONDS:
            return episode, vo
        words = sum(len(s.text.split()) for s in episode.scenes)
        extra = int(words * (config.MIN_SECONDS + 40) / vo.duration) - words
        episode = agents.editor(brief, episode, note=(
            f"После озвучки выпуск длится {vo.duration:.0f} секунд, а нужно не меньше {config.MIN_SECONDS + 40}: "
            f"вертикальные видео короче трёх минут YouTube превращает в шортсы. Добавь примерно {extra} слов — "
            f"новые сцены story в основной части."))
    vo = voice.make_voiceover([s.text for s in episode.scenes], workdir)
    if vo.duration < config.MIN_SECONDS:
        log.warning("Выпуск всё ещё короткий (%.0f с) — YouTube может сделать его шортсом", vo.duration)
    return episode, vo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="", help="тема выпуска")
    parser.add_argument("--no-telegram", action="store_true", help="не отправлять в Telegram")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    three_d = config.use_3d()
    if not three_d and not config.REFERENCE_IMAGE.exists():
        raise SystemExit("Нет лица Евы (persona/eva.png). Сначала запусти кастинг: python youtube/casting.py")

    history = load_history()
    number = len(history) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    name = f"eva-{number:03d}"
    workdir = config.OUT_DIR / f"{name}-{stamp}"
    workdir.mkdir(parents=True, exist_ok=True)

    # 1. Бриф: первый выпуск — знакомство, дальше тему ищет шоураннер.
    if number == 1 and not args.topic:
        brief = (config.PERSONA_DIR / "pilot.md").read_text(encoding="utf-8")
    else:
        log.info("Шоураннер ищет тему…")
        brief = agents.showrunner(history, args.topic)
    (workdir / "brief.md").write_text(brief, encoding="utf-8")

    # 2-3. Сценарий и озвучка.
    episode, vo = make_script(brief, workdir)
    log.info("Тема: %s", episode.topic)

    # 4. Раскадровка и превью.
    log.info("Арт-директор рисует раскадровку…")
    plan = agents.art_director(episode)
    shots = {s.scene: s for s in plan.shots}
    write_script(workdir / "script.md", brief, episode, plan)

    # 5. Кадры: по картинке на сцену плюс превью, параллельно. В 3D-режиме говорящие сцены рендерит Blender
    #    (в это же время), а под них генерируется только фон.
    talk = [i for i, s in enumerate(episode.scenes) if s.kind == "talk"]
    if three_d:
        log.info("Рендерю эталон 3D-Евы…")
        reference = eva3d.render_reference(workdir / "eva_reference.png")
    else:
        reference = config.REFERENCE_IMAGE

    def scene_image(i: int):
        scene, shot = episode.scenes[i], shots.get(i)
        prompt = shot.prompt if shot else f"Eva in {plan.talk_setting}, looking into the camera"
        with_eva = scene.kind == "talk" or (shot.with_eva if shot else True)
        out = workdir / f"scene_{i:02d}"
        return visuals.generate_images(prompt, out, with_eva=with_eva, reference=reference)[0]

    to_draw = [i for i in range(len(episode.scenes)) if not (three_d and i in talk)]
    log.info("Генерирую %d кадров и превью…", len(to_draw))
    with ThreadPoolExecutor(5) as pool:
        if three_d and talk:
            log.info("Рендерю 3D-Еву: %d сцен…", len(talk))
            emotions = {i: shots[i].emotion for i in talk if i in shots}
            eva_job = pool.submit(eva3d.render_talks, vo, talk, emotions, workdir)
            bg_job = pool.submit(visuals.generate_images, f"{plan.talk_setting}. Empty location, no people.",
                                 workdir / "talk_bg", with_eva=False)
        thumb_job = pool.submit(visuals.generate_images, plan.thumbnail.prompt, workdir / "thumb",
                                with_eva=True, aspect="16:9", reference=reference)
        drawn = dict(zip(to_draw, pool.map(scene_image, to_draw)))
        thumb_image = thumb_job.result()[0]
        if three_d and talk:
            frames_3d, background = eva_job.result(), bg_job.result()[0]
    thumb = thumbnail.make_thumbnail(thumb_image, plan.thumbnail.text, plan.thumbnail.text_side,
                                     config.OUT_DIR / f"{name}.jpg")
    media = [render.SceneMedia(drawn.get(i), shots[i].motion if i in shots else "zoom_in")
             for i in range(len(episode.scenes))]
    images_made = len(drawn) + 1

    # 6. Ева говорит в камеру.
    talk_seconds = 0.0
    if three_d:
        for i in talk:
            media[i].frames_3d, media[i].background = frames_3d[i], background
        images_made += 1
    else:
        # Оживляем портреты сцен talk (платно), пока не кончится лимит секунд.
        budget, talk_jobs = config.LIPSYNC_MAX_SECONDS, []
        for i in talk:
            length = vo.segment_times[i][1] - vo.segment_times[i][0]
            if length <= budget:
                talk_jobs.append(i)
                budget -= length
        talk_seconds = config.LIPSYNC_MAX_SECONDS - budget
        log.info("Оживляю Еву: %d сцен, %.0f с…", len(talk_jobs), talk_seconds)
        with ThreadPoolExecutor(3) as pool:
            videos = pool.map(lambda i: visuals.lipsync(drawn[i], vo.parts[i], workdir / f"talk_{i:02d}.mp4"),
                              talk_jobs)
            for i, video in zip(talk_jobs, videos):
                media[i].talk_video = video

    # 7. Монтаж.
    log.info("Монтирую…")
    video = render.render(vo, media, workdir, config.OUT_DIR / f"{name}.mp4")

    # 8. Тексты для публикации.
    log.info("SMM готовит описание…")
    meta = agents.smm(episode)
    title = clean(meta.title)[:100]
    description = build_description(meta, vo)
    tags = fit_tags(meta.tags)
    lipsync_price = LIPSYNC_PRICE.get(config.LIPSYNC_RESOLUTION, 0.08) if "fabric" in config.LIPSYNC_MODEL else 0.02
    cost = agents.claude_cost() + images_made * IMAGE_PRICE + talk_seconds * lipsync_price
    post = {"title": title, "description": description, "tags": tags,
            "pinned_comment": clean(meta.pinned_comment), "telegram_post": meta.telegram_post,
            "duration": round(vo.duration), "cost_usd": round(cost, 2)}
    (config.OUT_DIR / f"{name}.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Готово: %s (%.0f с, ~$%.2f)", video, vo.duration, cost)

    history.append({"episode": number, "date": stamp, "topic": episode.topic,
                    "story_beat": episode.story_beat, "title": title})
    config.HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 9. Всё — в Telegram.
    if args.no_telegram or not telegram.enabled():
        log.info("Telegram не настроен или отключён — файлы в %s", config.OUT_DIR)
        return
    m, s = divmod(round(vo.duration), 60)
    telegram.send([
        telegram.Message(f"🎬 Выпуск {number} готов: {title}\nДлительность {m}:{s:02d}, расходы ≈ ${cost:.2f}"),
        telegram.Message("Видео для загрузки", file=video),
        telegram.Message("Превью (1280×720)", file=thumb),
        telegram.Message(title),
        telegram.Message(description),
        telegram.Message(", ".join(tags)),
        telegram.Message(f"Закреплённый комментарий:\n\n{post['pinned_comment']}"),
        telegram.Message(f"Пост для твоего Telegram-канала:\n\n{meta.telegram_post}"),
        telegram.Message("Сценарий и бриф", file=workdir / "script.md"),
        telegram.Message("При загрузке: «Изменённый или синтетический контент» → Да. Сообщения выше идут "
                         "по порядку: название, описание, теги — их удобно копировать."),
    ])
    log.info("Отправлено в Telegram")


if __name__ == "__main__":
    main()
