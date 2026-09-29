"""Сценарий ролика через Claude: 1) ищем свежую новость в интернете, 2) пишем по ней сценарий в JSON."""

from datetime import date

import anthropic
from pydantic import BaseModel

import config

client = anthropic.Anthropic()

# Если модель откажется отвечать, запрос автоматически перезапустится на резервной модели.
FALLBACK = dict(betas=["server-side-fallback-2026-07-01"], fallbacks="default")


class Segment(BaseModel):
    text: str  # фраза диктора
    visual_query: str  # что показать на фоне: запрос к стоку на английском, 2-4 слова


class VideoScript(BaseModel):
    topic: str  # тема в 3-6 словах, для истории
    title: str
    segments: list[Segment]
    description: str
    tags: list[str]


RESEARCH_SYSTEM = """Ты редактор русскоязычного YouTube-канала «{channel}» про нейросети и ИИ-инструменты.
Формат — вертикальные ролики до минуты для широкой аудитории, не для программистов."""

RESEARCH_PROMPT = """Сегодня {today}. Найди в интернете одну свежую (за последние 7 дней) тему для ролика:
новая нейросеть, крупное обновление популярного ИИ-сервиса или полезная фишка, которую зритель может
попробовать сам. Лучше то, что доступно бесплатно или из России.

{topic_hint}Эти темы уже были, не повторяйся:
{history}

Проверь факты по первоисточникам. Ответь кратким брифом на русском:
- что за инструмент/новость и чья;
- что конкретно нового, 3-5 фактов с цифрами;
- как попробовать (сайт, цена, ограничения);
- дата новости и ссылки на источники."""

SCRIPT_SYSTEM = """Ты сценарист вертикальных роликов про нейросети для канала «{channel}».
Пишешь живо и просто, как друг рассказывает другу. Никакой воды и канцелярита."""

SCRIPT_PROMPT = """Напиши сценарий ролика на 40-55 секунд по брифу ниже. Используй только факты из брифа.

Требования:
- segments: 6-9 фраз, всего 110-140 слов. Каждая фраза — 1-2 коротких предложения.
- Первая фраза — сильный крючок, который цепляет за 2 секунды (без «привет» и «в этом видео»).
- Предпоследняя фраза — как попробовать самому.
- Последняя фраза — призыв: {cta}
- Числа пиши словами, как их произносят; английские названия оставляй латиницей.
- visual_query — запрос к стоковым видео на английском (2-4 слова), конкретная картинка:
  "person typing laptop", "robot hand", "city night timelapse". Без названий брендов.
- title: до 70 символов, интригующий, без кликбейта-вранья, можно 1 эмодзи.
- description: 2-3 предложения о сути ролика.
- tags: 8-12 тегов на русском и английском.

Бриф:
{brief}"""


def _text(response) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


def _check(response) -> None:
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude отказался отвечать: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Ответ Claude обрезан по max_tokens")


def research(history: list[str], topic_hint: str = "") -> str:
    hint = f"Тему задал автор канала: «{topic_hint}». Раскрой её.\n\n" if topic_hint else ""
    messages = [{
        "role": "user",
        "content": RESEARCH_PROMPT.format(
            today=date.today().isoformat(),
            topic_hint=hint,
            history="\n".join(f"- {t}" for t in history[-40:]) or "- (пока ничего)",
        ),
    }]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]

    for _ in range(5):
        response = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            system=RESEARCH_SYSTEM.format(channel=config.CHANNEL_NAME),
            messages=messages,
            tools=tools,
            output_config={"effort": "medium"},
            **FALLBACK,
        )
        if response.stop_reason != "pause_turn":
            break
        # Серверный цикл поиска упёрся в лимит итераций — продолжаем с того же места.
        messages = messages[:1] + [{"role": "assistant", "content": response.content}]
    _check(response)
    return _text(response)


def write_script(brief: str) -> VideoScript:
    handle = config.telegram_handle()
    cta = (f"позови в Telegram-канал {handle}, где ещё больше нейросетей (ссылка в профиле)."
           if handle else "попроси подписаться, чтобы не пропустить новые нейросети.")
    response = client.beta.messages.parse(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=SCRIPT_SYSTEM.format(channel=config.CHANNEL_NAME),
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(cta=cta, brief=brief)}],
        output_format=VideoScript,
        output_config={"effort": "medium"},
        **FALLBACK,
    )
    _check(response)
    script = response.parsed_output
    if not script or not script.segments:
        raise RuntimeError("Claude вернул пустой сценарий")
    return script
