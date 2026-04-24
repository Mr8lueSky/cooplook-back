import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from lib.http_exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    def handle_http_exception(_: Request, exc: HTTPException):
        logger.error(f"Got an error: {type(exc)}; {exc.msg}; {exc.status_code}")
        return JSONResponse({"detail": exc.msg}, exc.status_code)

    @app.exception_handler(FastAPIHTTPException)
    def handle_fastapi_http_exception(_: Request, exc: FastAPIHTTPException):
        logger.error(f"Got an error: {type(exc)}; {exc.detail}; {exc.status_code}")
        return JSONResponse({"detail": exc.detail}, exc.status_code)

    @app.exception_handler(Exception)
    def handle_general_exception(_: Request, exc: Exception):
        logger.error(f"Got an error: {type(exc)} {exc}")
        return JSONResponse({"detail": "Internal Server Error"}, 500)
