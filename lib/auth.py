from datetime import datetime, timedelta, timezone
from typing import Annotated, override

from fastapi.security.oauth2 import OAuth2PasswordBearer
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config import ACCESS_TOKEN_EXPIRE, AUTH_SECRET_KEY
from lib.engine import async_session_maker
from lib.http_exceptions import NotFound
from models.user_model import UserModel
from schemas.user_schemas import GetUserSchema


ALGORITHM = "HS256"


class OAuth2BearerCookie(OAuth2PasswordBearer):
    @override
    async def __call__(self, request: Request) -> str | None:
        token = None
        try:
            token = await super().__call__(request)
        except HTTPException:
            token = request.cookies.get("token")
        if token is None:
            raise HTTPException(401, "Not authenticated")
        return token


oauth2_scheme = OAuth2BearerCookie("auth")


async def authenticate_user(session: AsyncSession, username: str, password: str):
    user = await UserModel.get_name(session, username)
    if not user:
        return False
    if not user.verify_password(password):
        return False
    return user


def create_access_token(data: dict[str, int | str], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = int(expire.timestamp())
    encoded_jwt = jwt.encode(to_encode, AUTH_SECRET_KEY, ALGORITHM)
    return encoded_jwt


async def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> GetUserSchema:
    unauthorized_resp = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, ALGORITHM)
        username: str = payload.get("sub")
    except jwt.InvalidTokenError:
        raise unauthorized_resp
    async with async_session_maker.begin() as session:
        try:
            user = await UserModel.get_name(session, username)
        except NotFound:
            raise unauthorized_resp
    return GetUserSchema.model_validate(user, from_attributes=True)


async def generate_token(session: AsyncSession, username: str, password: str):
    user = await authenticate_user(session, username, password)
    if not user:
        raise NotFound("User not found!")
    access_token = create_access_token(
        data={"sub": user.name},
        expires_delta=ACCESS_TOKEN_EXPIRE,
    )
    return access_token
