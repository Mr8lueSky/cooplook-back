class HTTPException(Exception):
    status_code: int = 200

    def __init__(self, msg: str) -> None:
        super().__init__()
        self.msg: str = msg


class NotFound(HTTPException):
    status_code: int = 404


class BadRequest(HTTPException):
    status_code: int = 400


class Unauthorized(HTTPException):
    status_code: int = 401


class UnprocessableEntity(HTTPException):
    status_code: int = 422


class ContentTooLarge(HTTPException):
    status_code: int = 413
