from collections.abc import Iterable
from enum import Enum
from lib.logger import Logging
import libtorrent as lt


Alert = lt.alert
TorrentAlert = lt.torrent_alert
ReadPieceAlert = lt.read_piece_alert


EXTENSIONS = ()

DEFAULT_SESSION_ARGS = {
    "request_timeout": 10,
    "peer_timeout": 10,
    "cache_size": 0,
    "smooth_connects": False,
    "support_share_mode": False,
    "enable_upnp": False,
    "enable_natpmp": False,
    "enable_lsd": False,
    "auto_sequential": False,
    "aio_threads": 1,
    "torrent_connect_boost": 100,
}


class PiecePriority(int, Enum):
    DONT_DOWNLOAD = 0
    LOWEST = 1
    LOW = 2
    MEDIUM = 3
    DEFAULT = 4
    HIGH = 5
    HIGHEST = 6


class SetDeadlineFlags(int, Enum):
    ALERT_WHEN_AVAILABLE = 1


def create_torrent_session() -> lt.session:
    session = lt.session(DEFAULT_SESSION_ARGS)
    for extension in EXTENSIONS:
        session.add_extension(extension)
    return session


class TorrentInfo(Logging):
    def __init__(self, torrent_path: str, save_path: str):
        self.session: lt.session = create_torrent_session()
        self.ti: lt.torrent_info = lt.torrent_info(torrent_path)
        self.th: lt.torrent_handle = self.session.add_torrent(
            {"ti": self.ti, "save_path": save_path}
        )
        self.save_path: str = save_path
        self.files: lt.file_storage = self.ti.files()

    def cleanup(self):
        self.logger.debug(f"Removing torrent handle for {self.save_path}")
        self.session.remove_torrent(self.th, lt.session.delete_files)

    def piece_bytes_offset(self, file_id: int, bytes_offset: int) -> tuple[int, int]:
        pr = self.ti.map_file(file_id, bytes_offset, 0)
        return pr.piece, pr.start

    def piece_size(self, piece_id: int) -> int:
        return self.ti.piece_size(piece_id)

    def set_pieces_priority(self, pieces: Iterable[tuple[int, PiecePriority]]):
        self.th.prioritize_pieces(
            (piece_id, priority.value) for piece_id, priority in pieces
        )

    def set_piece_deadline(self, piece_id: int, deadline_s: int, flags: int = 0):
        if self.have_piece(piece_id):
            return
        self.logger.debug(f"Setting deadline for piece {piece_id} to {deadline_s}")
        self.th.set_piece_deadline(piece_id, deadline_s, flags)

    def clear_deadlines(self):
        self.logger.debug(f"Clearing deadlines for {self.save_path}")
        self.th.clear_piece_deadlines()

    def pieces_count(self) -> int:
        return self.ti.num_pieces()

    def pop_alerts(self) -> list[Alert]:
        return self.session.pop_alerts()

    def read_piece(self, piece_id: int):
        self.th.read_piece(piece_id)

    def get_piece_priority(self, piece_id: int) -> PiecePriority:
        return PiecePriority(self.th.piece_priority(piece_id))

    def have_piece(self, piece_id: int) -> bool:
        return self.th.have_piece(piece_id)

    def get_file_name(self, file_id: int) -> str:
        return self.files.file_name(file_id)

    def files_count(self) -> int:
        return self.ti.num_files()

    def file_path(self, file_id: int) -> str:
        return self.files.file_path(file_id, self.save_path)

    def file_size(self, file_ind: int) -> int:
        return self.files.file_size(file_ind)
