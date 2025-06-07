import asyncio
from asyncio import Task, sleep
from collections.abc import AsyncGenerator
from secrets import token_hex
from time import time

import libtorrent as lt
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.types import Send

from logger import Logging


class TorrentManager(Logging):
    preload_pieces: int = 50

    def __init__(self, torrent: bytes | str, file_index: int, save_path: str):
        self.th: lt.torrent_handle | None = None
        self.ti: lt.torrent_info = lt.torrent_info(torrent)
        self.piece_buffer: dict[int, bytes] = {}
        self.piece_wait: dict[int, int] = {}
        self.ses: lt.session = lt.session()
        self.fi: int = file_index
        self.files: lt.file_storage = self.ti.files()
        self.file_start, self.file_start_offset = self.bytes_to_piece_offset(0)
        self.last_used_piece = self.file_start
        self.file_end, self.file_end_offset = self.bytes_to_piece_offset(
            self.file_size()
        )
        self.save_path = save_path

    def set_new_fi(self, new_fi: int):
        self.fi = new_fi
        self.file_start, self.file_start_offset = self.bytes_to_piece_offset(0)
        self.last_used_piece = self.file_start
        self.file_end, self.file_end_offset = self.bytes_to_piece_offset(
            self.file_size()
        )

    def get_curent_filename(self) -> str:
        return self.files.file_name(self.fi)

    def get_current_filepath(self) -> str:
        return self.files.file_path(self.fi, self.save_path)

    def get_all_filenames(self) -> list[tuple[int, str]]:
        files = []
        for fi in range(self.ti.num_files()):
            files.append((fi, self.files.file_name(fi)))
        return files

    def bytes_to_piece_offset(self, b: int) -> tuple[int, int]:
        pr = self.ti.map_file(self.fi, b, 0)
        return pr.piece, pr.start

    def initiate_torrent_download(self):
        if self.th is None: 
            self.th = self.ses.add_torrent({"ti": self.ti, "save_path": self.save_path})
        self.th.prioritize_pieces((i, 0) for i in range(self.ti.files().num_pieces()))
        self.th.prioritize_pieces(
            (i, 4)
            for i in range(self.file_start, self.file_end + 1)
            if not self.th.have_piece(i)
        )
        self.th.set_piece_deadline(self.file_end, 0, 0)
        self.initiate_request(0) 

    def file_size(self) -> int:
        return self.files.file_size(self.fi)

    def initiate_request(self, b_start: int):
        if self.th is None:
            raise RuntimeError("Torrent download in not initialized!")
        p_start, _ = self.bytes_to_piece_offset(b_start)
        self.logger.debug(f"Setting deadlines from {p_start=}")
        for p in range(p_start, p_start + self.preload_pieces):
            self.th.set_piece_deadline(p, p - p_start, 0)

    def cleanup(self):
        if self.th is None:
            return
        self.ses.remove_torrent(self.th, lt.session.delete_files) 

    async def iter_pieces(self, b_start: int, b_end: int = -1) -> AsyncGenerator[bytes]:
        if b_end == -1:
            b_end = self.file_size()
        self.initiate_request(b_start)
        start, start_offset = self.bytes_to_piece_offset(b_start)
        end, end_offset = self.bytes_to_piece_offset(b_end)
        if end_offset == 0:
            end -= 1
            end_offset = self.ti.piece_size(end)
        self.logger.debug(f"For {b_start} to {b_end}, {end=}, {end_offset=}")
        for piece_id in range(start, end + 1):
            piece = await self.get_piece(piece_id)
            fr, to = 0, len(piece)
            if piece_id == start:
                fr = start_offset
            if piece_id == end:
                to = end_offset
            self.last_used_piece = piece_id
            yield piece[fr:to]

    def increment_queue(self, piece_id: int):
        self.piece_wait[piece_id] = self.piece_wait.get(piece_id, 0) + 1

    def decrement_queue(self, piece_id: int):
        self.piece_wait[piece_id] -= 1
        if not self.piece_wait[piece_id]:
            self.piece_wait.pop(piece_id, None)
            self.piece_buffer.pop(piece_id, None)

    async def get_piece(self, piece_id: int, timeout_s: int = 60) -> bytes:
        if self.th is None:
            raise RuntimeError("Download is not initiated!")
        next_p = piece_id + self.preload_pieces
        self.logger.debug(f"Setting deadline for {piece_id + self.preload_pieces}")
        if piece_id not in self.piece_wait and next_p <= self.file_end:
            self.th.set_piece_deadline(
                piece_id + self.preload_pieces, self.last_used_piece - piece_id, 0
            )
        self.increment_queue(piece_id)
        finish = time() + timeout_s

        self.logger.debug(f"Waiting for {piece_id}")
        while not self.th.have_piece(piece_id) and finish > time():
            await sleep(0)

        if not self.th.have_piece(piece_id):
            self.decrement_queue(piece_id)
            raise AttributeError(
                f"Don't have {piece_id} after {timeout_s}! "
                f"Priority: {self.th.piece_priority(piece_id)} "
                f"Have piece: {self.th.have_piece(piece_id)}"
            )

        self.th.read_piece(piece_id)
        
        self.logger.debug(f"Waiting for read on {piece_id}")
        while piece_id not in self.piece_buffer and finish > time():
            alerts = self.ses.pop_alerts()
            for a in alerts:
                if isinstance(a, lt.read_piece_alert) and self.piece_wait.get(a.piece):
                    self.logger.debug(f"Got {a.piece}")
                    self.piece_buffer[a.piece] = a.buffer
            await sleep(0)

        if piece_id not in self.piece_buffer:
            self.decrement_queue(piece_id)
            raise AttributeError(f"{piece_id} not read in {timeout_s}")
        buffer = self.piece_buffer[piece_id]
        self.decrement_queue(piece_id)
        return buffer


class LoadingTorrentFileResponse(FileResponse, Logging):
    chunk_size = 64 * 1024

    def __init__(
        self,
        *args,
        piece_manager: TorrentManager | None = None,
        request: Request | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if piece_manager is None:
            raise AttributeError("piece manager is not given")
        if request is None:
            raise AttributeError("request must be provided")
        self.pm = piece_manager
        self.stop = False
        self.request = request
        self.tasks: list[Task] = []

    def cancel(self):
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()

    async def _download_range(self, start: int, end: int = -1):
        if end == -1:
            end = self.pm.file_size()

        async for buffer in self.pm.iter_pieces(start, end):
            yield buffer, True
        yield b"", False

    async def _handle_simple(self, send: Send, send_header_only: bool) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async with asyncio.TaskGroup() as tg:
                self.tasks.append(
                    tg.create_task(self._download_single_range(send, 0))
                )
                while not await self.request.is_disconnected() and self.tasks:
                    await sleep(1)
                self.cancel()

    async def _download_single_range(self, send: Send, start: int, end: int = -1):
        async for body, more_body in self._download_range(start, end):
            await send(
                {"type": "http.response.body", "body": body, "more_body": more_body}
            )
        self.logger.debug(f"Request {start}-{end} fully finished")

    async def _handle_single_range(
        self, send: Send, start: int, end: int, file_size: int, send_header_only: bool
    ) -> None:
        self.headers["content-range"] = f"bytes {start}-{end - 1}/{file_size}"
        self.headers["content-length"] = str(end - start)
        await send(
            {"type": "http.response.start", "status": 206, "headers": self.raw_headers}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async with asyncio.TaskGroup() as tg:
                self.tasks.append(
                    tg.create_task(self._download_single_range(send, start, end))
                )
                while not await self.request.is_disconnected() and self.tasks:
                    await sleep(1)
                if await self.request.is_disconnected():
                    self.logger.debug("Request dicsonnected by client")
                self.cancel()

    async def _handle_multiple_ranges(
        self,
        send: Send,
        ranges: list[tuple[int, int]],
        file_size: int,
        send_header_only: bool,
    ) -> None:
        # In firefox and chrome, they use boundary with 95-96 bits entropy (that's roughly 13 bytes).
        boundary = token_hex(13)
        content_length, header_generator = self.generate_multipart(
            ranges, boundary, file_size, self.headers["content-type"]
        )
        self.headers["content-range"] = f"multipart/byteranges; boundary={boundary}"
        self.headers["content-length"] = str(content_length)
        await send(
            {"type": "http.response.start", "status": 206, "headers": self.raw_headers}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            for start, end in ranges:
                await send(
                    {
                        "type": "http.response.body",
                        "body": header_generator(start, end),
                        "more_body": True,
                    }
                )
                async for body, _ in self._download_range(start, end):
                    await send(
                        {"type": "http.response.body", "body": body, "more_body": True}
                    )
                await send(
                    {"type": "http.response.body", "body": b"\n", "more_body": True}
                )
            await send(
                {
                    "type": "http.response.body",
                    "body": f"\n--{boundary}--\n".encode("latin-1"),
                    "more_body": False,
                }
            )
