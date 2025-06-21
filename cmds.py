from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import count
from typing import Iterable, Iterator, Self

from fastapi import WebSocket, WebSocketDisconnect

from logger import Logging
from models.room_model import RoomModel
from video_status import PauseStatus, PlayStatus, SuspendStatus, VideoStatus

client_commands: dict[str, type["ClientCommand"]] = {}


def register_client_command(cls):
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


class StateChangeClientCommand(ClientCommand):
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
    prefix = "cf"

    def __init__(self, by: int, file_ind: int) -> None:
        super().__init__(by)
        self.file_ind = file_ind

    @classmethod
    def from_arguments(cls, args: list[str], by: int) -> Self:
        try:
            file_ind = int(args[0])
            return cls(by, file_ind)
        except Exception as exc:
            raise ParseFailedException(exc)

    def default(self, current_status: VideoStatus) -> VideoStatus:
        return SuspendStatus(0, self.file_ind)


class StatusChangeClientCommand(StateChangeClientCommand):
    def __init__(self, by: int, video_time: float) -> None:
        super().__init__(by)
        self.video_time = video_time

    @classmethod
    def from_arguments(cls, args: list[str], by: int) -> Self:
        try:
            timestamp = float(args[0])
            return cls(by, timestamp)
        except Exception as exc:
            raise ParseFailedException(exc)


@register_client_command
class SuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "sp"

    def default(self, current_status: VideoStatus) -> VideoStatus:
        new_status = SuspendStatus.from_status(current_status)
        new_status.add_suspend_by(self.by)
        return new_status

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        suspend_status.add_suspend_by(self.by)
        return suspend_status


@register_client_command
class UnsuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "up"

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        suspend_status.remove_suspend_by(self.by)
        if suspend_status.should_unsuspend():
            return PlayStatus.from_status(suspend_status)
        return suspend_status


@register_client_command
class PlayClientCommand(StatusChangeClientCommand):
    prefix: str = "pl"

    def handle_status_pause(self, pause_status: PauseStatus) -> VideoStatus:
        return PlayStatus.from_status(pause_status).set_time(self.video_time)


@register_client_command
class PauseClientCommand(StatusChangeClientCommand):
    prefix: str = "pa"

    def handle_status_play(self, play_status: PlayStatus) -> VideoStatus:
        return PauseStatus.from_status(play_status).set_time(self.video_time)


@dataclass
class StatusChangeServerCommand(ServerCommand):
    video_time: float

    def to_string(self) -> str:
        return f"{self.prefix} {self.video_time}"


class PlayServerCommand(StatusChangeServerCommand):
    prefix = "pl"


class PauseServerCommand(StatusChangeServerCommand):
    prefix = "pl"


class SuspendServerCommand(StatusChangeServerCommand):
    prefix = "pl"


class CommandTypeHandler(ABC):
    handle_type: type[ClientCommand]

    @abstractmethod
    def handle(self, cmd: ClientCommand): ...


status_to_cmd: dict[type[VideoStatus], type["StatusChangeServerCommand"]] = {
    PlayStatus: PlayServerCommand,
    PauseStatus: PauseServerCommand,
    SuspendStatus: SuspendServerCommand,
}


@dataclass
class StatusStorage(Logging):
    status: VideoStatus = field(default_factory=lambda: PauseStatus(0, 0))

    def set_status(self, new_status: VideoStatus):
        self.status = new_status

    def from_current(self, new_status: type[VideoStatus]):
        self.status = new_status.from_status(self.status)

    def to_server_command(self) -> StatusChangeServerCommand:
        return status_to_cmd[self.status.__class__](video_time=self.status.video_time)

    @classmethod
    def from_mode(cls, model: RoomModel) -> 'StatusStorage':
        return cls(PauseStatus(model.last_watch_ts, model.last_file_ind))
    
    def update_model(self, model: RoomModel) -> RoomModel:
        model.last_file_ind = self.status.current_file_ind
        model.last_watch_ts = self.status.video_time
        return model


class StatusChangeCommandsHandler(CommandTypeHandler):
    handle_type = StateChangeClientCommand

    def __init__(self, status_storage: StatusStorage) -> None:
        super().__init__()
        self.status_storage = status_storage

    def handle(self, cmd: ClientCommand):
        if not isinstance(cmd, StateChangeClientCommand):
            raise TypeError(f"{self} can't handle {cmd}!")

        self.handle_status_change_cmd(cmd)

    def handle_status_change_cmd(self, cmd: StateChangeClientCommand):
        self.status_storage.set_status(cmd.handle_status(self.status_storage.status))


class AllCommandsHandler(CommandTypeHandler):
    handle_type = ClientCommand

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

    def add_connection(self, conn: Connection):
        conn_id = next(self.conn_id_iter)
        self.conns[conn_id] = conn
        return conn_id

    async def remove_connection(self, conn_id: int):
        self.conns.pop(conn_id)

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


class RoomState:
    def __init__(self, status_storage: StatusStorage) -> None:
        self.status_storage = status_storage
        self.cmd_handler = AllCommandsHandler(
            (StatusChangeCommandsHandler(self.status_storage),)
        )
        self.conn_manager = ConnectionsManager()

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


if __name__ == "__main__":
    status_storage = StatusStorage()
    cmd_handler = AllCommandsHandler((StatusChangeCommandsHandler(status_storage),))
    print(f"Status: {status_storage.status}")
    cmd_handler.handle_str_cmd("pl 10", 0)
    print(f"Status: {status_storage.status}")
    print(f"Time: {status_storage.status.video_time}")
    cmd_handler.handle_str_cmd("sp 20", 0)
    print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
    cmd_handler.handle_str_cmd("pl 10", 0)
    print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
    cmd_handler.handle_str_cmd("cf 4", 0)
    print(f"Status: {status_storage.status}, Time: {status_storage.status.video_time}")
