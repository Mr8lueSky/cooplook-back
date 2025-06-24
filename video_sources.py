import abc
import os
from asyncio import sleep
from pathlib import Path
from typing import override
from uuid import UUID, uuid1

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

import config
from custom_responses import LoadingTorrentFileResponse, TorrentManager
from models.room_model import RoomModel, VideoSourcesEnum


class VideoSource(abc.ABC):
    data_field: str
    enum: VideoSourcesEnum

    def __init__(self, data: str, file_index: int) -> None:
        super().__init__()
        self.curr_fi: int = file_index

    @abc.abstractmethod
    def get_available_files(self) -> list[tuple[int, str]]: ...

    @abc.abstractmethod
    def set_file_index(self, fi: int) -> bool: ...

    def start(self): ...

    @abc.abstractmethod
    def cancel_current_requests(self): ...

    def cleanup(self):
        self.cancel_current_requests()

    @classmethod
    def from_model(cls, model: RoomModel) -> "VideoSource":
        cls = enum_to_source.get(model.video_source)
        if cls is None:
            raise RuntimeError(f"Unknown source: {cls}")
        return cls(model.video_source_data, model.last_file_ind)

    def update_model(self, model: RoomModel) -> RoomModel:
        model.video_source = self.enum
        model.video_source_data = getattr(self, self.data_field)
        return model

    @abc.abstractmethod
    async def get_video_response(self, request: Request) -> Response: ...


class HttpLinkVideoSource(VideoSource):
    data_field: str = "link"
    enum: VideoSourcesEnum = VideoSourcesEnum.link

    def __init__(self, link: str, file_index: int) -> None:
        super().__init__(link, file_index)
        self.link: str = link

    @override
    def get_available_files(self) -> list[tuple[int, str]]:
        return [(0, self.link)]

    @override
    def set_file_index(self, fi: int) -> bool:
        return False

    @override
    def cancel_current_requests(self): ...

    @override
    async def get_video_response(self, request: Request) -> RedirectResponse:
        return RedirectResponse(self.link, 303)


class TorrentVideoSource(VideoSource):
    SAVE_PATH: Path = config.TORRENT_SAVE_PATH
    data_field: str = "torrent"
    enum: VideoSourcesEnum = VideoSourcesEnum.torrent

    def __init__(
        self,
        torrent: str,
        file_index: int,
    ):
        super().__init__("", file_index)
        self.folder_id: UUID = uuid1()
        os.makedirs(self.save_path, exist_ok=True)
        self.torrent: str = torrent
        self.tm: TorrentManager = TorrentManager(
            self.torrent, self.curr_fi, self.save_path
        )
        self.resps: list[LoadingTorrentFileResponse] = []

    @property
    def save_path(self) -> str:
        return str(self.SAVE_PATH / str(self.folder_id))

    @override
    def set_file_index(self, fi: int) -> bool:
        """Returns is file changed or not"""
        if fi == self.curr_fi:
            return False
        self.tm.set_file_index(fi)
        self.curr_fi: int = fi
        self.tm.initiate_torrent_download()
        return True

    @override
    def cleanup(self):
        super().cleanup()
        self.tm.cleanup()

    @override
    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.tm.initiate_torrent_download()

    @override
    def cancel_current_requests(self):
        for r in self.resps:
            r.cancel()
        self.resps.clear()

    @override
    def get_available_files(self) -> list[tuple[int, str]]:
        return self.tm.get_all_filenames()

    @override
    async def get_video_response(self, request: Request) -> LoadingTorrentFileResponse:
        file_path = self.tm.get_current_filepath()
        while not os.path.isfile(file_path):
            await sleep(0)
        r = LoadingTorrentFileResponse(
            file_path,
            piece_manager=self.tm,
            request=request,
        )
        self.resps.append(r)
        return r


enum_to_source: dict[VideoSourcesEnum, type[VideoSource]] = {
    VideoSourcesEnum.torrent: TorrentVideoSource,
    VideoSourcesEnum.link: HttpLinkVideoSource,
}
