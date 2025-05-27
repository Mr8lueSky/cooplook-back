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
from uuid import UUID

import libtorrent as lt
from fastapi import FastAPI, Path, Form, WebSocket
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response

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
    def __init__(self, torrent_path: FilePath, file_index: int):
        self.ti = lt.torrent_info(torrent_path)
        self.session = lt.session()
        self.file_index = file_index
        self.th = None

    def start(self):
        self.th = self.session.add_torrent(
            {'ti': self.ti, 'save_path': 'torrents'})
        total_piece_count = self.ti.files.num_pieces()
        self.th.prioritize_pieces((i, 0) for i in range(total_piece_count))
        self.th.prioritize_pieces((i, 7) for i in range(max(10, total_piece_count)))

    def get_video_response(self) -> Response:
        return FileResponse(self.file_path)


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


rooms = {
    UUID("75b762ca-37a9-11f0-92c9-00e93a0971c5"): RoomInfo(
        room_id=UUID("75b762ca-37a9-11f0-92c9-00e93a0971c5"),
        video_source=FileVideoSource("/home/marblesky/Videos/lazarus.mp4"),
        name="First"
    )
}

# rooms[UUID("75b762ca-37a9-11f0-92c9-00e93a0971c5")].video_source.start()

env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)
ROOM_TEMPLATE = env.get_template("room.html")


@app.get("/files/{room_id}")
async def get_video_file(room_id: UUID):
    room = rooms.get(room_id)
    if room is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return room.video_source.get_video_response()


@app.get('/rooms/{room_id}')
async def inside_room(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return HTMLResponse(env.get_template("room.html").render(
        **rooms[room_id].for_temp()
    ))


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
    return RedirectResponse("/rooms/75b762ca-37a9-11f0-92c9-00e93a0971c5", 303)
