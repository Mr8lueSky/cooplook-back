import time
from abc import ABC
from typing import override


class VideoStatus(ABC):
    def __init__(self, video_time: float, current_file_ind: int) -> None:
        super().__init__()
        self.video_time: float = video_time
        self.current_file_ind: int = current_file_ind

    @classmethod
    def from_status(cls, status: "VideoStatus"):
        return cls(
            video_time=status.video_time, current_file_ind=status.current_file_ind
        )

    def set_time(self, video_time: float):
        self.video_time = video_time
        return self


class PauseStatus(VideoStatus): ...


class PlayStatus(VideoStatus):
    def __init__(self, video_time: float, current_file_ind: int) -> None:
        self._video_time: float = 0
        super().__init__(video_time, current_file_ind)
        self._status_creation: float = time.time()

    @property
    @override
    def video_time(self) -> float:
        return self._video_time + time.time() - self._status_creation

    @video_time.setter
    def video_time(self, new_time: float):  # pyright: ignore[reportIncompatibleVariableOverride]
        self._video_time = new_time


class SuspendStatus(VideoStatus):
    def __init__(self, video_time: float, current_file_ind: int) -> None:
        super().__init__(video_time, current_file_ind)
        self.suspend_by: set[int] = set()
        self.change_to: type[VideoStatus] = PlayStatus

    def add_suspend_by(self, suspend_by: int):
        self.suspend_by.add(suspend_by)
        return self

    def remove_suspend_by(self, suspend_by: int):
        if suspend_by in self.suspend_by:
            self.suspend_by.remove(suspend_by)
        return self

    def should_unsuspend(self):
        return not bool(self.suspend_by)
