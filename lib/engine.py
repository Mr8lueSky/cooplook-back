from asyncio import Lock

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DB_URL, ENV
from lib.http_exceptions import NotFound
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
            for username in ("admin", "admin2"):
                user = LoginUserSchema(username=username, password="12345678")
                try:
                    existing = await UserModel.get_name(ses, username)
                    existing.pwhash = str(user.hash_password(), encoding="utf-8")
                    existing.salt = str(user.salt, encoding="utf-8")
                except NotFound:
                    await UserModel.create(
                        ses, user.username, user.hash_password(), user.salt
                    )
                except Exception:
                    logger.exception(f"Failed to create/update user {username}")
