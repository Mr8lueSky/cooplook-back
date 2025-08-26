import socket
from traceback import format_exc
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Path,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from starlette import status

from lib.auth import current_user
from lib.connections import Connection
from lib.engine import async_session_maker
from lib.logger import create_logger
from models.room_model import RoomModel
from lib.room import RoomStorage
from schemas.room_schemas import (
    CreateRoomLinkSchema,
    CreateRoomTorrentSchema,
    GetRoomSchema,
    GetRoomWatchingSchema,
    UpdateRoomLinkSchema,
    UpdateRoomTorrentSchema,
)
from schemas.user_schemas import GetUserSchema
from services.room_service import RoomService

rooms_router = APIRouter()
logger = create_logger("rooms-ws")


@rooms_router.post("/link", status_code=status.HTTP_201_CREATED)
async def create_room_link(
    room: CreateRoomLinkSchema = Form(),  # pyright: ignore[reportCallInDefaultInitializer]
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> GetRoomSchema:
    async with async_session_maker.begin() as session:
        new_room = await RoomService.create_room(session, room)
    return GetRoomSchema.model_validate(new_room, from_attributes=True)


@rooms_router.post("/torrent", status_code=status.HTTP_201_CREATED)
async def create_room_torrent(
    room: CreateRoomTorrentSchema = Form(),  # pyright: ignore[reportCallInDefaultInitializer]
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> GetRoomSchema:
    async with async_session_maker.begin() as session:
        new_room = await RoomService.create_room(session, room)
    return GetRoomSchema.model_validate(new_room, from_attributes=True)


@rooms_router.put("/{room_id}/torrent")
async def update_room_to_torrent(
    room_id: UUID,
    room_data: UpdateRoomTorrentSchema = Form(),  # pyright: ignore[reportCallInDefaultInitializer]
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
):
    async with async_session_maker.begin() as session:
        await RoomService.update_room(session, room_id, room_data)


@rooms_router.put("/{room_id}/link")
async def update_room_to_link(
    room_id: UUID,
    room_data: UpdateRoomLinkSchema = Form(),  # pyright: ignore[reportCallInDefaultInitializer]
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
):
    async with async_session_maker.begin() as session:
        await RoomService.update_room(session, room_id, room_data)


@rooms_router.get("/files/{room_id}/{fi}")
async def get_video_file(
    room_id: UUID,
    fi: int,  # pyright: ignore[reportUnusedParameter]
    request: Request,
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Response:
    async with async_session_maker.begin() as session:
        room = await RoomStorage.get_room(session, room_id)
    return await room.video_source.get_video_response(request)


@rooms_router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_end(
    room_id: UUID,
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
):
    async with async_session_maker.begin() as session:
        await RoomStorage.delete_room(session, room_id)


@rooms_router.get("/{room_id}")
async def inside_room(
    room_id: UUID,
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> GetRoomWatchingSchema:
    async with async_session_maker.begin() as session:
        room = await RoomStorage.get_room(session, room_id)
    return GetRoomWatchingSchema.model_validate(room, from_attributes=True)


@rooms_router.get("")
async def list_rooms(
    _: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> list[GetRoomSchema]:
    async with async_session_maker.begin() as session:
        rooms = await RoomModel.get_all(session)
        return [
            GetRoomSchema.model_validate(
                r,
                from_attributes=True,
            )
            for r in rooms
        ]


@rooms_router.websocket("/{room_id}/ws")
async def syncing(
    websocket: WebSocket,
    room_id: UUID = Path(),  # pyright: ignore[reportCallInDefaultInitializer]
    current_user: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
):
    async with async_session_maker.begin() as session:
        room = await RoomStorage.get_room(session, room_id)
    conn = Connection(websocket)
    room_user = await room.add_connection(conn, current_user)
    while True:  # TODO: while app is working
        try:
            msg = await conn.recieve()
            logger.debug(f"Recieved {msg} from {room_user.conn_id}")
            await room.handle_cmd_str(msg, room_user)
            async with async_session_maker.begin() as session:
                await RoomStorage.save_room(session, room_id)
        except WebSocketDisconnect:
            logger.debug(f"{room_user.conn_id} disconnected!")
            break
        except RuntimeError as exc:
            logger.error(f"{room_user.conn_id}: {exc}! Disconnecting.")
            break
        except socket.error as exc:
            logger.error(f"{room_user.conn_id}: {exc}! Disconnecting.")
            break
        except Exception as exc:
            logger.error(
                f"Got an error from {room_user.conn_id}: {type(exc)} {exc}\n{format_exc()}"
            )
            break
    await room.remove_connection(room_user.conn_id)
