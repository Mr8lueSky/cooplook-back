from abc import ABC, abstractmethod
import os
from typing import override
from uuid import UUID, uuid1
from pathlib import Path
import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from config import TORRENT_FILES_SAVE_PATH
from lib.room import RoomStorage
from models.room_model import RoomModel, VideoSourcesEnum
from schemas.room_schemas import (
    CreateRoomLinkSchema,
    CreateRoomSchema,
    CreateRoomTorrentSchema,
    UpdateRoomLinkSchema,
    UpdateRoomSchema,
    UpdateRoomTorrentSchema,
)


class RoomCreator(ABC):
    create_cls: type[CreateRoomSchema]
    update_cls: type[UpdateRoomSchema]

    @classmethod
    @abstractmethod
    async def create(
        cls, session: AsyncSession, data: CreateRoomSchema
    ) -> RoomModel: ...

    @classmethod
    @abstractmethod
    async def update(
        cls, session: AsyncSession, room_id: UUID, data: UpdateRoomSchema
    ): ...


class RoomFactory:
    factories: dict[type[CreateRoomSchema], type[RoomCreator]] = {}

    @classmethod
    def add_factory(cls, factory: type[RoomCreator]) -> type[RoomCreator]:
        cls.factories[factory.create_cls] = factory
        cls.factories[factory.update_cls] = factory
        return factory

    @classmethod
    def get_room_factory(cls, data: CreateRoomSchema) -> type[RoomCreator]:
        creator = cls.factories.get(data.__class__, None)
        if creator is None:
            raise RuntimeError(f"Can't find creator for {data}!")
        return creator


@RoomFactory.add_factory
class TorrentRoomCreator(RoomCreator):
    create_cls: type[CreateRoomSchema] = CreateRoomTorrentSchema
    update_cls: type[UpdateRoomSchema] = UpdateRoomTorrentSchema

    @classmethod
    async def create_torrent_file(cls, content: bytes) -> Path:
        os.makedirs(TORRENT_FILES_SAVE_PATH, exist_ok=True)
        torrent_path = TORRENT_FILES_SAVE_PATH / str(uuid1())
        async with await anyio.open_file(torrent_path, mode="wb") as file:
            _ = await file.write(content)
        return torrent_path

    @classmethod
    @override
    async def create(cls, session: AsyncSession, data: CreateRoomSchema) -> RoomModel:
        if not isinstance(data, CreateRoomTorrentSchema):
            raise TypeError("Given data is not a create torrent schema!")
        torrent_fpth = await cls.create_torrent_file(data.file_content)
        r = await RoomModel.create(
            session,
            data.name,
            VideoSourcesEnum.torrent,
            torrent_fpth.as_posix(),
            data.img_link,
            data.description
        )
        return r

    @classmethod
    @override
    async def update(cls, session: AsyncSession, room_id: UUID, data: UpdateRoomSchema):
        if not isinstance(data, UpdateRoomTorrentSchema):
            raise TypeError("Given data is not a create torrent schema!")
        torrent_path: str | None = None
        if data.torrent_file:
            torrent_path = (await cls.create_torrent_file(data.file_content)).as_posix()
        await RoomModel.update(
            session,
            room_id,
            last_watch_ts=0 if data.torrent_file else None,
            last_file_ind=0 if data.torrent_file else None,
            vs_enum=VideoSourcesEnum.torrent,
            name=data.name or None,
            img_link=data.img_link or None,
            video_source_data=torrent_path,
            description=data.description
        )


@RoomFactory.add_factory
class LinkRoomCreator(RoomCreator):
    create_cls: type[CreateRoomSchema] = CreateRoomLinkSchema
    update_cls: type[UpdateRoomSchema] = UpdateRoomLinkSchema

    @classmethod
    @override
    async def create(cls, session: AsyncSession, data: CreateRoomSchema) -> RoomModel:
        if not isinstance(data, CreateRoomLinkSchema):
            raise TypeError("Given data is not a create link schema!")
        r = await RoomModel.create(
            session,
            data.name,
            VideoSourcesEnum.link,
            data.video_link,
            data.img_link,
            data.description
        )
        return r

    @classmethod
    @override
    async def update(cls, session: AsyncSession, room_id: UUID, data: UpdateRoomSchema):
        if not isinstance(data, UpdateRoomLinkSchema):
            raise TypeError("Given data is not a create torrent schema!")
        await RoomModel.update(
            session,
            room_id,
            last_watch_ts=0 if data.video_link else None,
            last_file_ind=0 if data.video_link else None,
            name=data.name,
            vs_enum=VideoSourcesEnum.link,
            video_source_data=data.video_link,
            img_link=data.img_link,
            description=data.description
        )


class RoomService:
    @classmethod
    async def create_room(
        cls, session: AsyncSession, room_data: CreateRoomSchema
    ) -> RoomModel:
        creator = RoomFactory.get_room_factory(room_data)
        room_id = await creator.create(session, room_data)
        return room_id

    @classmethod
    async def update_room(
        cls, session: AsyncSession, room_id: UUID, room_data: UpdateRoomSchema
    ):
        updator = RoomFactory.get_room_factory(room_data)
        await updator.update(session, room_id, room_data)
        await RoomStorage.load_room(session, room_id, ignore_if_loaded=False)
