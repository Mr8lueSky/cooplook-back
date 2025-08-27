import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lib.http_exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    def handle_http_exception(
        _: Request, exc: HTTPException
    ):  # pyright: ignore[reportUnusedFunction]
        logger.error(f"Got an error: {type(exc)}; {exc.msg}; {exc.status_code}")
        return JSONResponse({"detail": exc.msg}, exc.status_code)

    @app.exception_handler(Exception)
    def handle_general_exception(
        _: Request, exc: Exception
    ):  # pyright: ignore[reportUnusedFunction]
        logger.error(f"Got an error: {type(exc)} {exc}")
        return JSONResponse({"detail": "Internal Server Error"}, 500)
