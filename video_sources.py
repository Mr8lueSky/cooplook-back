import os
from pathlib import Path
import config
from custom_responses import PieceManager, LoadingTorrentFileResponse
import abc
import libtorrent as lt
from validators import torrent_type
from uuid import UUID
from fastapi import Response
from fastapi.responses import FileResponse


class VideoSource(abc.ABC):
    fi = 0
    def __init__(self, _: str, __: int) -> None:
        super().__init__()
        self.room_id: UUID | None = None

    def get_player_src(self) -> str:
        return f"/files/{self.room_id}"

    def set_room_id(self, room_id: UUID):
        self.room_id = room_id

    def start(self): ...

    def cancel(self): ...

    @abc.abstractmethod
    def get_video_response(self, request) -> Response: ...


class HttpLinkVideoSource(VideoSource):
    def __init__(self, link: str, _: int = 0):
        self.link = link

    def get_player_src(self, *_, **__) -> str:
        return self.link

    def get_video_response(self, request):
        raise AttributeError("Don't need to be implemented")


class FileVideoSource(VideoSource):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def get_video_response(self, request) -> Response:
        return FileResponse(self.file_path)


class TorrentVideoSource(VideoSource):
    SAVE_PATH: Path = config.TORRENT_SAVE_PATH

    def __init__(self, torrent: torrent_type, file_index: int):
        self.ti = lt.torrent_info(torrent)
        self.session = lt.session()
        self.fi = file_index
        self.th = None
        self.pm: PieceManager | None = None
        self.resps: list[LoadingTorrentFileResponse] = []

    @property
    def save_path(self):
        if self.room_id is None:
            raise AttributeError("Room id is not set!")
        return str(self.SAVE_PATH / str(self.room_id))

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.th = self.session.add_torrent({"ti": self.ti, "save_path": self.save_path})
        self.pm = PieceManager(self.session, self.th, self.ti, self.fi)
        self.pm.initiate_torrent_download()

    def cancel(self):
        for r in self.resps:
            r.cancel()
        self.resps.clear()

    def get_video_response(self, request) -> Response:
        files = self.ti.files()
        r = LoadingTorrentFileResponse(
            files.file_path(self.fi, self.save_path),
            piece_manager=self.pm,
            request=request,
        )
        self.resps.append(r)
        return r
