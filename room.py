import asyncio
import time
from asyncio import Lock
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from commands.command_handlers import (CommandsGroupHandler,
                                       StatusChangeCommandsHandler)
from commands.server_commands import FileChangeCommand, ServerCommand
from config import ROOM_INACTIVITY_PERIOD
from connections import Connection, ConnectionsManager
from exceptions import NotFound
from logger import Logging, create_logger
from models.room_model import RoomModel
from video_sources import VideoSource
from video_status.status_storage import StatusStorage
from video_status.video_statuses import PauseStatus, SuspendStatus, VideoStatus

monitor_logger = create_logger("RoomMonitor")


class RoomStateHandler(Logging):
    def __init__(
        self,
        status_storage: StatusStorage,
        cmd_handler: CommandsGroupHandler,
        conn_manager: ConnectionsManager,
    ) -> None:
        self.status_storage: StatusStorage = status_storage
        self.cmd_handler: CommandsGroupHandler = cmd_handler
        self.conn_manager: ConnectionsManager = conn_manager
        self.status_change_lock: Lock = Lock()

    def update_model(self, model: RoomModel):
        _ = self.status_storage.update_model(model)

    async def send_status_update(self):
        await self.conn_manager.send_room(self.status_storage.to_server_command())

    async def handle_cmd_str(self, cmd_str: str, by: int):
        async with self.status_change_lock:
            self.cmd_handler.handle_str_cmd(cmd_str, by)
            await self.send_status_update()

    async def send_cmd(self, cmd: ServerCommand, exclude_id: list[int] | None = None):
        exclude_id = exclude_id or []
        await self.conn_manager.send_room(cmd, exclude_id)

    def set_status(self, new_status: VideoStatus):
        self.status_storage.set_status(new_status)

    def set_status_from_current(self, new_status: type[VideoStatus]):
        _ = self.status_storage.from_current(new_status)

    async def add_connection(self, conn: Connection):
        conn_id = await self.conn_manager.add_connection(conn)
        suspend = SuspendStatus.from_status(self.status_storage.status).add_suspend_by(
            conn_id
        )
        suspend.change_to = PauseStatus
        self.status_storage.set_status(suspend)
        await self.send_status_update()
        return conn_id

    async def send_change_file(self):
        await self.conn_manager.send_room(
            FileChangeCommand(self.status_storage.current_file_ind)
        )

    async def remove_connection(self, conn_id: int):
        self.conn_manager.remove_connection(conn_id)
        curr_status = self.status_storage.status
        if isinstance(curr_status, SuspendStatus):
            _ = curr_status.remove_suspend_by(conn_id)
            if curr_status.should_unsuspend():
                _ = self.status_storage.from_current(PauseStatus)
        else:
            _ = self.status_storage.from_current(PauseStatus)
        await self.send_status_update()

    async def cleanup(self): ...

    @property
    def current_status(self) -> VideoStatus:
        return self.status_storage.status

    @property
    def people_inside(self):
        return self.conn_manager.conn_count()


class Room:
    def __init__(
        self,
        room_id: UUID,
        name: str,
        img_link: str,
        status_storage: StatusStorage,
        video_source: VideoSource,
    ):
        self.room_id: UUID = room_id
        self.name: str = name
        self.img_link: str = img_link
        self.video_source: VideoSource = video_source
        cmd_handler = CommandsGroupHandler(
            (StatusChangeCommandsHandler(status_storage),)
        )
        conn_manager = ConnectionsManager()
        self.room_state_handler: RoomStateHandler = RoomStateHandler(
            status_storage, cmd_handler, conn_manager
        )
        self.last_leave: float = time.time()

    @classmethod
    def from_model(cls, model: RoomModel) -> "Room":
        return cls(
            room_id=model.room_id,
            name=model.name,
            img_link=model.img_link,
            status_storage=StatusStorage.from_model(model),
            video_source=VideoSource.from_model(model),
        )

    def update_model(self, model: RoomModel):
        model.name = self.name
        model.img_link = self.img_link
        _ = self.room_state_handler.update_model(model)
        _ = self.video_source.update_model(model)

    async def add_connection(self, conn: Connection) -> int:
        conn_id = await self.room_state_handler.add_connection(conn)
        return conn_id

    async def remove_connection(self, conn_id: int):
        await self.room_state_handler.remove_connection(conn_id)
        self.last_leave = time.time()

    async def handle_cmd_str(self, cmd_str: str, by: int):
        await self.room_state_handler.handle_cmd_str(cmd_str, by)
        status = self.room_state_handler.current_status
        if self.video_source.set_file_index(status.current_file_ind):
            await self.room_state_handler.send_change_file()

    async def cleanup(self):
        self.video_source.cleanup()
        await self.room_state_handler.cleanup()

    @property
    def files(self):
        return self.video_source.get_available_files()

    @property
    def curr_fi(self):
        return self.video_source.curr_fi

    @property
    def people_inside(self):
        return self.room_state_handler.people_inside

    @property
    def video(self):
        return f"/files/{self.room_id}/{self.curr_fi}"


room_st_logger = create_logger("RoomStorage")


class RoomStorage:
    lock: Lock = Lock()
    loaded_rooms: dict[UUID, Room] = {}

    @classmethod
    async def load_room(
        cls, session: AsyncSession, room_id: UUID, ignore_if_loaded: bool = True
    ):
        async with cls.lock:
            if room_id in cls.loaded_rooms and ignore_if_loaded:
                return
            room = await RoomModel.get_room_id(session, room_id)
            cls.loaded_rooms[room_id] = Room.from_model(room)
            cls.loaded_rooms[room_id].video_source.start()

    @classmethod
    async def unload_room(cls, room_id: UUID):
        room_st_logger.debug(f"Unloading room {room_id}")
        room = cls.loaded_rooms.pop(room_id)
        await room.cleanup()

    @classmethod
    async def get_room(cls, session: AsyncSession, room_id: UUID) -> Room:
        await cls.load_room(session, room_id)
        room = cls.loaded_rooms.get(room_id)
        if room is None:
            raise NotFound("Room not found!")
        return room

    @classmethod
    def is_room_loaded(cls, room_id: UUID) -> bool:
        return room_id in cls.loaded_rooms

    @classmethod
    async def delete_room(cls, session: AsyncSession, room_id: UUID):
        room_st_logger.debug(f"Deleting room {room_id}")
        if cls.is_room_loaded(room_id):
            room = await cls.get_room(session, room_id)
            await room.cleanup()

    @classmethod
    async def save_room(cls, session: AsyncSession, room_id: UUID):
        room_model = await RoomModel.get_room_id(session, room_id)
        (await cls.get_room(session, room_id)).update_model(room_model)

    @classmethod
    async def full_cleanup(cls):
        room_st_logger.debug("Cleaning up all rooms")
        _ = await asyncio.gather(
            *(cls.unload_room(room_id) for room_id in cls.loaded_rooms.keys())
        )

    @classmethod
    async def remove_inactive(cls):
        room_st_logger.debug("Cleaning up inactive rooms")
        _ = await asyncio.gather(
            *(
                cls.unload_room(room_id)
                for room_id, room in cls.loaded_rooms.items()
                if not room.people_inside
                and time.time() - room.last_leave >= ROOM_INACTIVITY_PERIOD
            )
        )


async def _monitor_rooms():
    while True:
        await asyncio.sleep(60)
        await RoomStorage.remove_inactive()


async def monitor_rooms():
    _ = asyncio.create_task(_monitor_rooms())
