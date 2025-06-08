class HTTPException(Exception):
    status_code = 200

    def __init__(self, msg: str, html=True) -> None:
        self.msg = msg
        self.html = html

class NotFound(HTTPException):
    status_code = 404


class BadRequest(HTTPException):
    status_code = 400


class UnprocessableEntity(HTTPException):
    status_code = 422


class ContentTooLarge(HTTPException):
    status_code = 413

