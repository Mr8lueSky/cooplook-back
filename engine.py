from asyncio import Lock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DB_URL, ENV
from logger import Logging
from models.base import BaseModel
from models.user_model import UserModel
from schemas.user_schema import CreateUserSchema

engine = create_async_engine(DB_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
lock = Lock()

logger = Logging().logger


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)


async def get_session():
    async with async_session_maker.begin() as ses:
        logger.debug("DB Session open")
        yield ses
        logger.debug("DB Session close")


async def create_users():
    if ENV == "DEV":
        async with async_session_maker.begin() as ses:
            user = CreateUserSchema(name="admin", password="12345678")
            await UserModel.create(
                ses,
                user.name,
                user.hash_password(),
                user.salt
            )
