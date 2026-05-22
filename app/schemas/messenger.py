from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional

class EmailDetail(BaseModel):
    email: str
    label: str

class PhoneNumberDetail(BaseModel):
    country: str
    phoneNumber: str = Field(alias="phoneNumber")
    label: str
    
    model_config = ConfigDict(populate_by_name=True)

class ContactDetails(BaseModel):
    emails: List[EmailDetail] = []
    phoneNumbers: List[PhoneNumberDetail] = []
    title: Optional[str] = None
    company: str = "aPilot"
    birthday: str = "1990-01-01"
    address: str = "San Francisco, CA"

class ContactAttachments(BaseModel):
    media: List[str] = []
    docs: List[str] = []
    links: List[str] = []

class Contact(BaseModel):
    id: str
    avatar: Optional[str] = None
    name: str
    about: str
    details: ContactDetails
    attachments: ContactAttachments = Field(default_factory=ContactAttachments)
    status: str = "online"

class ChatOut(BaseModel):
    id: str
    contactIds: List[str] = Field(alias="contactIds")
    unreadCount: int = Field(alias="unreadCount", default=0)
    muted: bool
    lastMessage: str = Field(alias="lastMessage", default="")
    lastMessageAt: str = Field(alias="lastMessageAt", default="")

    model_config = ConfigDict(populate_by_name=True)

class ChatCreate(BaseModel):
    contactIds: List[str] = Field(alias="contactIds")
    
    model_config = ConfigDict(populate_by_name=True)

class MessageOut(BaseModel):
    id: str
    chatId: str = Field(alias="chatId")
    contactId: str = Field(alias="contactId")
    value: str
    createdAt: str = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)

class MessageCreate(BaseModel):
    id: Optional[str] = None
    chatId: str = Field(alias="chatId")
    contactId: Optional[str] = Field(alias="contactId", default=None)
    value: str

    model_config = ConfigDict(populate_by_name=True)

class ProfileOut(BaseModel):
    id: str
    name: str
    email: str
    avatar: Optional[str] = None
    about: Optional[str] = None

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar: Optional[str] = None
    about: Optional[str] = None
