from enum import Enum


class Commands(str, Enum):
    PLAY = "pl"
    PAUSE = "pa"
    SUSPEND = "sp"
    UNSUSPEND = "up"
    SET_CT = "sc"
    PEOPLE_COUNT = "pc"
    CHANGE_FILE = "cf"

    @classmethod
    def change_file_cmd(cls, fi: int):
        return f"{cls.CHANGE_FILE.value} {fi}"

    @classmethod
    def play_cmd(cls, ts: float):
        return f"{cls.PLAY.value} {ts}"

    @classmethod
    def pause_cmd(cls, ts: float):
        return f"{cls.PAUSE.value} {ts}"

    @classmethod
    def suspend_cmd(cls, ts: float):
        return f"{cls.SUSPEND.value} {ts}"

    @classmethod
    def unsuspend_cmd(cls, ts: float):
        return f"{cls.UNSUSPEND.value} {ts}"

    @classmethod
    def people_count_cmd(cls, people_cnt: int):
        return f"{cls.PEOPLE_COUNT.value} {people_cnt}"


class VideoStatus(str, Enum):
    PLAY = Commands.PLAY.value
    PAUSE = Commands.PAUSE.value
    SUSPEND = Commands.SUSPEND.value
