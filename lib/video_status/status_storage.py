from dataclasses import dataclass, field
from typing import Self


from lib.commands.server_commands import (
    PauseServerCommand,
    PlayServerCommand,
    StatusChangeServerCommand,
    SuspendServerCommand,
)
from lib.logger import Logging
from models.room_model import RoomModel
from lib.video_status.video_statuses import (
    PauseStatus,
    PlayStatus,
    SuspendStatus,
    VideoStatus,
)

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


@dataclass
class StatusHandler(Logging):
    status: VideoStatus = field(default_factory=lambda: PauseStatus(0, 0))

    @property
    def current_file_ind(self):
        return self.status.current_file_ind

    def set_video_time(self, video_time: float) -> Self:
        self.status.video_time = video_time
        return self

    def set_current_file_ind(self, fi: int) -> Self:
        if fi == self.status.current_file_ind:
            return self
        self.status.current_file_ind = fi
        return self.set_pause_status().set_video_time(0)

    def set_play_status(self) -> Self:
        if not isinstance(self.status, PauseStatus):
            return self
        self.status = PlayStatus.from_status(self.status)
        return self

    def set_pause_status(self) -> Self:
        # if not isinstance(self.status, PlayStatus):
        #     return self
        self.status = PauseStatus.from_status(self.status)
        return self

    def unsuspend_to(self, status: type[VideoStatus]) -> Self:
        if isinstance(self.status, SuspendStatus):
            self.status.change_to = status
        return self

    def add_suspend_by(self, id: int) -> Self:
        if not isinstance(self.status, SuspendStatus):
            self.status = SuspendStatus.from_status(self.status)
        _ = self.status.add_suspend_by(id)
        return self

    def remove_suspend_by(self, id: int) -> Self:
        if not isinstance(self.status, SuspendStatus):
            return self
        _ = self.status.remove_suspend_by(id)
        if self.status.should_unsuspend():
            self.status = self.status.change_to.from_status(self.status)
        return self

    def to_server_command(self) -> StatusChangeServerCommand:
        server_cmd = status_to_server_cmd(self.status)
        return server_cmd(video_time=self.status.video_time)

    @classmethod
    def from_model(cls, model: RoomModel) -> "StatusHandler":
        return cls(PauseStatus(model.last_watch_ts, model.last_file_ind))

    def update_model(self, model: RoomModel) -> RoomModel:
        model.last_file_ind = self.status.current_file_ind
        model.last_watch_ts = self.status.video_time
        return model
