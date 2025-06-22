from abc import ABC, abstractmethod
from asyncio import Lock
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Self, override
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from logger import Logging
from models.room_model import RoomModel
from video_sources import VideoSource
from video_status import PauseStatus, PlayStatus, SuspendStatus, VideoStatus

client_commands: dict[str, type["ClientCommand"]] = {}


def register_client_command(cls: type["ClientCommand"]) -> type["ClientCommand"]:
    if cls.prefix in client_commands:
        raise RuntimeError(f"Command {cls.prefix} is already defined!")
    client_commands[cls.prefix] = cls
    return cls


class ParseFailedException(Exception): ...


class ClientCommand(ABC):
    prefix: str

    @classmethod
    @abstractmethod
    def from_arguments(cls, args: list[str], by: int) -> Self: ...


class ServerCommand(ABC):
    prefix: str

    @abstractmethod
    def to_string(self) -> str: ...


class StateChangeClientCommand(ClientCommand, ABC):
    def __init__(self, by: int) -> None:
        super().__init__()
        self.by: int = by

    def default(self, current_status: VideoStatus) -> VideoStatus:
        return current_status

    def handle_status(self, video_status: VideoStatus) -> VideoStatus:
        new_status = None
        if isinstance(video_status, PlayStatus):
            new_status = self.handle_status_play(video_status)
        elif isinstance(video_status, PauseStatus):
            new_status = self.handle_status_pause(video_status)
        elif isinstance(video_status, SuspendStatus):
            new_status = self.handle_status_suspend(video_status)
        else:
            raise RuntimeError(f"Unknown video status: {video_status}")
        return new_status

    def handle_status_play(self, play_status: PlayStatus) -> VideoStatus:
        return self.default(play_status)

    def handle_status_pause(self, pause_status: PauseStatus) -> VideoStatus:
        return self.default(pause_status)

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        return self.default(suspend_status)


@register_client_command
class ChangeFileClientCommand(StateChangeClientCommand):
    prefix: str = "cf"

    def __init__(self, by: int, file_ind: int) -> None:
        super().__init__(by)
        self.file_ind: int = file_ind

    @classmethod
    @override
    def from_arguments(cls, args: list[str], by: int) -> Self:
        try:
            file_ind = int(args[0])
            return cls(by, file_ind)
        except Exception as exc:
            raise ParseFailedException(exc)

    @override
    def default(self, current_status: VideoStatus) -> VideoStatus:
        return SuspendStatus(0, self.file_ind)


class StatusChangeClientCommand(StateChangeClientCommand):
    def __init__(self, by: int, video_time: float) -> None:
        super().__init__(by)
        self.video_time: float = video_time

    @classmethod
    @override
    def from_arguments(cls, args: list[str], by: int) -> Self:
        try:
            timestamp = float(args[0])
            return cls(by, timestamp)
        except Exception as exc:
            raise ParseFailedException(exc)


@register_client_command
class SuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "sp"

    @override
    def default(self, current_status: VideoStatus) -> VideoStatus:
        new_status = SuspendStatus.from_status(current_status).add_suspend_by(self.by)
        return new_status

    @override
    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        return suspend_status.add_suspend_by(self.by)


@register_client_command
class UnsuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "up"

    @override
    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        _ = suspend_status.remove_suspend_by(self.by)
        if suspend_status.should_unsuspend():
            return PlayStatus.from_status(suspend_status)
        return suspend_status


@register_client_command
class PlayClientCommand(StatusChangeClientCommand):
    prefix: str = "pl"

    @override
    def handle_status_pause(self, pause_status: PauseStatus) -> VideoStatus:
        return PlayStatus.from_status(pause_status).set_time(self.video_time)


@register_client_command
class PauseClientCommand(StatusChangeClientCommand):
    prefix: str = "pa"

    @override
    def handle_status_play(self, play_status: PlayStatus) -> VideoStatus:
        return PauseStatus.from_status(play_status).set_time(self.video_time)


@dataclass
class StatusChangeServerCommand(ServerCommand):
    video_time: float

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {self.video_time}"


class PlayServerCommand(StatusChangeServerCommand):
    prefix: str = "pl"


class PauseServerCommand(StatusChangeServerCommand):
    prefix: str = "pl"


class SuspendServerCommand(StatusChangeServerCommand):
    prefix: str = "pl"


class CommandTypeHandler(ABC):
    handle_type: type[ClientCommand]

    @abstractmethod
    def handle(self, cmd: ClientCommand): ...


statuses_to_cmds: dict[type[VideoStatus], type["StatusChangeServerCommand"]] = {
    PlayStatus: PlayServerCommand,
    PauseStatus: PauseServerCommand,
    SuspendStatus: SuspendServerCommand,
}


def status_to_server_cmd(status: VideoStatus) -> type[StatusChangeServerCommand]:
    server_cmd = statuses_to_cmds.get(status.__class__)
    if server_cmd is None:
        raise RuntimeError(
            f"Can't find mapping of {status.__class__} status to server command!"
        )
    return server_cmd


StatusChangeNotify = Callable[[VideoStatus], None]

@dataclass
class StatusStorage(Logging):
    status: VideoStatus = field(default_factory=lambda: PauseStatus(0, 0))
    nofity: list[StatusChangeNotify] = field(init=False, default_factory=list)

    def set_status(self, new_status: VideoStatus):
        self.status = new_status
        for n in self.nofity:
            n(new_status)
    
    def add_observer(self, notify: StatusChangeNotify):
        self.nofity.append(notify)

    def remove_observer(self, notify: StatusChangeNotify):
        self.nofity.remove(notify)

    def from_current(self, new_status: type[VideoStatus]):
        self.status = new_status.from_status(self.status)

    def to_server_command(self) -> StatusChangeServerCommand:
        server_cmd = status_to_server_cmd(self.status)
        return server_cmd(video_time=self.status.video_time)

    @classmethod
    def from_model(cls, model: RoomModel) -> "StatusStorage":
        return cls(PauseStatus(model.last_watch_ts, model.last_file_ind))

    def update_model(self, model: RoomModel) -> RoomModel:
        model.last_file_ind = self.status.current_file_ind
        model.last_watch_ts = self.status.video_time
        return model


class StatusChangeCommandsHandler(CommandTypeHandler):
    handle_type: type[ClientCommand] = StateChangeClientCommand

    def __init__(self, status_storage: StatusStorage) -> None:
        super().__init__()
        self.status_storage: StatusStorage = status_storage

    @override
    def handle(self, cmd: ClientCommand):
        if not isinstance(cmd, StateChangeClientCommand):
            raise TypeError(f"{self} can't handle {cmd}!")

        self.handle_status_change_cmd(cmd)

    def handle_status_change_cmd(self, cmd: StateChangeClientCommand):
        self.status_storage.set_status(cmd.handle_status(self.status_storage.status))


class CommandsGroupHandler(CommandTypeHandler):
    handle_type: type[ClientCommand] = ClientCommand

    def __init__(self, handlers_to_reg: Iterable[CommandTypeHandler]) -> None:
        super().__init__()
        self.cmd_type_to_handler: dict[type[ClientCommand], CommandTypeHandler] = {
            handler.handle_type: handler for handler in handlers_to_reg
        }

    def match_cmd_handler(self, cmd: ClientCommand):
        for cmd_type, handler in self.cmd_type_to_handler.items():
            if isinstance(cmd, cmd_type):
                return handler
        raise RuntimeError(f"Can not find handler for {cmd} command!")

    @override
    def handle(self, cmd: ClientCommand):
        handler = self.match_cmd_handler(cmd)
        handler.handle(cmd)

    def handle_str_cmd(self, cmd_str: str, by: int):
        prefix, *args = cmd_str.split(" ")
        command = client_commands.get(prefix)
        if command is None:
            raise RuntimeError(f"Unknown command {prefix}!")
        return self.handle(command.from_arguments(args, by))


@dataclass
class Connection:
    ws_conn: WebSocket

    async def send(self, cmd: ServerCommand):
        try:
            await self.ws_conn.send_text(cmd.to_string())
        except WebSocketDisconnect:
            ...


@dataclass
class ConnectionsManager:
    conns: dict[int, Connection] = field(default_factory=dict)
    conn_id_iter: Iterator[int] = count()

    async def send_to(self, conn_id: int, cmd: ServerCommand):
        if conn_id not in self.conns:
            raise RuntimeError(f"Unknown id:{conn_id}")
        conn = self.conns[conn_id]
        await conn.send(cmd)

    def add_connection(self, conn: Connection) -> int:
        conn_id = next(self.conn_id_iter)
        self.conns[conn_id] = conn
        return conn_id

    def remove_connection(self, conn_id: int):
        _ = self.conns.pop(conn_id)

    async def send_room(self, cmd: ServerCommand, exclude: list[int] | None = None):
        exclude = exclude or []
        for conn_id, conn in self.conns.items():
            if conn_id in exclude:
                continue
            await conn.send(cmd)


@dataclass
class RoomInfo:
    name: str
    img_link: str


class RoomStateHandler:
    def __init__(
        self,
        status_storage: StatusStorage,
        cmd_handler: CommandsGroupHandler,
        conn_manager: ConnectionsManager,
    ) -> None:
        self.status_storage: StatusStorage = status_storage
        self.cmd_handler: CommandsGroupHandler = cmd_handler
        self.conn_manager: ConnectionsManager = conn_manager

    async def send_status_update(self):
        await self.conn_manager.send_room(self.status_storage.to_server_command())

    async def handle_cmd_str(self, cmd_str: str, by: int):
        self.cmd_handler.handle_str_cmd(cmd_str, by)
        await self.send_status_update()

    def set_status(self, new_status: VideoStatus):
        self.status_storage.set_status(new_status)

    def set_status_from_current(self, new_status: type[VideoStatus]):
        self.status_storage.from_current(new_status)

    async def add_connection(self, conn: Connection):
        conn_id = self.conn_manager.add_connection(conn)
        suspend = SuspendStatus.from_status(self.status_storage.status).add_suspend_by(
            conn_id
        )
        self.status_storage.set_status(suspend)
        await self.send_status_update()
        return conn_id

    def remove_connection(self, conn_id: int):
        self.conn_manager.remove_connection(conn_id)


@dataclass
class Room:
    room_id: UUID
    name: str
    img_link: str
    status_storage: StatusStorage
    video_source: VideoSource
    room_state_handler: RoomStateHandler = field(init=False)

    def __post_init__(self):
        cmd_handler = CommandsGroupHandler(
            (StatusChangeCommandsHandler(self.status_storage),)
        )
        conn_manager = ConnectionsManager()
        self.room_state_handler = RoomStateHandler(
            self.status_storage, cmd_handler, conn_manager
        )

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
        _ = self.status_storage.update_model(model)
        _ = self.video_source.update_model(model)

    async def add_connection(self, conn: Connection) -> int:
        conn_id = await self.room_state_handler.add_connection(conn)
        self.room_state_handler.set_status_from_current(SuspendStatus)
        return conn_id

    async def remove_connection(self, conn_id: int):
        self.room_state_handler.remove_connection(conn_id)

    async def handle_cmd_str(self, cmd_str: str, by: int):
        await self.room_state_handler.handle_cmd_str(cmd_str, by)
        _ = self.video_source.set_file_index(
            self.status_storage.status.current_file_ind
        )


class RoomStorage:
    def __init__(self) -> None:
        self.lock: Lock = Lock()
        self.loaded_rooms: dict[UUID, Room] = {}

    async def load_room(self, session: AsyncSession, room_id: UUID):
        room = await RoomModel.get_room_id(session, room_id)
        self.loaded_rooms[room_id] = Room.from_model(room)

    async def get_room(self, session: AsyncSession, room_id: UUID):
        async with self.lock:
            if room_id not in self.loaded_rooms:
                await self.load_room(session, room_id)
        return self.loaded_rooms[room_id]


# def create_room():
#     model = RoomModel(name="", video_source="src", video_source_data="", img_link="")
#     status_storage = StatusStorage.from_model(model)
#     cmd_handler = CommandsGroupHandler((StatusChangeCommandsHandler(status_storage),))
#     conn_manager = ConnectionsManager()
#     room_state_handler = RoomStateHandler(status_storage, cmd_handler, conn_manager)


# if __name__ == "__main__":
#     status_storage = StatusStorage()
#     cmd_handler = CommandsGroupHandler((StatusChangeCommandsHandler(status_storage),))
#     print(f"Status: {status_storage.status}")
#     cmd_handler.handle_str_cmd("pl 10", 0)
#     print(f"Status: {status_storage.status}")
#     print(f"Time: {status_storage.status.video_time}")
#     cmd_handler.handle_str_cmd("sp 20", 0)
#     print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
#     cmd_handler.handle_str_cmd("pl 10", 0)
#     print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
#     cmd_handler.handle_str_cmd("cf 4", 0)
#     print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
