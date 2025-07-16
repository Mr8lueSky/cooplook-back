import pytest
from lib.video_status.status_storage import StatusHandler


@pytest.fixture(scope="module")
def status_handler():
    return


@pytest.mark.asyncio
async def test_pause_play(): ...
