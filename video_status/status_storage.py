from dataclasses import dataclass, field

from commands.server_commands import (PauseServerCommand, PlayServerCommand,
                                      StatusChangeServerCommand,
                                      SuspendServerCommand)
from logger import Logging
from models.room_model import RoomModel
from video_status.video_statuses import (PauseStatus, PlayStatus,
                                         SuspendStatus, VideoStatus)

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
class StatusStorage(Logging):
    status: VideoStatus = field(default_factory=lambda: PauseStatus(0, 0))

    def set_status(self, new_status: VideoStatus):
        self.status = new_status

    def from_current(self, new_status: type[VideoStatus]):
        self.status = new_status.from_status(self.status)
        return self.status

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
