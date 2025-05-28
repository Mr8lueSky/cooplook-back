import os
from asyncio import sleep
from secrets import token_hex
from time import sleep as sync_sleep

import anyio
import libtorrent as lt
from starlette.responses import FileResponse
from starlette.types import Send


class LoadingFileResponse(FileResponse):
    chunk_size = 64 * 1024

    def __init__(self, *args, **kwargs):
        actual_size = kwargs.pop('actual_size', None)
        super().__init__(*args, **kwargs)
        if actual_size is None:
            raise ValueError("actual_size is not given")

        self.actual_size = actual_size

    async def _handle_simple(self, send: Send, send_header_only: bool) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            curr_size = 0
            async with await anyio.open_file(self.path, mode="rb") as file:
                more_body = True
                while more_body:
                    while curr_size + self.chunk_size > os.path.getsize(self.path) != self.actual_size:
                        await sleep(0.1)
                    chunk = await file.read(self.chunk_size)
                    more_body = len(chunk) == self.chunk_size
                    await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

    async def _handle_single_range(
            self, send: Send, start: int, end: int, file_size: int, send_header_only: bool
    ) -> None:
        self.headers["content-range"] = f"bytes {start}-{end - 1}/{file_size}"
        self.headers["content-length"] = str(end - start)
        await send({"type": "http.response.start", "status": 206, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async with await anyio.open_file(self.path, mode="rb") as file:
                curr_size = start
                while curr_size + self.chunk_size > os.path.getsize(self.path) != self.actual_size:
                    await sleep(0.1)
                await file.seek(start)
                more_body = True
                while more_body:
                    while curr_size + self.chunk_size > os.path.getsize(self.path) != self.actual_size:
                        await sleep(0.1)
                    chunk = await file.read(min(self.chunk_size, end - start))
                    start += len(chunk)
                    more_body = len(chunk) == self.chunk_size and start < end
                    await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

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
        await send({"type": "http.response.start", "status": 206, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async with await anyio.open_file(self.path, mode="rb") as file:
                for start, end in ranges:
                    await send({"type": "http.response.body", "body": header_generator(start, end), "more_body": True})
                    curr_size = start
                    while curr_size + self.chunk_size > os.path.getsize(self.path) != self.actual_size:
                        await sleep(0.1)
                    await file.seek(start)
                    while start < end:
                        while curr_size + self.chunk_size > os.path.getsize(self.path) != self.actual_size:
                            await sleep(0.1)
                        chunk = await file.read(min(self.chunk_size, end - start))
                        start += len(chunk)
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
                    await send({"type": "http.response.body", "body": b"\n", "more_body": True})
                await send(
                    {
                        "type": "http.response.body",
                        "body": f"\n--{boundary}--\n".encode("latin-1"),
                        "more_body": False,
                    }
                )


class LoadingTorrentFileResponse(FileResponse):
    chunk_size = 64 * 1024
    preload_pieces = 10

    def __init__(self, *args, torrent_info: lt.torrent_info = None, torrent_handle: lt.torrent_handle,
                 file_index: int = -1, piece_manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        while not os.path.isfile(self.path):
            sync_sleep(0.001)
        if torrent_info is None:
            raise AttributeError("torrent info is not given!")
        if torrent_handle == -1:
            raise AttributeError("torrent handle is not given")
        if file_index == -1:
            raise AttributeError("file index is not given")
        if piece_manager is None:
            raise AttributeError("piece manager is not given")
        self.ti = torrent_info
        self.fi = file_index
        self.th = torrent_handle
        self.pm = piece_manager

    async def _download_range(self, start: int, end: int = -1):
        print("Download range started")
        fs = self.ti.files()
        if end == -1:
            end = fs.file_size(self.fi)

        prs = self.ti.map_file(self.fi, start, 0)
        piece_start = prs.piece
        piece_start_offset = prs.start

        pre = self.ti.map_file(self.fi, end, 0)
        piece_end = pre.piece
        piece_end_offset = pre.start

        curr_piece = piece_start

        self.th.prioritize_pieces(
            (i, 7) for i in range(piece_start, min(piece_start + self.preload_pieces, piece_end + 1)))
        print(
            f"Prioritizing from {piece_start} to {min(piece_start + self.preload_pieces, piece_end)} for {start, end}")
        more_body = True

        while more_body:
            self.th.piece_priority(curr_piece + self.preload_pieces, 7)
            while not self.th.have_piece(curr_piece):
                await sleep(0.01)

            buffer = await self.pm.get_piece(curr_piece)
            piece_size = fs.piece_size(curr_piece)
            fr, to = 0, piece_size
            if curr_piece == piece_start:
                fr = piece_start_offset
            if curr_piece == piece_end:
                to = piece_end_offset

            for i in range(fr, to, self.chunk_size):
                print(f"Sent from {curr_piece}", min(to, i + self.chunk_size) - i)
                yield buffer[i:min(to, i + self.chunk_size)], more_body

            more_body = curr_piece != piece_end
            curr_piece += 1
        yield b'', False
        print("Download range finished")

    async def _handle_simple(self, send: Send, send_header_only: bool) -> None:
        print("Simple")
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async for body, more_body in self._download_range(0):
                resp = await send({"type": "http.response.body",
                                   "body": body,
                                   "more_body": more_body})
                print(resp)

    async def _handle_single_range(
            self, send: Send, start: int, end: int, file_size: int, send_header_only: bool
    ) -> None:
        print("Single range")
        self.headers["content-range"] = f"bytes {start}-{end - 1}/{file_size}"
        self.headers["content-length"] = str(end - start)
        await send({"type": "http.response.start", "status": 206, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            async for body, more_body in self._download_range(start, end):
                await send({"type": "http.response.body",
                            "body": body,
                            "more_body": more_body})

    async def _handle_multiple_ranges(
            self,
            send: Send,
            ranges: list[tuple[int, int]],
            file_size: int,
            send_header_only: bool,
    ) -> None:
        print("Multi range")
        # In firefox and chrome, they use boundary with 95-96 bits entropy (that's roughly 13 bytes).
        boundary = token_hex(13)
        content_length, header_generator = self.generate_multipart(
            ranges, boundary, file_size, self.headers["content-type"]
        )
        self.headers["content-range"] = f"multipart/byteranges; boundary={boundary}"
        self.headers["content-length"] = str(content_length)
        await send({"type": "http.response.start", "status": 206, "headers": self.raw_headers})
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        else:
            for start, end in ranges:
                await send({"type": "http.response.body", "body": header_generator(start, end), "more_body": True})
                async for body, _ in self._download_range(start, end):
                    await send({"type": "http.response.body", "body": body, "more_body": True})
                await send({"type": "http.response.body", "body": b"\n", "more_body": True})
            await send(
                {
                    "type": "http.response.body",
                    "body": f"\n--{boundary}--\n".encode("latin-1"),
                    "more_body": False,
                }
            )
