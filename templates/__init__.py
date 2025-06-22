from typing import Any

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, Template

from config import ENV

env = Environment(
    loader=FileSystemLoader(searchpath="templates/v2"),
)

templates = {}


def get_template(name: str) -> Template:
    return env.get_template(f"{name}.html")


def get_template_response(
    name: str,
    data: dict[str, Any] | None = None,
):
    data = data or {}
    if ENV == "DEV":
        return HTMLResponse(get_template(name).render(**data))
    if name not in templates:
        templates[name] = get_template(name)
    return HTMLResponse(templates[name].render(**data))
