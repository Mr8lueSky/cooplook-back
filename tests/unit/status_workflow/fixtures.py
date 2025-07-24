from pytest import fixture

from lib.video_status.status_storage import StatusHandler
from lib.video_status.video_statuses import PauseStatus, VideoStatus, SuspendStatus
from tests.unit.status_workflow import StatusType


@fixture(scope="function")
def initial_file_ind() -> int:
    return 0


@fixture(scope="function")
def initial_video_time() -> int:
    return 0


@fixture(scope="function")
def initial_suspend_list() -> list[int]:
    return [0]


@fixture(scope="function")
def initial_status_type() -> StatusType:
    return PauseStatus


@fixture(scope="function")
def initial_status(
    initial_status_type: StatusType,
    initial_video_time: int,
    initial_file_ind: int,
    initial_suspend_list: list[int],
) -> VideoStatus:
    status = initial_status_type(initial_video_time, initial_file_ind)
    if isinstance(status, SuspendStatus):
        for i in initial_suspend_list:
            _ = status.add_suspend_by(i)
    return status


@fixture(scope="function")
def expected_file_ind(initial_file_ind: int) -> int:
    return initial_file_ind


@fixture(scope="function")
def expected_video_time(initial_video_time: int) -> int:
    return initial_video_time


@fixture(scope="function")
def expected_status_type(initial_status_type: StatusType) -> StatusType:
    return initial_status_type


@fixture(scope="function")
def expected_status(
    expected_status_type: StatusType,
    expected_video_time: int,
    expected_file_ind: int,
) -> VideoStatus:
    return expected_status_type(expected_video_time, expected_file_ind)


@fixture(scope="function")
def status_handler(
    initial_status: VideoStatus,
):
    return StatusHandler(initial_status)
