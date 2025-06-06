import abc
import os
from asyncio import sleep
from pathlib import Path
from uuid import UUID

from fastapi import Response
from fastapi.responses import FileResponse

import config
from custom_responses import LoadingTorrentFileResponse, PieceManager


class VideoSource(abc.ABC):
    def __init__(self, _: str, file_index: int, room_id: UUID) -> None:
        super().__init__()
        self.room_id: UUID | None = room_id
        self.fi = file_index

    def get_player_src(self) -> str:
        return f"/files/{self.room_id}"

    def start(self): ...

    def cancel(self): ...

    @abc.abstractmethod
    async def get_video_response(self, request) -> Response: ...


class HttpLinkVideoSource(VideoSource):
    def __init__(self, link: str, _: int, room_id: UUID):
        super().__init__("", 0, room_id)
        self.link = link

    def get_player_src(self, *_, **__) -> str:
        return self.link

    def get_video_response(self, request):
        raise AttributeError("Don't need to be implemented")


class FileVideoSource(VideoSource):
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def get_video_response(self, request) -> Response:
        return FileResponse(self.file_path)


class TorrentVideoSource(VideoSource):
    SAVE_PATH: Path = config.TORRENT_SAVE_PATH

    def __init__(self, torrent: bytes | str, file_index: int, room_id: UUID):
        super().__init__("", file_index, room_id)
        self.torrent = torrent
        self.pm = PieceManager(self.torrent, self.fi, self.save_path)
        self.resps: list[LoadingTorrentFileResponse] = []

    @property
    def save_path(self) -> str:
        if self.room_id is None:
            raise AttributeError("Room id is not set!")
        return str(self.SAVE_PATH / str(self.room_id))

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.pm.initiate_torrent_download()

    def cancel(self):
        for r in self.resps:
            r.cancel()
        self.resps.clear()

    async def get_video_response(self, request) -> LoadingTorrentFileResponse:
        file_path = self.pm.get_current_filepath()
        while not os.path.isfile(file_path):
            await sleep(0.01)
        r = LoadingTorrentFileResponse(
            file_path,
            piece_manager=self.pm,
            request=request,
        )
        self.resps.append(r)
        return r
