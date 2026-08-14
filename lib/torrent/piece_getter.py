from asyncio import sleep
from collections import OrderedDict
from time import time

import libtorrent as lt

from lib.torrent.alert_observer import AlertObserver
from lib.torrent.exceptions import (
    PieceHaveTimeoutException,
    PieceReadTimeoutException,
    PieceTimeoutException,
)
from lib.torrent.torrent_info import (
    Alert,
    ReadPieceAlert,
    SetDeadlineFlags,
    TorrentInfo,
)


WAIT_PIECE_HAVE_SLEEP = 0.1
WAIT_PIECE_READ_SLEEP = 0.1

PIECE_CACHE_SIZE = 64


class PieceGetter:
    def __init__(self, torrent: TorrentInfo, alert_observer: AlertObserver) -> None:
        self.piece_wait_count: dict[int, int] = {}
        self.piece_buffer: dict[int, bytes] = {}
        self.piece_cache: OrderedDict[int, bytes] = OrderedDict()
        self.torrent: TorrentInfo = torrent
        self.alert_observer: AlertObserver = alert_observer
        self.alert_observer.add_alert_observer(
            lt.read_piece_alert, self.handle_read_piece_alert
        )

    async def wait_piece_have(self, piece_id: int, timeout_s: int = 60):
        if self._has_piece(piece_id):
            return
        finish = time() + timeout_s
        while time() < finish and not self.torrent.have_piece(piece_id):
            await sleep(WAIT_PIECE_HAVE_SLEEP)
        if not self.torrent.have_piece(piece_id) and not self._has_piece(piece_id):
            raise PieceHaveTimeoutException(f"No piece {piece_id} in {timeout_s}")

    def handle_read_piece_alert(self, alert: Alert) -> None:
        if not isinstance(alert, ReadPieceAlert):
            raise RuntimeError(
                f"Alert is not a type of read_piece_alert! Actual type: {type(alert)}"
            )
        if alert.error.value() != 0 or alert.size <= 0 or alert.buffer is None:
            return
        buf = bytes(alert.buffer)
        self._cache_piece(alert.piece, buf)
        if alert.piece in self.piece_wait_count:
            self.piece_buffer[alert.piece] = buf

    def is_waiting_for_piece(self, piece_id: int) -> bool:
        return piece_id in self.piece_wait_count

    def _has_piece(self, piece_id: int) -> bool:
        return piece_id in self.piece_buffer or piece_id in self.piece_cache

    def _cache_piece(self, piece_id: int, buf: bytes) -> None:
        self.piece_cache[piece_id] = buf
        self.piece_cache.move_to_end(piece_id)
        while len(self.piece_cache) > PIECE_CACHE_SIZE:
            self.piece_cache.popitem(last=False)

    async def wait_piece_read(self, piece_id: int, timeout_s: int = 60, retries: int = 2):
        for attempt in range(retries + 1):
            if self._has_piece(piece_id):
                return
            finish = time() + timeout_s
            while time() < finish:
                if self._has_piece(piece_id):
                    return
                await sleep(WAIT_PIECE_READ_SLEEP)
            if self._has_piece(piece_id):
                return
        raise PieceReadTimeoutException(
            (
                f"Can't read {piece_id} in {timeout_s} after {retries} retries!\n"
                f"Piece priority: {self.torrent.get_piece_priority(piece_id)}\n"
                f"Have piece: {self.torrent.have_piece(piece_id)}"
            )
        )

    def require_piece(self, piece_id: int, in_s: int = 0):
        count = self.piece_wait_count.get(piece_id, 0)
        self.piece_wait_count[piece_id] = count + 1
        if count == 0:
            self.torrent.set_piece_deadline(
                piece_id, in_s, SetDeadlineFlags.ALERT_WHEN_AVAILABLE
            )

    def not_require_piece(self, piece_id: int):
        self.piece_wait_count[piece_id] = max(
            0, self.piece_wait_count.get(piece_id, 0) - 1
        )
        if self.piece_wait_count.get(piece_id, 0) <= 0:
            _ = self.piece_wait_count.pop(piece_id, None)
            _ = self.piece_buffer.pop(piece_id, None)

    async def get_piece(self, piece_id: int) -> bytes:
        try:
            if piece_id in self.piece_cache:
                self.piece_cache.move_to_end(piece_id)
                return self.piece_cache[piece_id]
            await self.wait_piece_have(piece_id)
            await self.wait_piece_read(piece_id)
            if piece_id in self.piece_cache:
                self.piece_cache.move_to_end(piece_id)
                return self.piece_cache[piece_id]
            return self.piece_buffer[piece_id]
        except PieceTimeoutException as exc:
            raise exc
        except Exception as exc:
            raise exc
        finally:
            self.not_require_piece(piece_id)