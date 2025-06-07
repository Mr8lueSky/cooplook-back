from dataclasses import dataclass
from typing import Annotated, Any, Callable, Optional
from uuid import UUID

import libtorrent as lt
from fastapi import UploadFile
from pydantic import Field, model_validator
from pydantic_core import core_schema

from config import MAX_TORRENT_FILE_SIZE
from exceptions import ContentTooLarge, UnprocessableEntity
from models.room_model import RoomModel
from room_info import RoomInfo
from schemas.base_schema import BaseSchema

RoomNameField = Field(min_length=3, max_length=31, pattern=r"[a-zA-Z ,./|\\?!:0-9]*")
LinkField = Field(min_length=3, max_length=63)
torrent_type = str | bytes


def is_valid_torrent(torrent: torrent_type):
    ans = False
    try:
        lt.torrent_info(torrent)
        ans = True
    except Exception:
        ...
    return ans


@dataclass
class FileSizeValidator:
    max_size: int | None = None

    def size_validator(self, value: UploadFile, handler: Callable):
        value = handler(value)
        assert value.size, "Unknown size of a file!"
        max_size = float("inf") if self.max_size is None else self.max_size
        if max_size < value.size:
            raise ContentTooLarge(f"File to large. Max is {max_size / 1024 / 1024} Mb.")
        return value

    def __get_pydantic_core_schema__(self, source_type: Any, handler):
        return core_schema.no_info_wrap_validator_function(
            self.size_validator, handler(source_type)
        )


class CreateRoomLinkSchema(BaseSchema):
    name: str = RoomNameField
    link: str = LinkField
    model_config = {"extra": "forbid"}


class CreateRoomTorrentSchema(BaseSchema):
    name: str = RoomNameField
    torrent_file: Annotated[UploadFile, FileSizeValidator(MAX_TORRENT_FILE_SIZE)]
    file_content: bytes = Field(
        init=False, init_var=False, exclude=True, default_factory=bytes
    )

    @model_validator(mode="after")
    def set_content(cls, values):
        values.file_content = values.torrent_file.file.read()
        if not is_valid_torrent(values.file_content):
            raise UnprocessableEntity("Not a valid torrent")
        return values


class GetRoomSchema(BaseSchema):
    room_id: UUID
    name: str
    video: Optional[str]

    @classmethod
    def from_room_info(cls, room_info: RoomInfo):
        return cls(
            room_id=room_info.room_id,
            name=room_info.name,
            video=room_info.video_source.get_player_src(),
        )

    @classmethod
    def from_room_model(cls, room_model: RoomModel):
        return cls(room_id=room_model.room_id, name=room_model.name, video=None)


class GetRoomWatchingSchema(GetRoomSchema):
    files: list[tuple[int, str]]
    curr_fi: int

    @classmethod
    def from_room_info(cls, room_info: RoomInfo):
        return cls(
            room_id=room_info.room_id,
            name=room_info.name,
            video=room_info.video_source.get_player_src(),
            files=room_info.get_available_files(),
            curr_fi=room_info.video_source.fi,
        )
