from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional
import uuid
from datetime import datetime

from app.db.session import get_db
from app.models.user import User
from app.models.messenger import Chat, ChatParticipant, Message
from app.schemas.messenger import (
    Contact, ContactDetails, EmailDetail, PhoneNumberDetail,
    ChatOut, ChatCreate, MessageOut, MessageCreate, ProfileOut, ProfileUpdate
)
from app.api.deps import get_current_user
from app.core.security import get_password_hash

router = APIRouter()

def user_to_contact(user: User) -> Contact:
    return Contact(
        id=str(user.id),
        avatar=user.avatar,
        name=user.display_name,
        about=user.about or "Hi there! I'm using aPilot Chat.",
        status="online",
        details=ContactDetails(
            emails=[EmailDetail(email=user.email, label="Work")],
            phoneNumbers=[PhoneNumberDetail(phoneNumber="123 456 7890", country="us", label="Work")],
            title="aPilot Member",
            company="aPilot",
            birthday="1990-01-01T12:00:00.000Z",
            address="San Francisco, CA"
        )
    )

def chat_to_out(chat: Chat, db: Session) -> ChatOut:
    contact_ids = [str(p.user_id) for p in chat.participants]
    
    # Find last message
    last_msg = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.desc()).first()
    
    last_message_val = ""
    last_message_at = chat.created_at.isoformat() + "Z"
    
    if last_msg:
        last_message_val = last_msg.value
        if last_msg.created_at:
            last_message_at = last_msg.created_at.isoformat() + "Z"

    return ChatOut(
        id=chat.id,
        contactIds=contact_ids,
        unreadCount=0,
        muted=chat.muted,
        lastMessage=last_message_val,
        lastMessageAt=last_message_at
    )

def message_to_out(msg: Message) -> MessageOut:
    created_at_str = msg.created_at.isoformat() + "Z" if msg.created_at else datetime.now().isoformat() + "Z"
    return MessageOut(
        id=msg.id,
        chatId=msg.chat_id,
        contactId=str(msg.contact_id),
        value=msg.value,
        createdAt=created_at_str
    )

# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/contacts", response_model=List[Contact])
def get_contacts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = db.query(User).filter(User.id != current_user.id).all()
    return [user_to_contact(u) for u in users]

@router.get("/contacts/{contact_id}", response_model=Contact)
def get_contact(contact_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        uid = int(contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid contact ID")
        
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Contact not found")
    return user_to_contact(user)

@router.get("/chat-list", response_model=List[ChatOut])
def get_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Get all chats where current user is a participant
    chats = (
        db.query(Chat)
        .join(ChatParticipant)
        .filter(ChatParticipant.user_id == current_user.id)
        .all()
    )
    return [chat_to_out(c, db) for c in chats]

@router.post("/chat-list", response_model=ChatOut)
def create_chat(chat_in: ChatCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        participant_ids = [int(cid) for cid in chat_in.contactIds]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid participant IDs")
        
    if current_user.id not in participant_ids:
        participant_ids.append(current_user.id)
        
    # Check if chat already exists with exactly these participants
    user_chats = (
        db.query(Chat)
        .join(ChatParticipant)
        .filter(ChatParticipant.user_id == current_user.id)
        .all()
    )
    existing_chat = None
    target_set = set(participant_ids)
    
    for c in user_chats:
        chat_part_ids = {p.user_id for p in c.participants}
        if chat_part_ids == target_set:
            existing_chat = c
            break
            
    if existing_chat:
        return chat_to_out(existing_chat, db)
        
    # Create new chat
    chat_id = str(uuid.uuid4())
    new_chat = Chat(id=chat_id)
    db.add(new_chat)
    db.commit()
    
    # Add participants
    for pid in target_set:
        # Verify user exists
        user_exists = db.query(User).filter(User.id == pid).first()
        if user_exists:
            part = ChatParticipant(chat_id=chat_id, user_id=pid)
            db.add(part)
            
    db.commit()
    db.refresh(new_chat)
    return chat_to_out(new_chat, db)

@router.get("/messages", response_model=List[MessageOut])
def get_messages(chatId: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify participant
    part = db.query(ChatParticipant).filter(
        ChatParticipant.chat_id == chatId,
        ChatParticipant.user_id == current_user.id
    ).first()
    if not part:
        raise HTTPException(status_code=403, detail="You are not a participant in this chat")
        
    messages = db.query(Message).filter(Message.chat_id == chatId).order_by(Message.created_at.asc()).all()
    return [message_to_out(m) for m in messages]

@router.post("/messages", response_model=List[MessageOut])
def send_message(msg_in: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify participant
    part = db.query(ChatParticipant).filter(
        ChatParticipant.chat_id == msg_in.chatId,
        ChatParticipant.user_id == current_user.id
    ).first()
    if not part:
        raise HTTPException(status_code=403, detail="You are not a participant in this chat")
        
    msg_id = msg_in.id or str(uuid.uuid4())
    db_message = Message(
        id=msg_id,
        chat_id=msg_in.chatId,
        contact_id=current_user.id,
        value=msg_in.value
    )
    db.add(db_message)
    db.commit()
    
    # Return all messages in chat
    messages = db.query(Message).filter(Message.chat_id == msg_in.chatId).order_by(Message.created_at.asc()).all()
    return [message_to_out(m) for m in messages]

@router.get("/profile/me", response_model=ProfileOut)
def get_profile_me(current_user: User = Depends(get_current_user)):
    return ProfileOut(
        id=str(current_user.id),
        name=current_user.display_name,
        email=current_user.email,
        avatar=current_user.avatar,
        about=current_user.about
    )

@router.put("/profile/me", response_model=ProfileOut)
def update_profile_me(profile_in: ProfileUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if profile_in.name is not None:
        user.display_name = profile_in.name
    if profile_in.email is not None:
        user.email = profile_in.email
    if profile_in.avatar is not None:
        user.avatar = profile_in.avatar
    if profile_in.about is not None:
        user.about = profile_in.about
        
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return ProfileOut(
        id=str(user.id),
        name=user.display_name,
        email=user.email,
        avatar=user.avatar,
        about=user.about
    )

# ── Seeding ───────────────────────────────────────────────────────────────

def seed_dummy_users(db: Session):
    dummy_contacts = [
        {
            "email": "dejesusmichael@mail.org",
            "name": "Dejesus Michael",
            "avatar": "/assets/images/avatars/male-01.jpg",
            "about": "Hi there! I'm using aPilot Chat."
        },
        {
            "email": "denamolina@mail.us",
            "name": "Dena Molina",
            "avatar": "/assets/images/avatars/female-01.jpg",
            "about": "Always online and ready to help."
        },
        {
            "email": "bernardlangley@mail.com",
            "name": "Bernard Langley",
            "avatar": "/assets/images/avatars/male-02.jpg",
            "about": "Let's build something awesome today."
        },
        {
            "email": "trudyberg@mail.us",
            "name": "Trudy Berg",
            "avatar": "/assets/images/avatars/female-03.jpg",
            "about": "Frontend developer & UI enthusiast."
        }
    ]
    
    dummy_password_hash = get_password_hash("default_dummy_password_123")
    
    for contact in dummy_contacts:
        user = db.query(User).filter(User.email == contact["email"]).first()
        if not user:
            new_user = User(
                email=contact["email"],
                display_name=contact["name"],
                hashed_password=dummy_password_hash,
                avatar=contact["avatar"],
                about=contact["about"],
                is_active=True
            )
            db.add(new_user)
    db.commit()
