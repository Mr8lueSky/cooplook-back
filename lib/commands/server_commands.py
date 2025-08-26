from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from typing import override

from schemas.user_schemas import UserRoomSchema


class ServerCommand(ABC):
    prefix: str

    @abstractmethod
    def to_string(self) -> str: ...


@dataclass
class StatusChangeServerCommand(ServerCommand, ABC):
    video_time: float

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {self.video_time}"


class PlayServerCommand(StatusChangeServerCommand):
    prefix: str = "pl"


class PauseServerCommand(StatusChangeServerCommand):
    prefix: str = "pa"


class SuspendServerCommand(StatusChangeServerCommand):
    prefix: str = "sp"


@dataclass
class FileChangeCommand(ServerCommand):
    fi: int
    prefix: str = "cf"

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {self.fi}"


@dataclass
class CurrentUsersCommand(ServerCommand):
    users: list[UserRoomSchema]
    prefix: str = "ua"

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {json.dumps(self.users)}"


@dataclass
class UserConnectedCommand(ServerCommand):
    user: UserRoomSchema
    prefix: str = "uc"

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {self.user.model_dump_json()}"


@dataclass
class UserDisconnectedCommand(ServerCommand):
    user_id: int
    prefix: str = "uc"

    @override
    def to_string(self) -> str:
        return f"{self.prefix} {self.user_id}"
