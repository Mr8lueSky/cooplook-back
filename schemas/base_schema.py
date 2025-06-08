from pydantic import BaseModel


class BaseSchema(BaseModel):
    class Config:
        str_strip_whitespace = True
