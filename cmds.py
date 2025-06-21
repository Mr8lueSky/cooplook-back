from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self

from logger import Logging
from video_status import PauseStatus, PlayStatus, SuspendStatus, VideoStatus


class ParseFailedException(Exception): ...


class Command(ABC):
    prefix: str

    @classmethod
    @abstractmethod
    def from_arguments(cls, args: list[str], by: int) -> Self: ...


@dataclass
class StatusChangeCommand(Command):
    timestamp: float
    by: int = -1

    @classmethod
    def from_arguments(cls, args: list[str], by: int) -> Self:
        try:
            timestamp = float(args[0])
            return cls(timestamp, by)
        except Exception as exc:
            raise ParseFailedException(exc)

    def to_string(self) -> str:
        return f"{self.prefix} {self.timestamp}"

    def default(self, current_status: VideoStatus) -> VideoStatus:
        current_status.current_time = self.timestamp
        return current_status

    def handle_status(self, video_status: VideoStatus) -> VideoStatus:
        if isinstance(video_status, PlayStatus):
            return self.handle_status_play(video_status)
        elif isinstance(video_status, PauseStatus):
            return self.handle_status_pause(video_status)
        elif isinstance(video_status, SuspendStatus):
            return self.handle_status_suspend(video_status)
        raise RuntimeError(f"Unknown video status: {video_status}")

    def handle_status_play(self, play_status: PlayStatus) -> VideoStatus:
        return self.default(play_status)

    def handle_status_pause(self, pause_status: PauseStatus) -> VideoStatus:
        return self.default(pause_status)

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        return self.default(suspend_status)


class SuspendCommand(StatusChangeCommand):
    prefix: str = "sp"

    def default(self, *args, **kwargs) -> VideoStatus:
        new_status = SuspendStatus(self.timestamp)
        new_status.add_suspend_by(self.by)
        return new_status

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        suspend_status.add_suspend_by(self.by)
        return suspend_status


class UnsuspendCommand(StatusChangeCommand):
    prefix: str = "up"

    def handle_status_suspend(self, suspend_status: SuspendStatus) -> VideoStatus:
        suspend_status.remove_suspend_by(self.by)
        return suspend_status


class PlayCommand(StatusChangeCommand):
    prefix: str = "pl"

    def handle_status_pause(self, pause_status: PauseStatus) -> VideoStatus:
        return PlayStatus(self.timestamp)


class PauseCommand(StatusChangeCommand):
    prefix: str = "pa"

    def handle_status_play(self, play_status: PlayStatus) -> VideoStatus:
        return PauseStatus(self.timestamp)


commands = {
    cmd.prefix: cmd
    for cmd in (PlayCommand, PauseCommand, SuspendCommand, UnsuspendCommand)
}


class RoomState(Logging):
    status: VideoStatus = PauseStatus(0)

    def handle_cmd_str(self, cmd_str: str, by: int):
        prefix, *args = cmd_str.split(" ")
        cmd = commands[prefix].from_arguments(args, by)
        self.status = cmd.handle_status(self.status)
