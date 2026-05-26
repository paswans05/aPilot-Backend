from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class NotificationBase(BaseModel):
    icon: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    time: Optional[str] = None
    read: bool = False
    link: Optional[str] = None
    useRouter: bool = Field(default=False, serialization_alias="useRouter", validation_alias="use_router")
    variant: Optional[str] = None
    image: Optional[str] = None

class NotificationCreate(NotificationBase):
    id: Optional[str] = None

class NotificationOut(NotificationBase):
    id: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
