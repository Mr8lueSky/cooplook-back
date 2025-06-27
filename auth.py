from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Cookie, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config import AUTH_SECRET_KEY
from engine import async_session_maker
from exceptions import NotFound
from models.user_model import UserModel
from schemas.user_schema import GetUserSchema

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30 # one mounth


async def authenticate_user(session: AsyncSession, username: str, password: str):
    user = await UserModel.get_name(session, username)
    if not user:
        return False
    if not user.verify_password(password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = int(expire.timestamp())
    encoded_jwt = jwt.encode(to_encode, AUTH_SECRET_KEY, ALGORITHM)
    return encoded_jwt


async def current_user(token: Annotated[str | None, Cookie()] = None) -> GetUserSchema:
    logout_resp = HTTPException(
        status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/logout"}
    )

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"}
        )

    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, ALGORITHM)
        username = payload.get("sub")
        if username is None:
            raise logout_resp
    except jwt.InvalidTokenError as exc:
        raise logout_resp
    async with async_session_maker.begin() as session:
        user = await UserModel.get_name(session, username)
    if user is None:
        raise logout_resp
    return GetUserSchema.model_validate(user, from_attributes=True)


async def generate_token(session: AsyncSession, username: str, password: str):
    user = await authenticate_user(session, username, password)
    if not user:
        raise NotFound("User not found!")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.name},
        expires_delta=access_token_expires,
    )
    return access_token
