import abc
import os
from asyncio import sleep
from pathlib import Path
from uuid import UUID

from fastapi.responses import FileResponse

import config
from custom_responses import LoadingTorrentFileResponse, TorrentManager

class VideoSource(abc.ABC):
    def __init__(self, _: str, file_index: int, room_id: UUID) -> None:
        super().__init__()
        self.room_id: UUID | None = room_id
        self.curr_fi = file_index

    def get_player_src(self) -> str:
        return f"/files/{self.room_id}"

    @abc.abstractmethod
    def get_available_files(self) -> list[tuple[int, str]]: ...

    @abc.abstractmethod
    def set_current_fi(self, fi: int) -> bool: ...

    def start(self): ...
    
    def cleanup(self): ...

    @abc.abstractmethod
    def cancel_current_requests(self): ...

    @abc.abstractmethod
    async def get_video_response(self, request) -> FileResponse: ...


class HttpLinkVideoSource(VideoSource):
    def __init__(self, link: str, _: int, room_id: UUID):
        super().__init__("", 0, room_id)
        self.link = link

    def get_player_src(self, *_, **__) -> str:
        return self.link

    def get_available_files(self) -> list[tuple[int, str]]:
        return [(0, self.link)]

    def set_current_fi(self, fi: int) -> bool:
        return False

    def cancel_current_requests(self): ...

    def get_video_response(self, request):
        raise AttributeError("Don't need to be implemented")


class TorrentVideoSource(VideoSource):
    SAVE_PATH: Path = config.TORRENT_SAVE_PATH

    def __init__(self, torrent: bytes | str, file_index: int, room_id: UUID):
        super().__init__("", file_index, room_id)
        self.torrent = torrent
        self.tm = TorrentManager(self.torrent, self.curr_fi, self.save_path)
        self.resps: list[LoadingTorrentFileResponse] = []
        os.makedirs(self.SAVE_PATH, exist_ok=True)

    @property
    def save_path(self) -> str:
        if self.room_id is None:
            raise AttributeError("Room id is not set!")
        return str(self.SAVE_PATH / str(self.room_id))

    def set_current_fi(self, fi: int) -> bool:
        """Returns is file changed or not"""
        if fi == self.curr_fi:
            return False
        self.tm.set_new_fi(fi)
        self.curr_fi = fi
        self.tm.initiate_torrent_download()
        return True
    
    def cleanup(self):
        self.tm.cleanup()

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.tm.initiate_torrent_download()

    def cancel_current_requests(self):
        for r in self.resps:
            r.cancel()
        self.resps.clear()

    def get_available_files(self) -> list[tuple[int, str]]:
        return self.tm.get_all_filenames()

    async def get_video_response(self, request) -> LoadingTorrentFileResponse:
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


