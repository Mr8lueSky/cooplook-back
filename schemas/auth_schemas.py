from schemas.base_schema import BaseSchema


class TokenSchema(BaseSchema):
    access_token: str
    token_type: str = "bearer"
