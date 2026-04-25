from lib.video_status.status_storage import StatusHandler
from lib.video_status.video_statuses import (
    PauseStatus,
    PlayStatus,
    SuspendStatus,
    VideoStatus,
)
from pytest import mark

from tests.unit.status_workflow import (
    StatusChangeFunc,
    StatusType,
    add_suspend_by,
    assert_status,
    pause,
    play,
    remove_suspend_by,
)
from tests.unit.status_workflow.fixtures import *  # noqa: F403

#                 initial status ->action:           expected status
status_flow: dict[StatusType, dict[StatusChangeFunc, StatusType]] = {
    PauseStatus: {
        play(): PlayStatus,
        pause(): PauseStatus,
        add_suspend_by(0): SuspendStatus,
        remove_suspend_by(0): PauseStatus,
    },
    PlayStatus: {
        play(): PlayStatus,
        pause(): PauseStatus,
        add_suspend_by(0): SuspendStatus,
        remove_suspend_by(0): PlayStatus,
    },
    SuspendStatus: {
        play(): SuspendStatus,
        pause(): SuspendStatus,
        add_suspend_by(0): SuspendStatus,
        remove_suspend_by(0): PlayStatus,
    },
}

VideoTime = int
FileInd = int
status_video_file: list[tuple[VideoTime, FileInd]] = [(0, 0), (10, 2), (22, 5)]


@mark.parametrize(
    "initial_status_type,status_change_func,expected_status_type",
    [
        (initial_status_type, status_change_func, expected_status_type)
        for initial_status_type, status_dict in status_flow.items()
        for (status_change_func, expected_status_type) in status_dict.items()
    ],
)
@mark.parametrize("initial_file_ind,initial_video_time", status_video_file)
def test_general_status_flow(
    status_handler: StatusHandler,
    status_change_func: StatusChangeFunc,
    expected_status_type: StatusType,
    initial_video_time: VideoTime,
    initial_file_ind: FileInd,
):
    expected_status = expected_status_type(initial_video_time, initial_file_ind)
    assert_status(status_change_func(status_handler), expected_status)


@mark.parametrize(
    "initial_status_type,initial_suspend_list,expected_status_type",
    [(SuspendStatus, list(range(10)), PlayStatus)],
)
def test_suspend_unsuspend_by_10_people(
    status_handler: StatusHandler,
    initial_suspend_list: list[int],
    expected_status: SuspendStatus,
):
    for i in initial_suspend_list:
        assert isinstance(status_handler.status, SuspendStatus)
        _ = status_handler.remove_suspend_by(i)
    assert_status(status_handler, expected_status)


@mark.parametrize(
    "initial_status_type,expected_status_type", [(SuspendStatus, PauseStatus)]
)
def test_suspend_unsuspend_to_play(
    status_handler: StatusHandler,
    expected_status: VideoStatus,
    expected_status_type: StatusType,
    initial_suspend_list: list[int],
):
    _ = status_handler.unsuspend_to(expected_status_type)
    for i in initial_suspend_list:
        _ = status_handler.remove_suspend_by(i)
    assert_status(status_handler, expected_status)
