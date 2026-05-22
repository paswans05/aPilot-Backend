from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional
import uuid
import asyncio
from datetime import datetime
from jose import jwt, JWTError

from app.db.session import get_db, SessionLocal
from app.models.user import User
from app.models.messenger import Chat, ChatParticipant, Message
from app.schemas.messenger import (
    Contact, ContactDetails, EmailDetail, PhoneNumberDetail,
    ChatOut, ChatCreate, MessageOut, MessageCreate, ProfileOut, ProfileUpdate
)
from app.api.deps import get_current_user, SECRET_KEY, ALGORITHM

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast_status(self, user_id: str, status: str):
        payload = {
            "type": "status_update",
            "contactId": user_id,
            "status": status
        }
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json(payload)
                except Exception:
                    pass

    async def send_chat_message(self, chat_id: str, message: dict, sender_id: str, participant_ids: list[str]):
        payload = {
            "type": "new_message",
            "chatId": chat_id,
            "message": message
        }
        for pid in participant_ids:
            if pid in self.active_connections:
                for connection in self.active_connections[pid]:
                    try:
                        await connection.send_json(payload)
                    except Exception:
                        pass

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    db = SessionLocal()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    finally:
        db.close()

    user_id = str(user.id)
    await manager.connect(user_id, websocket)
    await manager.broadcast_status(user_id, "online")

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "send_message":
                chat_id = data.get("chatId")
                value = data.get("value")
                msg_id = data.get("id") or str(uuid.uuid4())
                
                db = SessionLocal()
                try:
                    part = db.query(ChatParticipant).filter(
                        ChatParticipant.chat_id == chat_id,
                        ChatParticipant.user_id == user.id
                    ).first()
                    if part:
                        db_message = Message(
                            id=msg_id,
                            chat_id=chat_id,
                            contact_id=user.id,
                            value=value
                        )
                        db.add(db_message)
                        db.commit()
                        
                        participants = db.query(ChatParticipant).filter(
                            ChatParticipant.chat_id == chat_id
                        ).all()
                        pids = [str(p.user_id) for p in participants]
                        msg_out = message_to_out(db_message)
                        await manager.send_chat_message(chat_id, msg_out.model_dump(), user_id, pids)
                except Exception as e:
                    print(f"Error handling WS message: {e}")
                finally:
                    db.close()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        await manager.broadcast_status(user_id, "offline")

def user_to_contact(user: User, status: str = "online") -> Contact:
    return Contact(
        id=str(user.id),
        avatar=user.avatar,
        name=user.display_name,
        about=user.about or "Hi there! I'm using aPilot Chat.",
        status=status,
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
    return [user_to_contact(u, "online" if str(u.id) in manager.active_connections else "offline") for u in users]

@router.get("/contacts/{contact_id}", response_model=Contact)
def get_contact(contact_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        uid = int(contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid contact ID")
        
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Contact not found")
    status_val = "online" if str(user.id) in manager.active_connections else "offline"
    return user_to_contact(user, status_val)

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
    
    # Broadcast message to all active participants via WebSocket
    participants = db.query(ChatParticipant).filter(ChatParticipant.chat_id == msg_in.chatId).all()
    pids = [str(p.user_id) for p in participants]
    msg_out = message_to_out(db_message)
    asyncio.create_task(manager.send_chat_message(msg_in.chatId, msg_out.model_dump(), str(current_user.id), pids))
    
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
