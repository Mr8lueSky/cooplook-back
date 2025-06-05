from pathlib import Path

ENV = "DEV"
DB_URL = "sqlite+aiosqlite:///test.db"

TORRENT_SAVE_PATH = Path("torrents")
TORRENT_FILES_SAVE_PATH = Path("torrent_files")
MAX_TORRENT_FILE_SIZE = 5 * 1024 * 1024
