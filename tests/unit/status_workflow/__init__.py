from typing import Callable
from lib.video_status.status_storage import StatusHandler
from lib.video_status.video_statuses import VideoStatus


StatusChangeFunc = Callable[[StatusHandler], StatusHandler]
StatusType = type[VideoStatus]


VIDEO_TIME_MARGIN = 0.001


def assert_status(status_handler: StatusHandler, status: VideoStatus):
    actual_status = status_handler.status
    assert isinstance(
        actual_status, status.__class__
    ), f"Status is not {status}! {status_handler.status}"
    assert (
        actual_status.current_file_ind == status.current_file_ind
    ), "Non matching file index!"
    video_time = status.video_time
    assert (
        video_time - VIDEO_TIME_MARGIN
        <= actual_status.video_time
        <= video_time + VIDEO_TIME_MARGIN
    ), "Video time is out of expected!"


def add_suspend_by(pid: int = 0):
    def inner(
        status_handler: StatusHandler,
    ) -> StatusHandler:
        return status_handler.add_suspend_by(pid)

    return inner


def remove_suspend_by(pid: int = 0):
    def inner(
        status_handler: StatusHandler,
    ) -> StatusHandler:
        return status_handler.remove_suspend_by(pid)

    return inner


def play():
    def inner(
        status_handler: StatusHandler,
    ) -> StatusHandler:
        return status_handler.set_play_status()

    return inner


def pause():
    def inner(
        status_handler: StatusHandler,
    ) -> StatusHandler:
        return status_handler.set_pause_status()

    return inner
