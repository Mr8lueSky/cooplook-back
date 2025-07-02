from asyncio import sleep
from collections import defaultdict
from collections.abc import AsyncGenerator, Awaitable, Iterable
from enum import Enum
import os
from time import time
from typing import Callable

import libtorrent as lt


class PieceTimeoutException(Exception): ...


class PieceHaveTimeoutException(PieceTimeoutException): ...


class PieceReadTimeoutException(PieceTimeoutException): ...


AlertType = type[lt.alert]
Alert = lt.alert
TorrentAlert = lt.torrent_alert
ReadPieceAlert = lt.read_piece_alert
NotifyAlert = Callable[[Alert], Awaitable[None]]

WAIT_PIECE_HAVE_SLEEP = 0
WAIT_PIECE_READ_SLEEP = 0
WAIT_FILE_READY_SLEEP = 0
OBSERVE_ALERTS_SLEEP = 0


class PiecePriority(int, Enum):
    DONT_DOWNLOAD = 0
    LOWEST = 1
    LOW = 2
    MEDIUM = 3
    DEFAULT = 4
    HIGH = 5
    HIGHEST = 6


class Torrent:
    def __init__(self, torrent_path: str, save_path: str):
        self.session: lt.session = lt.session(
            {"enable_incoming_utp": False, "enable_incoming_tcp": False}
        )
        self.ti: lt.torrent_info = lt.torrent_info(torrent_path)
        self.th: lt.torrent_handle = self.session.add_torrent(
            {"ti": self.ti, "save_path": save_path}
        )
        self.save_path: str = save_path
        self.files: lt.file_storage = self.ti.files()

    def cleanup(self):
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

    def get_piece_priority(self, piece_id: int) -> PiecePriority:
        return PiecePriority(self.th.piece_priority(piece_id))

    def set_piece_deadline(self, piece_id: int, deadline_s: int, flags: int = 0):
        self.th.set_piece_deadline(piece_id, deadline_s, flags)

    def clear_deadlines(self):
        self.th.clear_piece_deadlines()

    def pieces_count(self) -> int:
        return self.ti.num_pieces()

    def pop_alerts(self) -> list[Alert]:
        return self.session.pop_alerts()

    def read_piece(self, piece_id: int):
        self.th.read_piece(piece_id)

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


class AlertObserver:
    def __init__(self, torrent: Torrent) -> None:
        self.alert_observers: defaultdict[AlertType, list[NotifyAlert]] = defaultdict(
            list
        )
        self.torrent: Torrent = torrent
        self.observe: bool = True

    async def observe_alerts(self):
        while self.observe:
            alerts = self.torrent.pop_alerts()
            for a in alerts:
                alert_type = type(a)
                for observer in self.alert_observers[alert_type]:
                    await observer(a)
            await sleep(OBSERVE_ALERTS_SLEEP)

    def cleanup(self):
        self.observe = False

    def add_alert_observer(self, alert_type: AlertType, observer: NotifyAlert):
        self.alert_observers[alert_type].append(observer)

    def remove_alert_observer(self, alert_type: AlertType, observer: NotifyAlert):
        self.alert_observers[alert_type].remove(observer)


class PieceGetter:
    def __init__(self, torrent: Torrent, alert_observer: AlertObserver) -> None:
        self.piece_wait_count: dict[int, int] = {}
        self.piece_buffer: dict[int, bytes] = {}
        self.torrent: Torrent = torrent
        self.alert_observer: AlertObserver = alert_observer

    async def wait_piece_have(self, piece_id: int, timeout_s: int = 60):
        finish = time() + timeout_s
        while time() < finish and not self.torrent.have_piece(piece_id):
            await sleep(WAIT_PIECE_HAVE_SLEEP)
        if not self.torrent.have_piece(piece_id):
            raise PieceHaveTimeoutException(f"No piece {piece_id} in {timeout_s}")

    async def handle_read_piece_alert(self, alert: Alert) -> None:
        if not isinstance(alert, ReadPieceAlert):
            raise RuntimeError(
                f"Alert is not a type of read_piece_alert! Actual type: {type(alert)}"
            )
        self.piece_buffer[alert.piece] = alert.buffer

    async def wait_piece_read(self, piece_id: int, timeout_s: int = 60):
        self.torrent.read_piece(piece_id)
        self.alert_observer.add_alert_observer(
            lt.read_piece_alert, self.handle_read_piece_alert
        )
        finish = time() + timeout_s
        while time() < finish and piece_id not in self.piece_buffer:
            await sleep(WAIT_PIECE_READ_SLEEP)
        if piece_id not in self.piece_buffer:
            raise PieceReadTimeoutException(f"Can't read {piece_id} in {timeout_s}!")

    def require_piece(self, piece_id: int):
        self.piece_wait_count[piece_id] += 1

    def not_require_piece(self, piece_id: int):
        self.piece_wait_count[piece_id] -= 1
        if self.piece_wait_count[piece_id] <= 0:
            _ = self.piece_wait_count.pop(piece_id, None)
            _ = self.piece_buffer.pop(piece_id, None)

    async def get_piece(self, piece_id: int) -> bytes:
        self.require_piece(piece_id)
        try:
            await self.wait_piece_have(piece_id)
            await self.wait_piece_read(piece_id)
            return self.piece_buffer[piece_id]
        except PieceTimeoutException as exc:
            raise exc
        except Exception as exc:
            raise exc
        finally:
            self.not_require_piece(piece_id)


class FileTorrentHandler:
    def __init__(self, torrent_path: str, file_index: int, save_path: str) -> None:
        self.torrent: Torrent = Torrent(torrent_path, save_path)
        self.dont_download_everything()
        self.alert_observer: AlertObserver = AlertObserver(self.torrent)
        self.file_index: int = file_index
        self.piece_getter: PieceGetter = PieceGetter(self.torrent, self.alert_observer)
        self.init_download()

    def init_download(self):
        piece_start, _ = self.torrent.piece_bytes_offset(self.file_index, 0)
        piece_end, _ = self.torrent.piece_bytes_offset(
            self.file_index, self.torrent.file_size(self.file_index)
        )
        self.torrent.set_piece_deadline(piece_start, PiecePriority.HIGHEST)
        self.torrent.set_piece_deadline(piece_end, PiecePriority.HIGHEST)

    @property
    def file_path(self):
        return self.torrent.file_path(self.file_index)

    async def wait_file_ready(self, timeout_s: int = 15) -> str:
        finish = time() + timeout_s
        while time() < finish and not os.path.exists(self.file_path):
            await sleep(WAIT_FILE_READY_SLEEP)
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File {self.file_path} not exists!")
        return self.file_path

    def get_all_files(self) -> list[tuple[int, str]]:
        return [
            (file_id, self.torrent.get_file_name(file_id))
            for file_id in range(self.torrent.files_count())
        ]

    def dont_download_everything(self):
        self.torrent.set_pieces_priority(
            (piece_id, PiecePriority.DONT_DOWNLOAD)
            for piece_id in range(self.torrent.pieces_count())
        )

    def set_file_index(self, file_index: int):
        self.file_index = file_index
        self.torrent.clear_deadlines()

    def cleanup(self):
        self.torrent.cleanup()

    async def iter_pieces(
        self, byte_start: int, byte_end: int = -1
    ) -> AsyncGenerator[bytes]:
        if byte_end == -1:
            byte_end = self.torrent.file_size(self.file_index)

        piece_start, start_offset = self.torrent.piece_bytes_offset(
            self.file_index, byte_start
        )
        piece_end, end_offset = self.torrent.piece_bytes_offset(
            self.file_index, byte_end
        )

        if end_offset == 0:
            piece_end -= 1
            end_offset = self.torrent.piece_size(piece_end)

        for piece_id in range(piece_start, piece_end + 1):
            self.torrent.set_piece_deadline(piece_id, piece_start - piece_id)

        yield (await self.piece_getter.get_piece(piece_start))[start_offset:]

        for piece_id in range(piece_start + 1, piece_end):
            yield await self.piece_getter.get_piece(piece_id)

        yield (await self.piece_getter.get_piece(piece_end))[:end_offset]
