import asyncio
import os.path
from asyncio import sleep
from dataclasses import dataclass, field
from enum import Enum
from time import time
from traceback import format_exception
from uuid import UUID

from fastapi import FastAPI, Path, Form, WebSocket
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from starlette.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse

from custom_responses import LoadingFileResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"))

VIDEO_PATH = "low3.mp4"
MOE = 1


PLAY = "pl"
PAUSE = "pa"
PING = "pi"
SET_CT = "sc"
PEOPLE_COUNT = "pc"


class VideoStatus(str, Enum):
    PLAY = PLAY
    PAUSE = PAUSE

@dataclass
class RoomInfo:
    room_id: UUID
    video: str
    wss: dict[int, WebSocket] = field(default_factory=dict)
    _current_time: float = 0
    status: VideoStatus = VideoStatus.PAUSE
    last_change: float = field(default_factory=time)

    def for_temp(self):
        return {
            "room_id": self.room_id,
            "video": self.video
        }

    async def send_room(self, msg: str, except_ids: list[int] = None):
        except_ids = except_ids or []
        await asyncio.gather(
            *(ws.send_text(msg) for ws_id, ws in self.wss.items() if ws_id not in except_ids)
        )

    async def change_status(self, new_status: VideoStatus, except_ids: list[int] = None):
        if new_status == self.status:
            return
        if new_status == VideoStatus.PAUSE:
            self._current_time = self.current_time
        self.status = new_status
        self.last_change = time()
        await self.send_room(f"{new_status.value} {self.current_time}", except_ids)

    async def send_current_status(self, except_ids: list[int] = None):
        await self.send_room(f"{self.status.value} {self.current_time}")

    @property
    def current_time(self):
        if self.status == VideoStatus.PLAY:
            return self._current_time + time() - self.last_change
        return self._current_time

    async def set_current_time(self, new_time: float, except_ids: list[int] = None):
        self._current_time = new_time
        self.last_change = time()
        await self.send_room(f"{SET_CT} {self.current_time}", except_ids)

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

rooms = {
    UUID("75b762ca-37a9-11f0-92c9-00e93a0971c5"): RoomInfo(
        room_id=UUID("75b762ca-37a9-11f0-92c9-00e93a0971c5"),
        video=VIDEO_PATH
    )
}


env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)
ROOM_TEMPLATE = env.get_template("room.html")


async def file_iterator(path: str, actual_size: int, chunk_size: int = 64 * 1024):
    print("file iter start")
    curr_size = 0
    with open(path, "rb") as file:
        while curr_size < actual_size:
            while curr_size + chunk_size > os.path.getsize(path) != actual_size:
                await sleep(0.1)
            yield file.read(chunk_size)
            curr_size += chunk_size
    print("file iter stop")


@app.get("/file/{path}")
async def get_file(path: str):
    video_path = "/home/marblesky/Videos/" + path
    if os.path.isfile(video_path):
        # StreamingResponse
        # return StreamingResponse(file_iterator(video_path, 9360944), headers={"content-length": "9360944"})
        # return FileResponse(video_path)
        stat_result = os.stat(video_path)
        stat_result = list(stat_result)
        stat_result[6] = 9360944
        return LoadingFileResponse(video_path, stat_result=os.stat_result(stat_result), actual_size=9360944)
        # return FileResponse(video_path, stat_result=os.stat_result(stat_result))
    return "Not found"


@app.get('/rooms/{room_id}')
async def inside_room(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return HTMLResponse(env.get_template("room.html").render(
        **rooms[room_id].for_temp()
    ))


class SetToPlay(BaseModel):
    link: str


@app.post('/rooms/{room_id}')
async def set_to_play(link: str = Form(), room_id: UUID = Path()):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    print(f"Link is {link}")
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)




@app.websocket('/rooms/{room_id}/ws')
async def syncing(websocket: WebSocket, room_id: UUID = Path()):
    if room_id not in rooms:
        await websocket.close(reason="room doesn't exist")
    ws_id = len(rooms[room_id].wss)
    room = rooms[room_id]
    try:
        await room.initial(websocket, ws_id)

        while True:
            data = await websocket.receive_text()
            cmd, ts = data.split(' ')
            ts = float(ts)
            if cmd.startswith(PLAY) or cmd.startswith(PAUSE):
                await room.change_status(VideoStatus(cmd), except_ids=[ws_id])
            elif cmd.startswith(PING):
                if not(ts - MOE <= room.current_time <= ts + MOE):
                    await websocket.send_text(f"{SET_CT} {room.current_time}")
            elif cmd == SET_CT:
                await room.set_current_time(ts, except_ids=[ws_id])
            print("Rc:", ws_id, data)
    except Exception as exc:
        print("\n".join(format_exception(exc)))
        if ws_id in room.wss:
            room.wss.pop(ws_id)

@app.get('/')
async def index():
    return RedirectResponse("/rooms/75b762ca-37a9-11f0-92c9-00e93a0971c5", 303)
