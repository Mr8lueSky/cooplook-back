import os
from asyncio import sleep
from secrets import token_hex

import anyio
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
        print("stat_result", self.stat_result)
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
        print("stat_result", self.stat_result)
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
        print("stat_result", self.stat_result)
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
