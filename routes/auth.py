from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from fastapi.security.oauth2 import OAuth2PasswordRequestForm

from lib.auth import current_user, generate_token
from lib.engine import async_session_maker
from lib.http_exceptions import BadRequest, HTTPException
from schemas.auth_schemas import TokenSchema
from schemas.user_schemas import GetUserSchema

auth_router = APIRouter(prefix="/auth")

CurrentUserDep = Annotated[GetUserSchema, Depends(current_user)]


@auth_router.get("/me")
async def me(user: CurrentUserDep) -> GetUserSchema:
    return user


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"detail": "Logged out"}


@auth_router.post("")
async def auth(
    user: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
) -> TokenSchema:
    async with async_session_maker.begin() as session:
        try:
            token = await generate_token(session, user.username, user.password)
        except (HTTPException, RequestValidationError):
            raise BadRequest("Incorrect username or password!")
    response.set_cookie("token", token, httponly=True, samesite="lax")
    return TokenSchema(access_token=token)
