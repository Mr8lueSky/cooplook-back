from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DB_URL, ENV
from models.base import Base

engine = create_async_engine(DB_URL, echo=ENV == "DEV")
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with async_session_maker.begin() as ses:
        yield ses
