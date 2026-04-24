from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Request, WebSocket
from fastapi.datastructures import Headers
from fastapi.security.oauth2 import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.ext.asyncio import AsyncSession

from config import ACCESS_TOKEN_EXPIRE, AUTH_SECRET_KEY
from lib.engine import async_session_maker
from lib.http_exceptions import NotFound, Unauthorized
from models.user_model import UserModel
from schemas.user_schemas import GetUserSchema

ALGORITHM = "HS256"


class OAuth2BearerCookie(OAuth2PasswordBearer):
    def handle_header(self, headers: Headers):
        authorization = headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            return None
        return param

    def handle_cookie(self, cookies: dict[str, str]):
        return cookies.get("token")

    async def __call__(self, request: Request = None, websocket: WebSocket = None):  # type: ignore[assignment]
        provider: Request | WebSocket | None = request or websocket
        if provider is None:
            raise Unauthorized("Unauthorized")
        token = self.handle_header(provider.headers) or self.handle_cookie(
            provider.cookies
        )
        if token is None:
            raise Unauthorized("Unauthorized")
        return token


oauth2_scheme = OAuth2BearerCookie("auth")


async def authenticate_user(session: AsyncSession, username: str, password: str):
    try:
        user = await UserModel.get_name(session, username)
    except NotFound:
        return None
    if not user.verify_password(password):
        return None
    return user


def create_access_token(data: dict[str, int | str], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = int(expire.timestamp())
    encoded_jwt = jwt.encode(to_encode, AUTH_SECRET_KEY, ALGORITHM)
    return encoded_jwt


async def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> GetUserSchema:
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")
    username: str = payload.get("sub")
    if not username:
        raise Unauthorized("Invalid token")
    async with async_session_maker.begin() as session:
        try:
            user = await UserModel.get_name(session, username)
        except NotFound:
            raise Unauthorized("User not found")
    return GetUserSchema.model_validate(user, from_attributes=True)


async def generate_token(session: AsyncSession, username: str, password: str) -> str:
    user = await authenticate_user(session, username, password)
    if not user:
        raise NotFound("User not found!")
    access_token = create_access_token(
        data={"sub": user.name},
        expires_delta=ACCESS_TOKEN_EXPIRE,
    )
    return access_token
