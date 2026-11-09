from typing import Annotated

from pydantic import BaseModel, Field

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.schemas.common import Email

NewPassword = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]


class LoginRequest(BaseModel):
    email: Email
    # No minimum here: the login form must not reveal or depend on the password policy.
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    old_password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]
    new_password: NewPassword
