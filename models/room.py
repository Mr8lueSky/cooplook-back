from enum import Enum
from uuid import UUID, uuid1

from fastapi import HTTPException
from sqlalchemy import String, Uuid, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from models.base import Base
from room_info import RoomInfo
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


def model_to_info(model) -> RoomInfo:
    vs_cls = enum_to_source[model.video_source]
    r = RoomInfo(
        vs_cls(model.video_source_data, model.last_file_ind), model.name, model.room_id, _current_time=model.last_watch_ts
    )
    r.video_source.set_room_id(r.room_id)
    return r


class RoomModel(MappedAsDataclass, Base):
    __tablename__ = "rooms"

    name: Mapped[str] = mapped_column(String(32))
    video_source: Mapped[VideoSourcesEnum]
    video_source_data: Mapped[str] = mapped_column(String(64))
    room_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid1)
    last_file_ind: Mapped[int] = mapped_column(default=0)
    last_watch_ts: Mapped[float] = mapped_column(default=0)

    @classmethod
    async def get_all(cls, session: AsyncSession) -> list[RoomInfo]:
        stmt = select(RoomModel)
        result = await session.execute(stmt)
        return [model_to_info(m[0]) for m in result.all()]

    @classmethod
    async def get_room_id(cls, session: AsyncSession, room_id: UUID) -> RoomInfo:
        stmt = select(RoomModel).where(RoomModel.room_id == room_id)
        result = (await session.execute(stmt)).first()
        if not result:
            raise HTTPException(404, {"error": "Room not found!"})
        return model_to_info(result[0])

    @classmethod
    async def get_name(cls, session: AsyncSession, name: str) -> RoomInfo:
        stmt = select(RoomModel).where(RoomModel.name == name)
        result = (await session.execute(stmt)).first()
        if not result:
            raise HTTPException(404, {"error": "Room not found!"})
        return model_to_info(result)

    @classmethod
    async def exists_with_name(cls, session: AsyncSession, name: str) -> bool:
        stmt = exists(RoomModel).where(RoomModel.name == name)
        result = await session.scalar(select(stmt))
        return bool(result)

    @classmethod
    async def update(cls, session: AsyncSession, room_info: RoomInfo):
        vs_cls = type(room_info.video_source)
        if vs_cls not in source_to_enum:
            raise HTTPException(404, {"error": f"Video source not found: {vs_cls}"})
        stmt = (
            update(RoomModel)
            .where(RoomModel.room_id == room_info.room_id)
            .values(
                name=room_info.name,
                video_source=source_to_enum[vs_cls],
                last_watch_ts=room_info.current_time,
                last_file_ind=room_info.video_source.fi,
            )
        )
        await session.execute(stmt)

    @classmethod
    async def create(
        cls, session: AsyncSession, name: str, vs_cls: type[VideoSource], vs_data: str
    ) -> RoomInfo:
        if vs_cls not in source_to_enum:
            raise HTTPException(404, {"error": f"Video source not found: {vs_cls}"})
        if await cls.exists_with_name(session, name):
            raise HTTPException(422, {"error": "Room with same name already exists!"})
        rm = RoomModel(
            name=name, video_source=source_to_enum[vs_cls], video_source_data=vs_data
        )
        session.add(rm)
        await session.flush()
        return model_to_info(rm)
