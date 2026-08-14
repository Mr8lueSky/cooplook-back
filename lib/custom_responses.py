import asyncio
import hashlib
import os
from asyncio import Task
from email.utils import formatdate
from secrets import token_hex
from typing import override
from collections.abc import Mapping
from fastapi import Request
from starlette.responses import FileResponse
from starlette.types import Send

from lib.logger import Logging
from lib.torrent.torrent_handler import FileTorrentHandler


class LoadingTorrentFileResponse(FileResponse, Logging):
    def __init__(
        self,
        torrent_handler: FileTorrentHandler,
        request: Request,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        method: str | None = None,
        content_disposition_type: str = "attachment",
    ):
        path = torrent_handler.file_path
        super().__init__(
            path,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            method=method,
            content_disposition_type=content_disposition_type,
        )
        self.request: Request = request
        self.tasks: list[Task[None]] = []
        self.torrent_handler: FileTorrentHandler = torrent_handler
        self._cancelled: bool = False

    def cancel(self):
        self._cancelled = True
        for task in self.tasks:
            _ = task.cancel()
        self.tasks.clear()

    @override
    def set_stat_headers(self, stat_result: os.stat_result) -> None:
        # Use stable headers that don't change while libtorrent writes pieces.
        # mtime/ctime change on every write, which breaks Chrome's If-Range
        # validation and causes range requests to fall back to whole-file 200.
        file_size = self.torrent_handler.torrent.file_size(
            self.torrent_handler.file_index
        )
        self.headers.setdefault("content-length", str(file_size))
        etag_base = self.torrent_handler.file_path + "-" + str(file_size)
        etag = f'"{hashlib.md5(etag_base.encode(), usedforsecurity=False).hexdigest()}"'
        self.headers.setdefault("etag", etag)
        # Derive a stable last-modified from the path hash (constant per file).
        path_hash = int(hashlib.md5(self.torrent_handler.file_path.encode(), usedforsecurity=False).hexdigest(), 16)
        self.headers.setdefault("last-modified", formatdate(path_hash % 1700000000, usegmt=True))

    async def _download_range(self, start: int, end: int):
        async for buffer in self.torrent_handler.iter_pieces(start, end):
            if self._cancelled:
                break
            yield buffer, True
            await asyncio.sleep(0)
        yield b"", False

    async def _download_single_range(self, send: Send, start: int, end: int):
        async for body, more_body in self._download_range(start, end):
            await send(
                {"type": "http.response.body", "body": body, "more_body": more_body}
            )
        self.logger.debug(f"Request {start}-{end} fully finished")

    async def _download_multiple_ranges(
        self, send: Send, ranges: list[tuple[int, int]]
    ):
        boundary = token_hex(13)
        for start, end in ranges:
            async for piece in self._download_range(start, end):
                await send(
                    {"type": "http.response.body", "body": piece, "more_body": True}
                )
            await send({"type": "http.response.body", "body": b"\n", "more_body": True})
        await send(
            {
                "type": "http.response.body",
                "body": f"\n--{boundary}--\n".encode("latin-1"),
                "more_body": False,
            }
        )

    @override
    async def _handle_simple(self, send: Send, send_header_only: bool) -> None:
        file_size = self.torrent_handler.torrent.file_size(
            self.torrent_handler.file_index
        )
        self.headers["content-length"] = str(file_size)
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            await self._download_single_range(send, 0, file_size)

    @override
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
            await self._download_single_range(send, start, end)

    @override
    async def _handle_multiple_ranges(
        self,
        send: Send,
        ranges: list[tuple[int, int]],
        file_size: int,
        send_header_only: bool,
    ) -> None:
        # In firefox and chrome, they use boundary with 95-96 bits entropy (that's roughly 13 bytes).
        boundary = token_hex(13)
        content_length, _ = self.generate_multipart(
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
            await self._download_multiple_ranges(send, ranges)