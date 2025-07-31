import bcrypt
from pydantic import Field

from config import PW_SECRET_KET
from schemas.base_schema import BaseSchema

UsernameField = Field(min_length=3, max_length=31, pattern=r"[a-zA-Z ,./|\\?!:0-9]*")
PasswordField = Field(max_length=64)


class GetUserSchema(BaseSchema):
    name: str = UsernameField


class LoginUserSchema(BaseSchema):
    username: str = UsernameField
    password: str = PasswordField
    salt: bytes = Field(
        init=False,
        init_var=False,
        exclude=True,
        default_factory=lambda: bcrypt.gensalt(),
    )

    def hash_password(self) -> bytes:
        return bcrypt.hashpw(
            bytes(self.password, "utf-8") + self.salt + PW_SECRET_KET, self.salt
        )
