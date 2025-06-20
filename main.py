import json
import logging
from collections import defaultdict
import os
from string import ascii_lowercase, ascii_uppercase
from typing import Annotated
from uuid import UUID, uuid1

import anyio
from fastapi import Depends, FastAPI, Form, Path, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import current_user, generate_token
from config import ENV, TORRENT_FILES_SAVE_PATH
from engine import async_session_maker, create_all, create_users
from exceptions import HTTPException
from models.room_model import RoomModel
from room_info import delete_room, get_room, monitor_rooms, retake_room
from schemas.room_schemas import (CreateRoomLinkSchema,
                                  CreateRoomTorrentSchema, GetRoomSchema,
                                  GetRoomWatchingSchema, UpdateSourceToLink,
                                  UpdateSourceToTorrentSchema)
from schemas.user_schema import GetUserSchema, LoginUserSchema
from templates import get_template_response
from video_sources import HttpLinkVideoSource, TorrentVideoSource

app = FastAPI()

app.add_event_handler("startup", create_all)
app.add_event_handler("startup", monitor_rooms)
app.add_event_handler("startup", create_users)

app.mount("/static", StaticFiles(directory="static"))

logger = logging.getLogger(__name__)

allowed_alert_table = defaultdict(lambda: ord("|"))

for char in ascii_lowercase + ascii_uppercase + " :-._[]":
    allowed_alert_table[ord(char)] = ord(char)


def format_exc_msg(msg: str):
    return msg.translate(allowed_alert_table).replace("|", "")


@app.exception_handler(HTTPException)
def handle_http_exception(r: Request, exc: HTTPException):
    if exc.html:
        resp = RedirectResponse(".", 303)
        try:
            exceptions = json.loads(r.cookies.get("exc", "[]"))
        except Exception:
            exceptions = []
        exceptions.append(format_exc_msg(exc.msg))
        resp.set_cookie("exc", json.dumps(exceptions))
        return resp
    return JSONResponse(
        {"detail": exc.msg.replace("<", "").replace(">", "")}, exc.status_code
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(r: Request, exc: RequestValidationError):
    resp = RedirectResponse(".", 303)
    try:
        exceptions = json.loads(r.cookies.get("exc", "[]"))
    except Exception:
        exceptions = []
    exceptions.extend(
        format_exc_msg(".".join(err["loc"]) + ": " + err["msg"]) for err in exc.errors()
    )
    resp.set_cookie("exc", json.dumps(exceptions))
    return resp


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
async def create_room_link(
    room: Annotated[CreateRoomLinkSchema, Form()],
    _: GetUserSchema = Depends(current_user),
) -> Response:
    async with async_session_maker.begin() as session:
        r = await RoomModel.create(
            session, room.name, HttpLinkVideoSource, room.video_link, room.img_link
        )
        return RedirectResponse(f"/rooms/{r.room_id}", 303)


@app.post("/rooms/from_torrent")
async def create_room_torrent(
    room: CreateRoomTorrentSchema = Form(),
    _: GetUserSchema = Depends(current_user),
) -> Response:
    torrent_fpth = TORRENT_FILES_SAVE_PATH / str(uuid1())
    os.makedirs(TORRENT_FILES_SAVE_PATH, exist_ok=True)
    async with await anyio.open_file(torrent_fpth, mode="wb") as file:
        await file.write(room.file_content)

    async with async_session_maker.begin() as session:
        r = await RoomModel.create(
            session,
            room.name,
            TorrentVideoSource,
            torrent_fpth.as_posix(),
            room.img_link,
        )

        return RedirectResponse(f"/rooms/{r.room_id}", 303)


@app.get("/files/{room_id}")
async def get_video_file(
    room_id: UUID, request: Request, _: GetUserSchema = Depends(current_user)
) -> FileResponse:
    async with async_session_maker.begin() as session:
        room = await get_room(session, room_id)
    return await room.video_source.get_video_response(request)


@app.delete("/rooms/{room_id}")
async def delete_room_end(room_id: UUID, _: GetUserSchema = Depends(current_user)):
    async with async_session_maker.begin() as session:
        await delete_room(session, room_id)
    return RedirectResponse("/rooms/", 303)


@app.post("/rooms/{room_id}/vs_torrent")
async def update_source_to_torrent(
    room_id: UUID,
    room: UpdateSourceToTorrentSchema = Form(),
    _: GetUserSchema = Depends(current_user),
):
    torrent_fpth = None
    if room.torrent_file is not None and room.file_content is not None:
        torrent_fpth = TORRENT_FILES_SAVE_PATH / str(uuid1())
        async with await anyio.open_file(torrent_fpth, mode="wb") as file:
            await file.write(room.file_content)
        torrent_fpth = torrent_fpth.as_posix()

    async with async_session_maker.begin() as session:
        await RoomModel.update(
            session,
            room_id,
            last_watch_ts=0,
            last_file_ind=0,
            vs_cls=TorrentVideoSource,
            name=room.name or None,
            img_link=room.img_link or None,
            video_source_data=torrent_fpth or None,
        )
        await retake_room(session, room_id)
        return RedirectResponse(f"/rooms/{room_id}", 303)


@app.post("/rooms/{room_id}/vs_link")
async def update_source_to_link(
    room_id: UUID,
    room: UpdateSourceToLink = Form(),
    _: GetUserSchema = Depends(current_user),
) -> Response:
    async with async_session_maker.begin() as session:
        await RoomModel.update(
            session,
            room_id,
            last_watch_ts=0,
            last_file_ind=0,
            vs_cls=HttpLinkVideoSource,
            name=room.name or None,
            img_link=room.img_link or None,
            video_source_data=room.video_link or None,
        )
        await retake_room(session, room_id)
        return RedirectResponse(f"/rooms/{room_id}", 303)


@app.get("/rooms/{room_id}")
async def inside_room(
    room_id: UUID,
    _: GetUserSchema = Depends(current_user),
) -> HTMLResponse:
    async with async_session_maker.begin() as session:
        room_info = await get_room(session, room_id)
        return get_template_response(
            "room",
            {
                "room": GetRoomWatchingSchema.model_validate(
                    room_info, from_attributes=True
                )
            },
        )


async def list_rooms(exceptions: list[HTTPException] | None = None):
    exceptions = exceptions or []
    async with async_session_maker.begin() as session:
        rooms = await RoomModel.get_all(session)
        return get_template_response(
            "rooms",
            {
                "rooms": [
                    GetRoomSchema.model_validate(r, from_attributes=True) for r in rooms
                ]
            },
            exceptions,
        )


@app.get("/rooms/")
async def list_rooms_end(
    _: GetUserSchema = Depends(current_user),
) -> HTMLResponse:
    return await list_rooms()


@app.get("/login")
async def login_page():
    return get_template_response("login")


@app.post("/login")
async def login(user: Annotated[LoginUserSchema, Form()]):
    async with async_session_maker.begin() as session:
        try:
            token = await generate_token(session, user.name, user.password)
            resp = RedirectResponse("/rooms/", 303)
            resp.set_cookie("token", token, httponly=True)
        except (HTTPException, RequestValidationError):
            raise HTTPException("Incorrent username or password!")
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
