from dataclasses import dataclass
from typing import Annotated, Any, Callable, Optional
from uuid import UUID

import libtorrent as lt
from fastapi import UploadFile
from pydantic import Field, StringConstraints, model_validator
from pydantic_core import core_schema

from config import MAX_TORRENT_FILE_SIZE
from lib.http_exceptions import ContentTooLarge, UnprocessableEntity
from schemas.base_schema import BaseSchema

RoomNameField = Annotated[
    str,
    StringConstraints(
        min_length=3, max_length=31, pattern=r"[а-яА-Яa-zA-Z ,./|\\?!:0-9]*"
    ),
]
LinkField = Annotated[str, StringConstraints(min_length=3, max_length=255)]
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


class CreateRoomSchema(BaseSchema):
    name: RoomNameField
    img_link: LinkField


class CreateRoomLinkSchema(CreateRoomSchema):
    video_link: LinkField


class UpdateSourceToLink(CreateRoomSchema):
    video_link: LinkField | None = None


class UpdateSourceToTorrentSchema(CreateRoomSchema):
    torrent_file: (
        Annotated[UploadFile, FileSizeValidator(MAX_TORRENT_FILE_SIZE)] | None
    ) = None
    file_content: bytes | None = Field(
        init=False, init_var=False, exclude=True, default_factory=bytes
    )

    @model_validator(mode="after")
    def set_content(cls, values):
        if values.torrent_file is None:
            return values
        values.file_content = values.torrent_file.file.read()
        if not is_valid_torrent(values.file_content):
            raise UnprocessableEntity("Not a valid torrent")
        return values


class CreateRoomTorrentSchema(CreateRoomSchema):
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

class GetRoomSchema(CreateRoomSchema):
    room_id: UUID
    name: RoomNameField
    img_link: LinkField


class GetRoomWatchingSchema(GetRoomSchema):
    files: list[tuple[int, str]]
    curr_fi: int
    video: Optional[str]
