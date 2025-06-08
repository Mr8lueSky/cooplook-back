import json
import logging
from typing import Annotated
from uuid import UUID, uuid1

import anyio
from fastapi import Depends, FastAPI, Form, Path, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import current_user, generate_token
from config import ENV, TORRENT_FILES_SAVE_PATH
from engine import async_session_maker, create_all, create_users
from exceptions import HTTPException
from models.room_model import RoomModel
from room_info import get_room, monitor_rooms
from schemas.room_schemas import (CreateRoomLinkSchema,
                                  CreateRoomTorrentSchema, GetRoomSchema,
                                  GetRoomWatchingSchema)
from schemas.user_schema import CreateUserSchema, GetUserSchema
from video_sources import HttpLinkVideoSource, TorrentVideoSource

app = FastAPI()
app.add_event_handler("startup", create_all)
app.add_event_handler("startup", monitor_rooms)
app.add_event_handler("startup", create_users)
app.mount("/static", StaticFiles(directory="static"))

logger = logging.getLogger(__name__)


@app.exception_handler(HTTPException)
def handle_http_json_exception(_: Request, exc: HTTPException):
    if exc.html:
        return HTMLResponse(
            env.get_template("exception.html").render(
                title=exc.__class__.__name__, error=exc.msg
            ),
            status_code=exc.status_code,
        )
    return JSONResponse({"detail": exc.msg}, exc.status_code)


@app.exception_handler(RequestValidationError)
def handle_validation_error(_: Request, exc: RequestValidationError):
    return HTMLResponse(
        env.get_template("exception.html").render(
            title=exc.__class__.__name__,
            error=f"Something bad happened. Pls don't cry.<br> Error: {exc.args}",
        ),
        status_code=422,
    )


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

    @app.get("/rooms/{room_id}/stats")
    async def get_stats(room_id: UUID):
        async with async_session_maker.begin() as session:
            room = await get_room(session, room_id)
            return JSONResponse(json.dumps(room, default=lambda o: str(o)))

    @app.get("/priorities/{room_id}")
    async def get_priorities(room_id: UUID):
        async with async_session_maker.begin() as session:
            r = await get_room(session, room_id)
            if not isinstance(r.video_source, TorrentVideoSource):
                return JSONResponse({"error": "Is not torrent"}, 422)
            if r.video_source.tm.th is None:
                return JSONResponse({"error": "In not initialized!"}, 422)
            return [
                (i, a)
                for i, a in enumerate(r.video_source.tm.th.get_piece_priorities())
            ]

    @app.get("/have/{piece_id}/{room_id}")
    async def have_piece(piece_id: int, room_id: UUID):
        async with async_session_maker.begin() as session:
            vs = (await get_room(session, room_id)).video_source
            if not isinstance(vs, TorrentVideoSource):
                return JSONResponse({"error": "not a torrent"}, 422)
            if not vs.tm or not vs.tm.th:
                return ""
            return vs.tm.th.have_piece(piece_id)


@app.post("/rooms/from_link")
async def create_room_from_link(
    room: Annotated[CreateRoomLinkSchema, Form()],
    _: GetUserSchema = Depends(current_user),
) -> GetRoomSchema:
    async with async_session_maker.begin() as session:
        r = await RoomModel.create(session, room.name, HttpLinkVideoSource, room.link)
        return GetRoomSchema.from_room_model(r)


@app.post("/rooms/from_torrent")
async def create_room_torrent(
    room: Annotated[CreateRoomTorrentSchema, Form()],
    _: GetUserSchema = Depends(current_user),
) -> GetRoomSchema:
    async with async_session_maker.begin() as session:
        torrent_fpth = TORRENT_FILES_SAVE_PATH / str(uuid1())
        async with await anyio.open_file(torrent_fpth, mode="wb") as file:
            await file.write(room.file_content)
        r = await RoomModel.create(
            session, room.name, TorrentVideoSource, torrent_fpth.as_posix()
        )
        return GetRoomSchema.from_room_model(r)


@app.get("/files/{room_id}")
async def get_video_file(
    room_id: UUID, request: Request, _: GetUserSchema = Depends(current_user)
) -> FileResponse:
    async with async_session_maker.begin() as session:
        room = await get_room(session, room_id)
    return await room.video_source.get_video_response(request)


@app.get("/rooms/{room_id}")
async def inside_room(
    room_id: UUID, _: GetUserSchema = Depends(current_user)
) -> HTMLResponse:
    async with async_session_maker.begin() as session:
        room = await get_room(session, room_id)
        return HTMLResponse(
            env.get_template("room.html").render(
                room=GetRoomWatchingSchema.from_room_info(room)
            )
        )


@app.get("/rooms/")
async def list_rooms(_: GetUserSchema = Depends(current_user)) -> HTMLResponse:
    async with async_session_maker.begin() as session:
        rooms = await RoomModel.get_all(session)
        return HTMLResponse(
            env.get_template("rooms.html").render(
                rooms=[GetRoomSchema.from_room_model(r) for r in rooms]
            )
        )


@app.get("/login/")
async def login_page():
    return HTMLResponse(env.get_template("login.html").render())


@app.post("/login/")
async def login(user: Annotated[CreateUserSchema, Form()]):
    async with async_session_maker.begin() as session:
        token = await generate_token(session, user.name, user.password)
        resp = RedirectResponse("/rooms/", 303)
        resp.set_cookie("token", token, httponly=True)
    return resp


@app.get("/user")
async def user(user: GetUserSchema = Depends(current_user)):
    return user


@app.post("/rooms/{room_id}")
async def set_to_play(
    link: str = Form(), room_id: UUID = Path(), _: GetUserSchema = Depends(current_user)
):
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


@app.websocket("/rooms/{room_id}/ws")
async def syncing(
    websocket: WebSocket,
    room_id: UUID = Path(),
    _: GetUserSchema = Depends(current_user),
):
    async with async_session_maker.begin() as session:
        room = await get_room(session, room_id)
    await room.handle_client(websocket)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie("token")
    return resp

@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse("/rooms/", 303)
