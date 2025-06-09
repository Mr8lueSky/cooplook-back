from uuid import UUID, uuid1

import bcrypt
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from config import PW_SECRET_KET
from exceptions import NotFound
from models.base import BaseModel


class UserModel(MappedAsDataclass, BaseModel):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(32))
    pwhash: Mapped[str] = mapped_column(String(60))
    salt: Mapped[str] = mapped_column(String(29))
    user_id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid1)

    @classmethod
    async def get_id(cls, session: AsyncSession, user_id: UUID) -> "UserModel":
        stmt = select(UserModel).where(UserModel.user_id == user_id)
        result = (await session.execute(stmt)).first()
        if result is None:
            raise NotFound("User not found!")
        return result[0]

    @classmethod
    async def get_name(cls, session: AsyncSession, name: str) -> "UserModel":
        stmt = select(UserModel).where(UserModel.name == name)
        result = (await session.execute(stmt)).first()
        if result is None:
            raise NotFound("User not found!")
        return result[0]

    @classmethod
    async def create(
        cls, session: AsyncSession, name: str, pwhash: bytes, salt: bytes
    ) -> "UserModel":
        user = UserModel(
            name=name,
            pwhash=str(pwhash, encoding="utf-8"),
            salt=str(salt, encoding="utf-8"),
        )
        session.add(user)
        await session.flush()
        return user

    def verify_password(self, password: str):
        bpassword = bytes(password, "utf-8") + bytes(self.salt, "utf-8") + PW_SECRET_KET
        return bcrypt.checkpw(bpassword, self.pwhash.encode("utf-8"))
