import os
from datetime import timedelta
from pathlib import Path

ENV = os.environ.get("ENV", "DEV")
DB_URL = os.environ.get("DB_URL", "sqlite+aiosqlite:///test.db")

TORRENT_SAVE_PATH = Path("torrents")
TORRENT_FILES_SAVE_PATH = Path("torrent_files")
MAX_TORRENT_FILE_SIZE = 5 * 1024 * 1024  # 5 megabytes

ROOM_INACTIVITY_PERIOD = 10 * 60  # 10 minutes

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "SOME RANDOM AUTH KEY(change for prod use)").encode("utf-8")
PW_SECRET_KEY = os.environ.get("PW_SECRET_KEY", "SOME SECRET PW KEY(change for prod use)").encode("utf-8")

ACCESS_TOKEN_EXPIRE = timedelta(days=30)  # one month
