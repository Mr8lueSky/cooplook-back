from enum import Enum
from typing import Optional
from uuid import UUID, uuid1

from sqlalchemy import String, Uuid, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from exceptions import BadRequest, NotFound
from models.base import BaseModel
from video_sources import HttpLinkVideoSource, TorrentVideoSource, VideoSource


class VideoSourcesEnum(str, Enum):
    torrent = 0
    link = 1


enum_to_source = {
    VideoSourcesEnum.torrent: TorrentVideoSource,
    VideoSourcesEnum.link: HttpLinkVideoSource,
}

source_to_enum = {
    TorrentVideoSource: VideoSourcesEnum.torrent,
    HttpLinkVideoSource: VideoSourcesEnum.link,
}


class RoomModel(MappedAsDataclass, BaseModel):
    __tablename__ = "rooms"

    name: Mapped[str] = mapped_column(String(32))
    video_source: Mapped[VideoSourcesEnum]
    video_source_data: Mapped[str] = mapped_column(String(256))
    img_link: Mapped[str] = mapped_column(String(256))
    room_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid1)
    last_file_ind: Mapped[int] = mapped_column(default=0)
    last_watch_ts: Mapped[float] = mapped_column(default=0)

    @classmethod
    async def get_all(cls, session: AsyncSession) -> list["RoomModel"]:
        stmt = select(RoomModel)
        result = await session.execute(stmt)
        return [m[0] for m in result.all()]

    @classmethod
    async def get_room_id(cls, session: AsyncSession, room_id: UUID) -> "RoomModel":
        stmt = select(RoomModel).where(RoomModel.room_id == room_id)
        result = (await session.execute(stmt)).first()
        if not result:
            raise NotFound("Room not found!")
        return result[0]

    @classmethod
    async def get_name(cls, session: AsyncSession, name: str) -> "RoomModel":
        stmt = select(RoomModel).where(RoomModel.name == name)
        result = (await session.execute(stmt)).first()
        if not result:
            raise NotFound("Room not found!")
        return result[0]

    @classmethod
    async def exists_with_name(cls, session: AsyncSession, name: str) -> bool:
        stmt = exists(RoomModel).where(RoomModel.name == name)
        result = await session.scalar(select(stmt))
        return bool(result)

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        room_id: UUID,
        last_watch_ts: Optional[float] = None,
        last_file_ind: Optional[int] = None,
        name: Optional[str] = None,
        video_source: Optional[VideoSourcesEnum] = None,
        video_source_data: Optional[str] = None,
        img_link: Optional[str] = None,
    ):
        values = {}
        if last_watch_ts is not None:
            values["last_watch_ts"] = last_watch_ts
        if last_file_ind is not None:
            values["last_file_ind"] = last_file_ind
        if name is not None:
            values["name"] = name
        if video_source is not None:
            values["video_source"] = video_source
        if video_source_data is not None:
            values["video_source_data"] = video_source_data
        if img_link is not None:
            values["img_link"] = img_link

        stmt = update(RoomModel).where(RoomModel.room_id == room_id).values(**values)
        await session.execute(stmt)

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        name: str,
        vs_cls: type[VideoSource],
        vs_data: str,
        img_link: str,
    ) -> "RoomModel":
        if vs_cls not in source_to_enum:
            raise NotFound("Video source not found: {vs_cls}")
        if await cls.exists_with_name(session, name):
            raise BadRequest("Room with same name already exists!")
        rm = RoomModel(
            name=name,
            video_source=source_to_enum[vs_cls],
            video_source_data=vs_data,
            img_link=img_link,
        )
        session.add(rm)
        await session.flush()
        return rm
