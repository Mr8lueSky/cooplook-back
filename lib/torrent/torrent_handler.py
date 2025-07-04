from asyncio import sleep
import asyncio
from collections.abc import AsyncGenerator
import os
from time import time


from lib.logger import Logging
from lib.torrent.alert_observer import AlertObserver
from lib.torrent.piece_getter import PieceGetter
from lib.torrent.torrent import PiecePriority, Torrent

WAIT_FILE_READY_SLEEP = 0


class FileTorrentHandler(Logging):
    def __init__(self, torrent: Torrent, file_index: int) -> None:
        self.torrent: Torrent = torrent
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
        _ = asyncio.create_task(self.alert_observer.observe_alerts())

    @property
    def file_path(self):
        return self.torrent.file_path(self.file_index)

    async def wait_file_ready(self, timeout_s: int = 30) -> str:
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
        self.init_download()

    def cleanup(self):
        self.torrent.cleanup()
        self.alert_observer.cleanup()

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

        self.logger.debug(
            f"Starting download {byte_start}-{byte_end}. "
            + f"{piece_start=}, {piece_end=} "
            + f"{start_offset=}, {end_offset=}"
        )
        if end_offset == 0:
            piece_end -= 1
            end_offset = self.torrent.piece_size(piece_end)

        for piece_id in range(piece_start, piece_end + 1):
            self.torrent.set_piece_deadline(piece_id, piece_id - piece_start)

        if piece_start == piece_end:
            yield (await self.piece_getter.get_piece(piece_start))[
                start_offset:end_offset
            ]
            return

        yield (await self.piece_getter.get_piece(piece_start))[start_offset:]

        for piece_id in range(piece_start + 1, piece_end):
            yield await self.piece_getter.get_piece(piece_id)

        if piece_end != piece_start:
            yield (await self.piece_getter.get_piece(piece_end))[:end_offset]
