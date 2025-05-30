from time import sleep
from uuid import uuid1

from main import VideoStatus, RoomInfo

ri = RoomInfo(uuid1(), "")

# Play/Pause
assert ri.current_time == 0
ri.change_status(VideoStatus.PLAY)
sleep(10)
ri.change_status(VideoStatus.PAUSE)
assert 9 <= ri.current_time <= 11, f"Actual: {ri.current_time}"
ri.change_status(VideoStatus.PLAY)
sleep(10)
ri.change_status(VideoStatus.PAUSE)
assert 19 <= ri.current_time <= 21, f"Actual: {ri.current_time}"
print("pass")

# Set time during pause
ri.current_time = 0
assert ri.current_time == 0, f"Actual: {ri.current_time}"
print("pass")

# Set time during play
ri.change_status(VideoStatus.PLAY)
sleep(5)
assert 4 <= ri.current_time <= 6, f"Actual: {ri.current_time}"
ri.current_time = 20
assert 19 <= ri.current_time <= 21, f"Actual: {ri.current_time}"
sleep(5)
assert 24 <= ri.current_time <= 26, f"Actual: {ri.current_time}"
sleep(5)
ri.change_status(VideoStatus.PAUSE)
assert 29 <= ri.current_time <= 31, f"Actual: {ri.current_time}"
print("pass")
