from asyncio import Lock

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DB_URL, ENV
from lib.logger import Logging
from models.user_model import UserModel
from schemas.user_schemas import LoginUserSchema

engine = create_async_engine(DB_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
lock = Lock()

logger = Logging().logger


async def get_session():
    async with async_session_maker.begin() as ses:
        logger.debug("DB Session open")
        yield ses
        logger.debug("DB Session close")


async def create_users():
    if ENV == "DEV":
        async with async_session_maker.begin() as ses:
            user = LoginUserSchema(username="admin", password="12345678")
            try:
                _ = await UserModel.create(
                    ses, user.username, user.hash_password(), user.salt
                )
            except IntegrityError:
                ...
