from enum import Enum


class Severity(str, Enum):
    error = "error"
    warning = "warning"


class HTTPException(Exception):
    status_code = 200

    def __init__(self, msg: str, html: bool = True, severity: Severity = Severity.error) -> None:
        super().__init__()
        self.msg = msg
        self.html = html
        self.severity = severity

class NotFound(HTTPException):
    status_code = 404


class BadRequest(HTTPException):
    status_code = 400


class UnprocessableEntity(HTTPException):
    status_code = 422


class ContentTooLarge(HTTPException):
    status_code = 413

