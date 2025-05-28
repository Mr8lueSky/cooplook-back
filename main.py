import abc
import asyncio
import json
import logging
import re
from asyncio import wait_for
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path as FilePath
from time import time
from traceback import format_exception
from uuid import UUID, uuid1

import libtorrent as lt
from fastapi import FastAPI, Path, Form, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response

from custom_responses import LoadingTorrentFileResponse, PieceManager

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"))

VIDEO_PATH = "low10.mp4"
MOE = 1

logger = logging.getLogger(__name__)
logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)

PLAY = "pl"
PAUSE = "pa"
SUSPEND = "sp"
UNSUSPEND = "up"
FORCE_UNSUSPEND = "fu"
PING = "pi"
SET_CT = "sc"
PEOPLE_COUNT = "pc"


class VideoStatus(str, Enum):
    PLAY = PLAY
    PAUSE = PAUSE
    SUSPEND = SUSPEND
    UNSUSPEND = UNSUSPEND


class VideoSource(abc.ABC):
    def get_player_src(self, room_id: UUID) -> str:
        return f"/files/{room_id}"

    async def start(self):
        ...

    @abc.abstractmethod
    def get_video_response(self) -> Response:
        ...


class HttpLinkVideoSource(VideoSource):
    def __init__(self, link: str):
        self.link = link

    def get_player_src(self, _: UUID) -> str:
        return self.link

    def get_video_response(self):
        raise AttributeError("Don't need to be implemented")


class FileVideoSource(VideoSource):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def get_video_response(self) -> Response:
        return FileResponse(self.file_path)


class TorrentVideoSource(VideoSource):
    SAVE_PATH = 'torrents'

    def __init__(self, torrent_path: FilePath | str, file_index: int):
        self.ti = lt.torrent_info(torrent_path)
        self.session = lt.session()
        self.fi = file_index
        self.th = None
        self.pm = None

    def start(self):
        self.th = self.session.add_torrent(
            {'ti': self.ti, 'save_path': 'torrents'})
        self.ti.map_file(self.fi, 0, 0)
        self.th.prioritize_pieces((i, 0) for i in range(self.ti.files().num_pieces()))
        for i in range(10):
            self.th.piece_priority(self.ti.map_file(self.fi, 0, 0).piece + i, 7)
        self.pm = PieceManager(self.session, self.th, self.ti, self.fi)

    def get_video_response(self) -> Response:
        # torrent_info: lt.torrent_info = None, torrent_handle: lt.torrent_handle,
        # file_index: int = -1, piece_manager=None,
        files = self.ti.files()
        return LoadingTorrentFileResponse(
            files.file_path(self.fi, self.SAVE_PATH),
            piece_manager=self.pm
        )


@dataclass
class RoomInfo:
    room_id: UUID
    video_source: VideoSource
    name: str = field(metadata=dict(validate=lambda d: 4 <= len(d) <= 32 and re.fullmatch(r"[a-zA-Z0-9]*", d)))
    wss: dict[int, WebSocket] = field(default_factory=dict)
    last_ws_id: int = 0
    _current_time: float = 0
    status: VideoStatus = VideoStatus.PAUSE
    last_change: float = field(default_factory=time)
    suspend_by: set[int] = field(default_factory=set)

    def for_temp(self):
        return {
            "room_id": self.room_id,
            "video": self.video_source.get_player_src(self.room_id),
            "room_name": self.name
        }

    async def send_room(self, msg: str, by: int = -1):
        logger.debug(f"Sn r {msg}, {by}")
        await asyncio.gather(
            *(ws.send_text(msg) for ws_id, ws in self.wss.items() if ws_id != by)
        )

    async def change_status(self, new_status: VideoStatus, by: int = -1):
        logger.info(f"Changing status from {self.status} to {new_status}")
        if new_status == self.status:
            return

        if new_status == VideoStatus.UNSUSPEND:
            if by in self.suspend_by:
                self.suspend_by.remove(by)
            if not self.suspend_by:
                return await self.change_status(VideoStatus.PLAY, by)

        if new_status == VideoStatus.SUSPEND:
            return
            self.suspend_by.add(by)

        if new_status == VideoStatus.PAUSE or new_status == VideoStatus.SUSPEND:
            self._current_time = self.current_time

        self.status = new_status
        self.last_change = time()
        await self.send_room(f"{new_status.value} {self.current_time}", by)

    async def send_current_status(self, by: int = -1):
        await self.send_room(f"{self.status.value} {self.current_time}", by)

    @property
    def current_time(self):
        if self.status == VideoStatus.PLAY:
            return self._current_time + time() - self.last_change
        return self._current_time

    async def set_current_time(self, new_time: float, by: int = None):
        logger.info(f"Set current time from {self._current_time} to {new_time}")
        self._current_time = new_time
        self.last_change = time()
        await self.send_room(f"{SET_CT} {self.current_time}", by)

    async def initial(self, ws: WebSocket, ws_id: int):
        await ws.accept()
        await ws.send_text(
            f"{SET_CT} {self.current_time}"
        )
        await ws.send_text(
            f"{PEOPLE_COUNT} {len(self.wss)}"
        )
        await self.send_current_status()
        self.wss[ws_id] = ws
        await self.send_room(f"{PEOPLE_COUNT} {len(self.wss)}")


random = False

if random:
    TORRENT_ROOM_UUID = uuid1()
    VIDEO_ROOM_UUID = uuid1()
else:
    TORRENT_ROOM_UUID = UUID("59afc00e-3b05-11f0-9332-00e93a0971c5")
    VIDEO_ROOM_UUID = UUID("7b3038c6-3b05-11f0-bfca-00e93a0971c5")

rooms = {
    TORRENT_ROOM_UUID: RoomInfo(
        room_id=TORRENT_ROOM_UUID,
        video_source=TorrentVideoSource("test.torrent", 1),
        name="From torrent"
    ),
    VIDEO_ROOM_UUID: RoomInfo(
        room_id=VIDEO_ROOM_UUID,
        video_source=FileVideoSource(
            'torrents/Kijin Gentoushou - AniLibria [WEBRip 1080p]/Kijin_Gentosho_[02]_[AniLibria]_[WEBRip_1080p].mkv'),
        name="From file"
    )
}

rooms[TORRENT_ROOM_UUID].video_source.start()
# rooms[VIDEO_ROOM_UUID].video_source.start()

env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)
ROOM_TEMPLATE = env.get_template("room.html")

i = 0


@app.get("/priorities/")
async def get_priorities():
    return [(i, a) for i, a in enumerate(rooms[TORRENT_ROOM_UUID].video_source.pm.th.get_piece_priorities())]


@app.get("/from_torrent")
def from_torrent():
    return HTMLResponse(f"""<video controls id=video width="640" height="480">
    <source src="/files/{TORRENT_ROOM_UUID}" type="video/mp4">
    Your browser does not support the video tag.
</video>""")


@app.get("/files/{room_id}")
async def get_video_file(room_id: UUID, request: Request):
    room = rooms.get(room_id)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    # global i
    # with open(f'headers/{i}', 'w') as file:
    #     json.dump(dict(request.headers), file)
    # i += 1
    return room.video_source.get_video_response()


@app.get('/rooms/{room_id}')
async def inside_room(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return HTMLResponse(env.get_template("room.html").render(
        **rooms[room_id].for_temp()
    ))


@app.get('/rooms/')
async def list_rooms():
    rooms_html = []
    for room_id, room_info in rooms.items():
        rooms_html.append(
            f'<a href="/rooms/{room_id}">{room_info.name}</a>'
        )
    return HTMLResponse(f"""{"<br>".join(rooms_html)}""")


@app.get('/rooms/{room_id}/stats')
async def inside_room(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return JSONResponse(json.dumps(rooms[room_id], default=lambda o: str(o)))


class SetToPlay(BaseModel):
    link: str


@app.post('/rooms/{room_id}')
async def set_to_play(link: str = Form(), room_id: UUID = Path()):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    logger.info(f"Link is {link}")
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


@app.websocket('/rooms/{room_id}/ws')
async def syncing(websocket: WebSocket, room_id: UUID = Path()):
    if room_id not in rooms:
        await websocket.close(reason="room doesn't exist")
    room = rooms[room_id]
    ws_id = room.last_ws_id
    room.last_ws_id += 1
    try:
        await room.initial(websocket, ws_id)
        logger.info(f"Client {ws_id} connected")
        while True:
            try:
                data = await wait_for(websocket.receive_text(), MOE)
                cmd, ts = data.split(' ')
                ts = float(ts)
                if cmd.startswith(PLAY) or cmd.startswith(PAUSE) or cmd == SUSPEND:
                    await room.change_status(VideoStatus(cmd), by=ws_id)
                elif cmd.startswith(PING):
                    if not (ts - MOE <= room.current_time <= ts + MOE):
                        await websocket.send_text(f"{SET_CT} {room.current_time}")
                elif cmd == SET_CT:
                    await room.set_current_time(ts, by=ws_id)
                elif cmd == FORCE_UNSUSPEND:
                    await room.set_current_time(min(0, room.current_time - 2), ws_id)
                    await room.change_status(VideoStatus.PLAY, ws_id)
                logger.debug(f"Rc: {ws_id}, {data}")
            except TimeoutError:
                if room.status != VideoStatus.PLAY:
                    continue
                logger.info(f"Timeout for {ws_id}")
                await room.change_status(VideoStatus.SUSPEND, ws_id)

    except Exception as exc:
        print("\n".join(format_exception(exc)))
        if ws_id in room.wss:
            room.wss.pop(ws_id)
        if ws_id in room.suspend_by:
            await room.change_status(VideoStatus.UNSUSPEND)
        await room.send_room(f"{PEOPLE_COUNT} {len(room.wss)}")
        await room.change_status(VideoStatus.PAUSE)


@app.get('/')
async def index():
    return RedirectResponse(f"/rooms/{str(TORRENT_ROOM_UUID)}", 303)
