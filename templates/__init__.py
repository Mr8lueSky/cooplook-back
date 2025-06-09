from typing import Any

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from exceptions import HTTPException

env = Environment(
    loader=FileSystemLoader(searchpath="templates"),
)


def get_template_response(
    name: str, data: dict[str, Any] | None = None, exceptions: list[HTTPException] | None = None
):
    data = data or {}
    exceptions = exceptions or []
    return HTMLResponse(
        env.get_template(f"{name}.html").render(**data, exceptions=exceptions)
    )
