"""Команда агентов. Каждый агент — это Claude со своей ролью (agents/<роль>.md) и общей библией Евы."""

from datetime import date
from typing import Literal

import anthropic
from pydantic import BaseModel

import config

client = anthropic.Anthropic()

# Если модель откажется отвечать, запрос автоматически перезапустится на резервной модели.
FALLBACK = dict(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

Motion = Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]


class Scene(BaseModel):
    kind: Literal["talk", "story"]  # talk — Ева говорит в камеру, story — картинка под закадровый голос
    text: str


class Episode(BaseModel):
    topic: str
    story_beat: str
    scenes: list[Scene]


class Shot(BaseModel):
    scene: int
    with_eva: bool
    prompt: str
    motion: Motion
    emotion: Literal["neutral", "joy", "fun", "sorrow", "surprised", "angry"]


class Thumbnail(BaseModel):
    prompt: str
    text: str
    text_side: Literal["left", "right"]


class ArtPlan(BaseModel):
    talk_setting: str
    shots: list[Shot]
    thumbnail: Thumbnail


class Chapter(BaseModel):
    scene: int
    title: str


class Metadata(BaseModel):
    title: str
    description: str
    tags: list[str]
    chapters: list[Chapter]
    pinned_comment: str
    telegram_post: str


# Сколько потрачено на Claude за запуск (цены Opus 5.5: $4 / $20 за 1M токенов, поиск $10 за 1000).
spent = {"input": 0, "output": 0, "searches": 0}


def _track(response) -> None:
    u = response.usage
    spent["input"] += sum(getattr(u, k, 0) or 0 for k in
                          ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    spent["output"] += u.output_tokens or 0
    spent["searches"] += getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0


def claude_cost() -> float:
    return spent["input"] * 4e-6 + spent["output"] * 20e-6 + spent["searches"] * 0.01


def _system(role: str) -> str:
    prompt = (config.AGENTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    persona = (config.PERSONA_DIR / "eva.md").read_text(encoding="utf-8")
    return f"{prompt}\n\n<persona>\n{persona}\n</persona>"


def _check(response) -> None:
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude отказался отвечать: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Ответ Claude обрезан по max_tokens")


def _ask(role: str, task: str, schema: type[BaseModel], effort: str = "medium"):
    response = client.beta.messages.parse(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=_system(role),
        messages=[{"role": "user", "content": task}],
        output_format=schema,
        output_config={"effort": effort},
        **FALLBACK,
    )
    _track(response)
    _check(response)
    if response.parsed_output is None:
        raise RuntimeError(f"Агент {role} вернул пустой ответ")
    return response.parsed_output


def format_script(episode: Episode) -> str:
    return "\n".join(f"[{i}] ({s.kind}) {s.text}" for i, s in enumerate(episode.scenes))


def format_history(history: list[dict]) -> str:
    lines = [f"- Выпуск {h['episode']} ({h['date']}): {h['topic']}. История: {h['story_beat']}"
             for h in history[-30:]]
    return "\n".join(lines) or "- (пока ни одного)"


def showrunner(history: list[dict], topic_hint: str = "") -> str:
    """Шоураннер: ищет тему в интернете и пишет бриф выпуска."""
    hint = f"Автор канала просит сделать выпуск на тему: «{topic_hint}».\n\n" if topic_hint else ""
    messages = [{
        "role": "user",
        "content": f"Сегодня {date.today().isoformat()}. {hint}"
                   f"Прошлые выпуски:\n{format_history(history)}\n\nПридумай следующий выпуск.",
    }]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    for _ in range(5):
        response = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            system=_system("showrunner"),
            messages=messages,
            tools=tools,
            output_config={"effort": "medium"},
            **FALLBACK,
        )
        _track(response)
        if response.stop_reason != "pause_turn":
            break
        # Серверный цикл поиска упёрся в лимит итераций — продолжаем с того же места.
        messages = messages[:1] + [{"role": "assistant", "content": response.content}]
    _check(response)
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


def screenwriter(brief: str) -> Episode:
    cta = f"Telegram-канал: {config.TELEGRAM_URL}" if config.TELEGRAM_URL else "Telegram-канал (ссылка в описании)"
    return _ask("screenwriter", f"Бриф выпуска:\n{brief}\n\nКуда звать зрителей: {cta}", Episode, effort="high")


def editor(brief: str, episode: Episode, note: str = "") -> Episode:
    task = f"Бриф:\n{brief}\n\nСценарий:\n{format_script(episode)}"
    if note:
        task += f"\n\nЗамечание: {note}"
    return _ask("editor", task, Episode)


def art_director(episode: Episode) -> ArtPlan:
    return _ask("art_director", f"Сценарий:\n{format_script(episode)}", ArtPlan)


def smm(episode: Episode) -> Metadata:
    return _ask("smm", f"Сценарий:\n{format_script(episode)}", Metadata, effort="low")
