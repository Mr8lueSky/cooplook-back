from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import override


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
