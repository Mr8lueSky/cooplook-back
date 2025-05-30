import logging
import os
from asyncio import sleep
from secrets import token_hex
from time import sleep as sync_sleep
from time import time
from typing import AsyncGenerator

import libtorrent as lt
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.types import Send

logger = logging.getLogger(__name__)


class PieceManager:
    preload_pieces = 30
    max_prior_from = 15
    """torrent_info: lt.torrent_info = None, torrent_handle: lt.torrent_handle,
                 file_index: int = -1"""

    def __init__(
        self,
        session: lt.session,
        th: lt.torrent_handle,
        ti: lt.torrent_info,
        file_index: int,
    ):
        self.piece_buffer = {}
        self.piece_wait = {}
        self.ses = session
        self.th: lt.torrent_handle = th
        self.ti = ti
        self.fi = file_index
        self.last_piece = -1
        self.start, self.start_offset = self.bytes_to_piece_offset(0)
        self.end, self.end_offset = self.bytes_to_piece_offset(self.file_size())

    def bytes_to_piece_offset(self, b: int):
        pr = self.ti.map_file(self.fi, b, 0)
        return pr.piece, pr.start

    def file_size(self):
        return self.ti.files().file_size(self.fi)

    def initiate(self, b_start: int, b_end: int):
        p_start, _ = self.bytes_to_piece_offset(b_start)
        p_end, _ = self.bytes_to_piece_offset(b_end)
        self.th.prioritize_pieces(
            (i, 4) for i in range(p_start, p_end) if not self.th.have_piece(i)
        )
        for p in range(p_start, p_start + self.preload_pieces):
            self.th.set_piece_deadline(p, p - p_start, 0)

    def cleanup(self): ...

    async def iter_pieces(self, b_start: int, b_end: int = -1) -> AsyncGenerator[bytes]:
        if b_end == -1:
            b_end = self.file_size()
        self.initiate(b_start, b_end)
        start, start_offset = self.bytes_to_piece_offset(b_start)
        end, end_offset = self.bytes_to_piece_offset(b_end)
        for piece_id in range(start, end + 1):
            piece = await self.get_piece(piece_id)
            fr, to = 0, len(piece)
            if piece_id == start:
                fr = start_offset
            if piece_id == end:
                to = end_offset
            self.last_piece = piece_id
            yield piece[fr:to]

    def increment_queue(self, piece_id: int):
        self.piece_wait[piece_id] = self.piece_wait.get(piece_id, 0) + 1

    def decrement_queue(self, piece_id: int):
        self.piece_wait[piece_id] -= 1
        if not self.piece_wait[piece_id]:
            self.piece_wait.pop(piece_id)
            self.piece_buffer.pop(piece_id)

    async def get_piece(self, piece_id: int, timeout_s: int = 15):
        if not self.th.have_piece(piece_id + self.preload_pieces):
            self.th.piece_priority(piece_id + self.preload_pieces, 4)
        if not self.th.have_piece(piece_id + self.max_prior_from):
            self.th.piece_priority(piece_id + self.max_prior_from, 6)
        if not self.th.have_piece(piece_id):
            self.th.piece_priority(piece_id, 7)
        self.th.set_piece_deadline(
            piece_id + self.preload_pieces, piece_id - self.start, 0
        )
        self.increment_queue(piece_id)
        finish = time() + timeout_s

        while not self.th.have_piece(piece_id) and finish > time():
            await sleep(0.005)

        if not self.th.have_piece(piece_id):
            self.decrement_queue(piece_id)
            raise AttributeError(
                f"Don't have {piece_id} after {timeout_s}! "
                f"Priority: {self.th.piece_priority(piece_id)}"
            )

        self.th.read_piece(piece_id)

        while piece_id not in self.piece_buffer and finish > time():
            alerts = self.ses.pop_alerts()
            for a in alerts:
                if isinstance(a, lt.read_piece_alert) and self.piece_wait.get(a.piece):
                    logger.debug(f"Got {a.piece}, curr: {piece_id}")
                    self.piece_buffer[a.piece] = a.buffer
            await sleep(0.005)

        if piece_id not in self.piece_buffer:
            self.decrement_queue(piece_id)
            raise AttributeError(f"{piece_id} not read in {timeout_s}")
        buffer = self.piece_buffer[piece_id]

        return buffer


class LoadingTorrentFileResponse(FileResponse):
    chunk_size = 64 * 1024

    def __init__(self, *args, piece_manager: PieceManager | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        while not os.path.isfile(self.path):
            sync_sleep(0.001)
        if piece_manager is None:
            raise AttributeError("piece manager is not given")
        self.pm = piece_manager
        self.request: Request | None = None

    async def _download_range(self, start: int, end: int = -1):
        if end == -1:
            end = self.pm.file_size()

        async for buffer in self.pm.iter_pieces(start, end):
            if self.request and await self.request.is_disconnected():
                self.pm.cleanup()
                return
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
            async for body, more_body in self._download_range(0):
                await send(
                    {"type": "http.response.body", "body": body, "more_body": more_body}
                )

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
            async for body, more_body in self._download_range(start, end):
                await send(
                    {"type": "http.response.body", "body": body, "more_body": more_body}
                )

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
