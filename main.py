from datetime import datetime
import json
import logging
import os
from string import ascii_lowercase, ascii_uppercase, digits
from traceback import format_exc
from typing import Annotated
from uuid import UUID, uuid1

import anyio
from fastapi import (
    Depends,
    FastAPI,
    Form,
    Path,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import current_user, generate_token
from config import ACCESS_TOKEN_EXPIRE, TORRENT_FILES_SAVE_PATH
from connections import Connection
from engine import async_session_maker, create_all, create_users
from exceptions import HTTPException
from models.room_model import RoomModel
from room import RoomStorage, monitor_rooms
from schemas.room_schemas import (
    CreateRoomLinkSchema,
    CreateRoomTorrentSchema,
    GetRoomSchema,
    GetRoomWatchingSchema,
    UpdateSourceToLink,
    UpdateSourceToTorrentSchema,
)
from schemas.user_schema import GetUserSchema, LoginUserSchema
from templates import get_template_response
from video_sources import HttpLinkVideoSource, TorrentVideoSource

app = FastAPI()

app.add_event_handler("startup", create_all)
app.add_event_handler("startup", monitor_rooms)
app.add_event_handler("startup", create_users)
app.add_event_handler("shutdown", RoomStorage.full_cleanup)

app.mount("/static", StaticFiles(directory="static"))

logger = logging.getLogger(__name__)

allowed_alert_table: dict[int, int] = {}

for char in ascii_lowercase + ascii_uppercase + " :-._[]" + digits:
    allowed_alert_table[ord(char)] = ord("|")


def format_exc_msg(msg: str) -> str:
    return msg.translate(allowed_alert_table).replace("|", "")


@app.exception_handler(HTTPException)
def handle_http_exception(r: Request, exc: HTTPException):
    if exc.html:
        resp = RedirectResponse(".", 303)
        exceptions: list[str] = []
        try:
            exceptions = json.loads(r.cookies.get("exc", "[]"))
        except Exception:
            ...
        exceptions.append(format_exc_msg(exc.msg))
        resp.set_cookie("exc", json.dumps(exceptions))
        return resp
    return JSONResponse(
        {"detail": exc.msg.replace("<", "").replace(">", "")}, exc.status_code
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(r: Request, exc: RequestValidationError):
    resp = RedirectResponse(".", 303)
    exceptions: list[str] = []
    try:
        exceptions = json.loads(r.cookies.get("exc", "[]"))
    except Exception:
        ...
    exceptions.extend(
        format_exc_msg(".".join(err["loc"]) + ": " + err["msg"]) for err in exc.errors()
    )
    resp.set_cookie("exc", json.dumps(exceptions))
    return resp


@app.post("/rooms/from_link")
async def create_room_link(
    room: Annotated[CreateRoomLinkSchema, Form()],
    _: GetUserSchema = Depends(current_user),
) -> Response:
    async with async_session_maker.begin() as session:
        r = await RoomModel.create(
            session, room.name, HttpLinkVideoSource.enum, room.video_link, room.img_link
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
            TorrentVideoSource.enum,
            torrent_fpth.as_posix(),
            room.img_link,
        )

        return RedirectResponse(f"/rooms/{r.room_id}", 303)


@app.get("/files/{room_id}/{fi}")
async def get_video_file(
    room_id: UUID, fi: int, request: Request, _: GetUserSchema = Depends(current_user)
) -> Response:
    async with async_session_maker.begin() as session:
        room = await RoomStorage.get_room(session, room_id)
    return await room.video_source.get_video_response(request)


@app.delete("/rooms/{room_id}")
async def delete_room_end(room_id: UUID, _: GetUserSchema = Depends(current_user)):
    async with async_session_maker.begin() as session:
        await RoomStorage.delete_room(session, room_id)
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
            vs_enum=TorrentVideoSource.enum,
            name=room.name or None,
            img_link=room.img_link or None,
            video_source_data=torrent_fpth or None,
        )
        await RoomStorage.load_room(session, room_id, ignore_if_loaded=False)
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
            vs_enum=HttpLinkVideoSource.enum,
            name=room.name or None,
            img_link=room.img_link or None,
            video_source_data=room.video_link or None,
        )
        await RoomStorage.load_room(session, room_id, ignore_if_loaded=False)
        return RedirectResponse(f"/rooms/{room_id}", 303)


@app.get("/rooms/{room_id}")
async def inside_room(
    room_id: UUID,
    _: GetUserSchema = Depends(current_user),
) -> HTMLResponse:
    async with async_session_maker.begin() as session:
        room = await RoomStorage.get_room(session, room_id)
        return get_template_response(
            "room",
            {"room": GetRoomWatchingSchema.model_validate(room, from_attributes=True)},
        )


@app.get("/rooms/")
async def list_rooms_end(
    _: GetUserSchema = Depends(current_user),
) -> HTMLResponse:
    async with async_session_maker.begin() as session:
        rooms = await RoomModel.get_all(session)
        room_models = [
            GetRoomSchema.model_validate(r, from_attributes=True) for r in rooms
        ]
    return get_template_response(
        "rooms",
        {"rooms": room_models},
    )


@app.get("/login")
async def login_page():
    return get_template_response("login")


@app.post("/login")
async def login(user: Annotated[LoginUserSchema, Form()]):
    async with async_session_maker.begin() as session:
        try:
            token = await generate_token(session, user.name, user.password)
            resp = RedirectResponse("/rooms/", 303)
            now = datetime.now()
            expires = int((now + ACCESS_TOKEN_EXPIRE).timestamp())
            resp.set_cookie(
                "token",
                token,
                httponly=True,
                expires=expires,
            )
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
        room = await RoomStorage.get_room(session, room_id)
    conn = Connection(websocket)
    conn_id = await room.add_connection(conn)
    while True:  # TODO: while app is working
        try:
            msg = await websocket.receive_text()
            logger.debug(f"Recieved {msg} from {conn_id}")
            await room.handle_cmd_str(msg, conn_id)
            async with async_session_maker.begin() as session:
                await RoomStorage.save_room(session, room_id)
        except WebSocketDisconnect:
            logger.error(f"{conn_id} disconnected!")
            break
        except RuntimeError:
            break
        except Exception as exc:
            logger.error(
                f"Got an error from {conn_id}: {type(exc)} {exc}\n{format_exc()}"
            )
    await room.remove_connection(conn_id)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie("token")
    return resp


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse("/rooms/", 303)
