from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    displayName: str = Field(validation_alias="display_name")

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    displayName: str = Field(validation_alias="display_name")
    is_active: bool
    created_at: datetime
    role: str = "user"

    class Config:
        from_attributes = True
        populate_by_name = True

class LoginResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"
