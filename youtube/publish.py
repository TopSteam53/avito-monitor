"""Публикация: загрузка на YouTube и отправка готового ролика в Telegram."""

import logging
import os
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def youtube_enabled() -> bool:
    return all(os.getenv(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"))


def upload_youtube(video: Path, title: str, description: str, tags: list[str]) -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=YOUTUBE_SCOPES,
    )
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": config.CATEGORY_ID,
            "defaultLanguage": "ru",
            "defaultAudioLanguage": "ru",
        },
        "status": {"privacyStatus": config.PRIVACY_STATUS, "selfDeclaredMadeForKids": False},
    }
    request = youtube.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def telegram_enabled() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_telegram(video: Path, text: str) -> None:
    """Шлёт ролик и текст для публикации себе в Telegram — удобно выкладывать с телефона."""
    api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
    chat = os.environ["TELEGRAM_CHAT_ID"]
    with open(video, "rb") as f:
        r = requests.post(f"{api}/sendVideo", data={"chat_id": chat, "supports_streaming": "true"},
                          files={"video": (video.name, f, "video/mp4")}, timeout=300)
    r.raise_for_status()
    requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": text[:4096]}, timeout=30).raise_for_status()
