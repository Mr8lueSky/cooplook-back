from custom_responses import PieceManager, LoadingTorrentFileResponse
import abc
import libtorrent as lt
from pathlib import Path as FilePath
from uuid import UUID
from fastapi import Response
from fastapi.responses import FileResponse


class VideoSource(abc.ABC):
    def get_player_src(self, room_id: UUID) -> str:
        return f"/files/{room_id}"

    def start(self): ...

    def cancel(self): ...

    @abc.abstractmethod
    def get_video_response(self, request) -> Response: ...


class HttpLinkVideoSource(VideoSource):
    def __init__(self, link: str):
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
    SAVE_PATH = "torrents"

    def __init__(self, torrent_path: FilePath | str, file_index: int):
        self.ti = lt.torrent_info(torrent_path)
        self.session = lt.session()
        self.fi = file_index
        self.th = None
        self.pm: PieceManager | None = None
        self.resps = []

    def start(self):
        self.th = self.session.add_torrent({"ti": self.ti, "save_path": "torrents"})
        self.ti.map_file(self.fi, 0, 0)
        self.pm = PieceManager(self.session, self.th, self.ti, self.fi)

    def cancel(self):
        for r in self.resps:
            r.stop = True
        self.resps.clear()

    def get_video_response(self, request) -> Response:
        files = self.ti.files()
        r = LoadingTorrentFileResponse(
            files.file_path(self.fi, self.SAVE_PATH), piece_manager=self.pm
        )
        r.request = request
        self.resps.append(r)
        return r
