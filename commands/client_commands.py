from abc import ABC, abstractmethod
from typing import Self, override

from logger import Logging
from video_status.video_statuses import (PauseStatus, PlayStatus,
                                         SuspendStatus, VideoStatus)

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
        self.logger.debug(f"Changing to new status: {new_status}")
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
        status = SuspendStatus(0, self.file_ind).add_suspend_by(self.by)
        return status


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

    @override
    def default(self, current_status: VideoStatus) -> VideoStatus:
        current_status.video_time = self.video_time
        return current_status

    @override
    def handle_status(self, video_status: VideoStatus) -> VideoStatus:
        new_status = super().handle_status(video_status)
        new_status.video_time = self.video_time
        return new_status


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
            return suspend_status.change_to.from_status(suspend_status)
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
