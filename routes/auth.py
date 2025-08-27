from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.security.oauth2 import OAuth2PasswordRequestForm

from lib.auth import current_user, generate_token
from lib.engine import async_session_maker
from lib.http_exceptions import BadRequest, HTTPException
from schemas.user_schemas import GetUserSchema
from schemas.auth_schemas import TokenSchema

auth_router = APIRouter()


@auth_router.get("/me")
async def me(
    user: GetUserSchema = Depends(
        current_user
    ),  # pyright: ignore[reportCallInDefaultInitializer]
) -> GetUserSchema:
    return user


@auth_router.post("")
async def auth(
    user: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response
):
    async with async_session_maker.begin() as session:
        try:
            token = await generate_token(session, user.username, user.password)
        except (HTTPException, RequestValidationError):
            raise BadRequest("Incorrect username or password!")
    response.set_cookie(
        "token",
        token,
        httponly=True,
    )
    return TokenSchema(access_token=token)
