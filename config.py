from datetime import timedelta
from pathlib import Path

ENV = "DEV"
DB_URL = "sqlite+aiosqlite:///test.db"

TORRENT_SAVE_PATH = Path("torrents")
TORRENT_FILES_SAVE_PATH = Path("torrent_files")
MAX_TORRENT_FILE_SIZE = 5 * 1024 * 1024  # 5 megabytes

ROOM_INACTIVITY_PERIOD = 10 * 60  # 10 minutes

AUTH_SECRET_KEY = b"SOME RANDOM AUTH KEY(change for prod use)"
PW_SECRET_KET = b"SOME SECRET PW KEY(change for prod use)"

ACCESS_TOKEN_EXPIRE = timedelta(days=30)  # one mounth
