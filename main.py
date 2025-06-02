import json
import logging
from uuid import UUID, uuid1

from fastapi import FastAPI, Form, Path, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from cmds import *
from room_info import RoomInfo
from video_sources import FileVideoSource, TorrentVideoSource

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"))

logger = logging.getLogger(__name__)


random = False

if random:
    TORRENT_ROOM_UUID = uuid1()
    VIDEO_ROOM_UUID = uuid1()
else:
    TORRENT_ROOM_UUID = UUID("59afc00e-3b05-11f0-9332-00e93a0971c5")
    VIDEO_ROOM_UUID = UUID("7b3038c6-3b05-11f0-bfca-00e93a0971c5")

torrent_vs = TorrentVideoSource("minecraft.torrent", 0)

rooms = {
    TORRENT_ROOM_UUID: RoomInfo(
        room_id=TORRENT_ROOM_UUID, video_source=torrent_vs, name="Room from torrent"
    ),
    VIDEO_ROOM_UUID: RoomInfo(
        room_id=VIDEO_ROOM_UUID,
        video_source=FileVideoSource("/home/marblesky/Videos/lazarus.mp4"),
        name="Room from file",
    ),
}

rooms[TORRENT_ROOM_UUID].video_source.start()

env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)
ROOM_TEMPLATE = env.get_template("room.html")


@app.get("/priorities/")
async def get_priorities():
    if torrent_vs.pm is None:
        return ""
    return [(i, a) for i, a in enumerate(torrent_vs.pm.th.get_piece_priorities())]


@app.get("/have/{piece_id}")
async def have_piece(piece_id: int):
    if not torrent_vs.pm:
        return ""
    return torrent_vs.pm.th.have_piece(piece_id)


@app.get("/from_torrent")
def from_torrent():
    return HTMLResponse(
        f"""<video controls preload=none id=video width="640" height="480">
    <source src="/files/{TORRENT_ROOM_UUID}" type="video/mp4">
    Your browser does not support the video tag.
</video>
<script>
let videoElem = document.getElementById("video")

videoElem.addEventListener("canplay", (event) => {{console.log("canplay")}} )
videoElem.addEventListener("waiting", (event) => {{console.log("waitingsolong")}} )
videoElem.addEventListener("playing", (event) => {{console.log("playing")}} )
</script>
"""
    )


@app.get("/files/{room_id}")
async def get_video_file(room_id: UUID, request: Request):
    room = rooms.get(room_id)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    return room.video_source.get_video_response(request)


@app.get("/rooms/{room_id}")
async def inside_room(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return HTMLResponse(
        env.get_template("room.html").render(**rooms[room_id].for_temp())
    )


@app.get("/rooms/")
async def list_rooms():
   return HTMLResponse(
           env.get_template("rooms.html").render(rooms=rooms.values())
           )

@app.get("/rooms/{room_id}/stats")
async def get_stats(room_id: UUID):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return JSONResponse(json.dumps(rooms[room_id], default=lambda o: str(o)))


class SetToPlay(BaseModel):
    link: str


@app.post("/rooms/{room_id}")
async def set_to_play(link: str = Form(), room_id: UUID = Path()):
    if room_id not in rooms:
        return HTMLResponse(f"Room {room_id} not found!", status_code=404)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


@app.websocket("/rooms/{room_id}/ws")
async def syncing(websocket: WebSocket, room_id: UUID = Path()):
    if room_id not in rooms:
        await websocket.close(reason="room doesn't exist")
    room = rooms[room_id]
    await room.handle_client(websocket)


@app.get("/")
async def index():
    return RedirectResponse(f"/rooms/{str(TORRENT_ROOM_UUID)}", 303)
