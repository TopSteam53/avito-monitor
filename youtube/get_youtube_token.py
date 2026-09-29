"""Один раз запусти у себя на компьютере, чтобы получить YOUTUBE_REFRESH_TOKEN.

    pip install google-auth-oauthlib
    python get_youtube_token.py client_secret.json

Откроется браузер — войди в Google-аккаунт канала и разреши загрузку видео.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

secrets_file = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(secrets_file, scopes=SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print("\nДобавь в GitHub → Settings → Secrets and variables → Actions:\n")
print(f"YOUTUBE_CLIENT_ID      = {creds.client_id}")
print(f"YOUTUBE_CLIENT_SECRET  = {creds.client_secret}")
print(f"YOUTUBE_REFRESH_TOKEN  = {creds.refresh_token}")
