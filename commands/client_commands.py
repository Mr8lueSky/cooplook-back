from abc import ABC, abstractmethod
from typing import Self, override

from logger import Logging
from video_status.status_storage import StatusHandler

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


class StateChangeClientCommand(ClientCommand, ABC, Logging):
    def __init__(self, by: int) -> None:
        super().__init__()
        self.by: int = by

    @abstractmethod
    def handle(self, status_handler: StatusHandler): ...


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
    def handle(self, status_handler: StatusHandler):
        _ = (
            status_handler.set_current_file_ind(self.file_ind)
            .set_pause_status()
            .set_video_time(0)
        )


class StatusChangeClientCommand(StateChangeClientCommand, ABC):
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

    @override
    def handle(self, status_handler: StatusHandler):
        _ = status_handler.set_video_time(self.video_time)


@register_client_command
class SuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "sp"

    @override
    def handle(self, status_handler: StatusHandler):
        super().handle(status_handler)
        _ = status_handler.add_suspend_by(self.by)


@register_client_command
class UnsuspendClientCommand(StatusChangeClientCommand):
    prefix: str = "up"

    @override
    def handle(self, status_handler: StatusHandler):
        super().handle(status_handler)
        _ = status_handler.remove_suspend_by(self.by)


@register_client_command
class PlayClientCommand(StatusChangeClientCommand):
    prefix: str = "pl"

    @override
    def handle(self, status_handler: StatusHandler):
        super().handle(status_handler)
        _ = status_handler.set_play_status()


@register_client_command
class PauseClientCommand(StatusChangeClientCommand):
    prefix: str = "pa"

    @override
    def handle(self, status_handler: StatusHandler):
        super().handle(status_handler)
        _ = status_handler.set_pause_status()
