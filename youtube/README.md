# YouTube-автопилот: «Нейросети за минуту»

Каждый день GitHub Actions сам делает вертикальный ролик (Shorts) про свежие нейросети:

1. **Claude** ищет в интернете свежую новость про ИИ и проверяет факты.
2. **Claude** пишет сценарий на 40–55 секунд с крючком в начале и призывом перейти в Telegram в конце.
3. **edge-tts** озвучивает его бесплатным нейроголосом.
4. **Pexels** подбирает стоковые видео под каждую фразу (без ключа будет анимированный градиент).
5. **ffmpeg** собирает ролик 1080×1920: крупные субтитры с подсветкой слов, ник Telegram-канала сверху, музыка.
6. Ролик загружается на YouTube и/или приходит тебе в Telegram.

Темы не повторяются: история хранится в `history.json`.

## Шаг 1. Минимальный запуск (ролик скачиваешь и выкладываешь сам)

В репозитории на GitHub: **Settings → Secrets and variables → Actions**.

**Secrets:**

| Имя | Где взять |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/), бесплатно |

**Variables** (вкладка Variables):

| Имя | Пример |
|---|---|
| `TELEGRAM_URL` | `https://t.me/my_ai_channel` |
| `CHANNEL_NAME` | `Нейросети за минуту` |

Дальше **Actions → YouTube autopilot → Run workflow**, сними галочку «Загрузить на YouTube» и запусти.
Через 3–5 минут готовый ролик появится внизу страницы запуска, в разделе **Artifacts**.

> Расписание (cron) работает только в основной ветке репозитория, так что сначала влей эту ветку в `main`.

## Шаг 2. Автозагрузка на YouTube

1. Зайди в [Google Cloud Console](https://console.cloud.google.com/) и создай проект.
2. Открой **APIs & Services → Library**, найди **YouTube Data API v3** и нажми Enable.
3. **OAuth consent screen**: тип External, добавь свой e-mail в Test users, затем нажми
   **Publish app → In production**. Без этого ключ перестанет работать через 7 дней.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**, скачай JSON.
5. У себя на компьютере выполни:
   ```bash
   pip install google-auth-oauthlib
   python youtube/get_youtube_token.py client_secret.json
   ```
   Войди в аккаунт **канала**. Скрипт выведет три значения, добавь их в Secrets:
   `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.

**Важно.** Пока Google не проверит проект, всё, что загружено через API, YouTube делает приватным.
Чтобы ролики выходили публичными, подай заявку на
[YouTube API Audit](https://support.google.com/youtube/contact/yt_api_form). До одобрения пользуйся шагом 3.

## Шаг 3. Получать готовые ролики в Telegram (удобно выкладывать с телефона)

1. Создай бота через [@BotFather](https://t.me/BotFather) и нажми у него **Start**.
2. Узнай свой chat id, например у [@userinfobot](https://t.me/userinfobot).
3. Добавь в Secrets `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.

Каждый день бот будет присылать видео и готовый текст: заголовок, описание, теги.

## Как лить трафик в Telegram

- В Shorts ссылки в описании **не кликабельны**. Поставь ссылку на Telegram в **шапку канала**:
  Творческая студия → Настройка канала → Профиль → Ссылки.
  Ролики говорят «ссылка в профиле», а ник канала всё время виден на экране.
- 1–2 ролика в день достаточно: массовая заливка однотипного контента — прямой путь к бану за спам.
- Поглядывай на ролики хотя бы первые недели. Если что-то звучит криво, поправь промпты в `writer.py`.

## Настройки

| Что | Где |
|---|---|
| Время и частота выхода | `cron` в `.github/workflows/youtube.yml` (время в UTC; 15:07 UTC = 18:07 МСК) |
| Голос | переменная `TTS_VOICE`: `ru-RU-DmitryNeural` или `ru-RU-SvetlanaNeural` |
| Видимость на YouTube | переменная `YOUTUBE_PRIVACY`: `public` / `unlisted` / `private` |
| Музыка | положи треки без авторских прав в `assets/music/` |
| Стиль и формат роликов | промпты в `writer.py` |
| Разовая тема | Run workflow → поле «Тема ролика» |

Стоимость: Claude API обходится примерно в $0.3–0.5 за ролик (поиск и сценарий). Остальное бесплатно,
GitHub Actions для публичных репозиториев не тарифицируется.

## Локальный запуск

```bash
sudo apt install ffmpeg
pip install -r youtube/requirements.txt
export ANTHROPIC_API_KEY=... PEXELS_API_KEY=... TELEGRAM_URL=https://t.me/...
python youtube/main.py --no-upload
```
