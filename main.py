import json
import logging
from uuid import UUID, uuid1

import anyio
from fastapi import (Body, Depends, FastAPI, Form, Path, Request, UploadFile,
                     WebSocket)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from starlette.responses import (HTMLResponse, JSONResponse,
                                 RedirectResponse)

from cmds import *
from config import ENV, TORRENT_FILES_SAVE_PATH
from engine import create_all, get_session
from models.room import RoomModel
from room_info import get_room
from validators import is_valid_torrent
from video_sources import (HttpLinkVideoSource,
                           TorrentVideoSource)
from engine import async_session_maker

app = FastAPI()
app.add_event_handler("startup", create_all)

app.mount("/static", StaticFiles(directory="static"))

logger = logging.getLogger(__name__)




env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)
ROOM_TEMPLATE = env.get_template("room.html")


if ENV == "DEV":
    random = False

    if random:
        TORRENT_ROOM_UUID = uuid1()
        VIDEO_ROOM_UUID = uuid1()
    else:
        TORRENT_ROOM_UUID = UUID("59afc00e-3b05-11f0-9332-00e93a0971c5")
        VIDEO_ROOM_UUID = UUID("7b3038c6-3b05-11f0-bfca-00e93a0971c5")

    @app.get("/priorities/{room_id}")
    async def get_priorities(room_id: UUID, session = Depends(get_session)):
        return [
            (i, a)
            for i, a in enumerate(
                (await get_room(session, room_id)).video_source.pm.th.get_piece_priorities()
            )
        ]

    @app.get("/have/{piece_id}/{room_id}")
    async def have_piece(piece_id: int, room_id: UUID, session = Depends(get_session)):
        vs = (await get_room(session, room_id)).video_source
        if not vs.pm:
            return ""
        return vs.pm.th.have_piece(piece_id)

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


class CreateRoomFromLinkModel(BaseModel):
    link: str
    name: str


@app.post("/rooms/from_link")
async def create_room_from_link(
    session=Depends(get_session), name: str = Form(), link: str = Form()
):
    r = await RoomModel.create(session, name, HttpLinkVideoSource, link)
    return JSONResponse({"room_id": str(r.room_id)})


class CreateRoomFromTorrent(BaseModel):
    name: str = Body()


@app.post("/rooms/from_torrent")
async def create_room_torrent(
    torrent_file: UploadFile, name: str = Form(), session=Depends(get_session)
):
    if torrent_file.size and torrent_file.size > 5 * 1024 * 1024:
        return JSONResponse({"error": "Too large"}, 422)
    torrent = await torrent_file.read()
    if not is_valid_torrent(torrent):
        return JSONResponse({"error": "Not a valid torrent"}, 422)
    torrent_fpth = TORRENT_FILES_SAVE_PATH / str(uuid1())
    async with await anyio.open_file(torrent_fpth, mode="wb") as file:
        await file.write(torrent)
    r = await RoomModel.create(
        session, name, TorrentVideoSource, torrent_fpth.as_posix()
    )
    vs = r.video_source
    vs.set_room_id(r.room_id)
    vs.start()
    return JSONResponse({"room_id": str(r.room_id)})


@app.get("/files/{room_id}")
async def get_video_file(room_id: UUID, request: Request):
    async with async_session_maker.begin() as session:
        room = await get_room(session, room_id)
    return room.video_source.get_video_response(request)


@app.get("/rooms/{room_id}")
async def inside_room(room_id: UUID, session=Depends(get_session)):
    room = await get_room(session, room_id)
    return HTMLResponse(env.get_template("room.html").render(**room.for_temp()))


@app.get("/rooms/")
async def list_rooms(session = Depends(get_session)):
    return HTMLResponse(env.get_template("rooms.html").render(rooms=await RoomModel.get_all(session)))


@app.get("/rooms/{room_id}/stats")
async def get_stats(room_id: UUID, session = Depends(get_session)):
    room = await get_room(session, room_id)
    return JSONResponse(json.dumps(room, default=lambda o: str(o)))


@app.post("/rooms/{room_id}")
async def set_to_play(link: str = Form(), room_id: UUID = Path()):
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


@app.websocket("/rooms/{room_id}/ws")
async def syncing(websocket: WebSocket, room_id: UUID = Path(), session = Depends(get_session)):
    room = await get_room(session, room_id)
    await room.handle_client(websocket)


@app.get("/")
async def index():
    return RedirectResponse("/rooms/", 303)
