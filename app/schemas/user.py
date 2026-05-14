from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    displayName: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    displayName: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str = Field(alias="displayName")
    is_active: bool
    access_token: Optional[str] = None
    created_at: datetime
    role: str = "admin"

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class LoginResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"
