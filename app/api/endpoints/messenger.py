from fastapi import APIRouter, Depends, HTTPException, status
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

import socketio

router = APIRouter()

# ── Socket.IO Server ────────────────────────────────────────────────────────

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=False,
    engineio_logger=False
)

# Track online users: { user_id_str: set(sid, ...) }
online_users: dict[str, set[str]] = {}
# Map sid -> user_id_str for quick disconnect lookup
sid_to_user: dict[str, str] = {}


@sio.event
async def connect(sid, environ, auth):
    """Authenticate user via JWT token on Socket.IO connect."""
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get('token')

    if not token:
        # Try query string fallback
        query_string = environ.get('QUERY_STRING', '')
        for part in query_string.split('&'):
            if part.startswith('token='):
                token = part[6:]
                break

    if not token:
        raise socketio.exceptions.ConnectionRefusedError('Authentication required')

    db = SessionLocal()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise socketio.exceptions.ConnectionRefusedError('Invalid token')

        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise socketio.exceptions.ConnectionRefusedError('User not found')

        user_id = str(user.id)
        user_name = user.display_name or user.email

    except JWTError:
        raise socketio.exceptions.ConnectionRefusedError('Invalid token')
    finally:
        db.close()

    # Store user mapping
    sid_to_user[sid] = user_id
    if user_id not in online_users:
        online_users[user_id] = set()
    online_users[user_id].add(sid)

    # Join personal room for targeted messages
    await sio.enter_room(sid, f'user_{user_id}')

    # Save session data
    await sio.save_session(sid, {
        'user_id': user_id,
        'user_name': user_name
    })

    # Broadcast online status to all connected clients
    await sio.emit('status_update', {
        'contactId': user_id,
        'status': 'online'
    })

    # Send currently online users list to the newly connected client
    # so they see who is already online
    online_list = [uid for uid in online_users if uid != user_id]
    if online_list:
        await sio.emit('online_users_list', {
            'onlineUserIds': online_list
        }, to=sid)

    # Join all chat rooms for this user
    db = SessionLocal()
    try:
        participations = db.query(ChatParticipant).filter(
            ChatParticipant.user_id == int(user_id)
        ).all()
        for p in participations:
            await sio.enter_room(sid, f'chat_{p.chat_id}')
    finally:
        db.close()

    print(f'Socket.IO: {user_name} connected (sid={sid})')


@sio.event
async def disconnect(sid):
    """Handle user disconnect, broadcast offline status."""
    user_id = sid_to_user.pop(sid, None)
    if user_id:
        if user_id in online_users:
            online_users[user_id].discard(sid)
            if not online_users[user_id]:
                del online_users[user_id]
                # Only broadcast offline if no more connections for this user
                await sio.emit('status_update', {
                    'contactId': user_id,
                    'status': 'offline'
                })
        print(f'Socket.IO: user {user_id} disconnected (sid={sid})')


@sio.event
async def join_chat(sid, chat_id):
    """Join a specific chat room."""
    session = await sio.get_session(sid)
    if not session:
        return

    user_id = session['user_id']

    # Verify user is a participant
    db = SessionLocal()
    try:
        part = db.query(ChatParticipant).filter(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == int(user_id)
        ).first()
        if part:
            await sio.enter_room(sid, f'chat_{chat_id}')
    finally:
        db.close()


@sio.event
async def send_message(sid, data):
    """Handle incoming chat message, save to DB, broadcast to room."""
    session = await sio.get_session(sid)
    if not session:
        return

    user_id = session['user_id']
    chat_id = data.get('chatId')
    value = data.get('value')
    msg_id = data.get('id') or str(uuid.uuid4())

    if not chat_id or not value:
        return

    db = SessionLocal()
    try:
        # Verify participant
        part = db.query(ChatParticipant).filter(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == int(user_id)
        ).first()
        if not part:
            return

        # Save message to database
        db_message = Message(
            id=msg_id,
            chat_id=chat_id,
            contact_id=int(user_id),
            value=value
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)

        msg_out = message_to_out(db_message).model_dump()

        # Broadcast to all participants in the chat room
        await sio.emit('new_message', {
            'chatId': chat_id,
            'message': msg_out
        }, room=f'chat_{chat_id}')

    except Exception as e:
        print(f"Error handling send_message: {e}")
    finally:
        db.close()


@sio.event
async def typing(sid, data):
    """Broadcast typing indicator to chat room."""
    session = await sio.get_session(sid)
    if not session:
        return

    chat_id = data.get('chatId') if isinstance(data, dict) else data
    if not chat_id:
        return

    await sio.emit('user_typing', {
        'chatId': chat_id,
        'userId': session['user_id'],
        'userName': session['user_name']
    }, room=f'chat_{chat_id}', skip_sid=sid)


@sio.event
async def stop_typing(sid, data):
    """Broadcast stop-typing to chat room."""
    session = await sio.get_session(sid)
    if not session:
        return

    chat_id = data.get('chatId') if isinstance(data, dict) else data
    if not chat_id:
        return

    await sio.emit('user_stop_typing', {
        'chatId': chat_id,
        'userId': session['user_id']
    }, room=f'chat_{chat_id}', skip_sid=sid)


# ── Helper functions ─────────────────────────────────────────────────────────

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

# ── REST Endpoints (kept for compatibility) ──────────────────────────────────

@router.get("/contacts", response_model=List[Contact])
def get_contacts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = db.query(User).filter(User.id != current_user.id).all()
    return [user_to_contact(u, "online" if str(u.id) in online_users else "offline") for u in users]

@router.get("/contacts/{contact_id}", response_model=Contact)
def get_contact(contact_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        uid = int(contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid contact ID")
        
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Contact not found")
    status_val = "online" if str(user.id) in online_users else "offline"
    return user_to_contact(user, status_val)

@router.get("/chat-list", response_model=List[ChatOut])
def get_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chats = (
        db.query(Chat)
        .join(ChatParticipant)
        .filter(ChatParticipant.user_id == current_user.id)
        .all()
    )
    return [chat_to_out(c, db) for c in chats]

@router.post("/chat-list", response_model=ChatOut)
async def create_chat(chat_in: ChatCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
		user_exists = db.query(User).filter(User.id == pid).first()
		if user_exists:
			part = ChatParticipant(chat_id=chat_id, user_id=pid)
			db.add(part)
			
	db.commit()
	db.refresh(new_chat)

	# Auto-join connected participants to the new chat room
	for pid in target_set:
		pid_str = str(pid)
		if pid_str in online_users:
			for user_sid in online_users[pid_str]:
				await sio.enter_room(user_sid, f'chat_{chat_id}')

	return chat_to_out(new_chat, db)

@router.get("/messages", response_model=List[MessageOut])
def get_messages(chatId: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    part = db.query(ChatParticipant).filter(
        ChatParticipant.chat_id == chatId,
        ChatParticipant.user_id == current_user.id
    ).first()
    if not part:
        raise HTTPException(status_code=403, detail="You are not a participant in this chat")
        
    messages = db.query(Message).filter(Message.chat_id == chatId).order_by(Message.created_at.asc()).all()
    return [message_to_out(m) for m in messages]

@router.post("/messages", response_model=List[MessageOut])
async def send_message_rest(msg_in: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	"""REST fallback for sending messages. Primary path is Socket.IO."""
	part = db.query(ChatParticipant).filter(
		ChatParticipant.chat_id == msg_in.chatId,
		ChatParticipant.user_id == current_user.id
	).first()
	if not part:
		raise HTTPException(status_code=403, detail="You are not a participant in this chat")
		
	msg_id = msg_in.id
	if not msg_id or len(msg_id) < 32:
		msg_id = str(uuid.uuid4())
	db_message = Message(
		id=msg_id,
		chat_id=msg_in.chatId,
		contact_id=current_user.id,
		value=msg_in.value
	)
	db.add(db_message)
	db.commit()
	
	# Broadcast via Socket.IO to all participants
	participants = db.query(ChatParticipant).filter(ChatParticipant.chat_id == msg_in.chatId).all()
	msg_out = message_to_out(db_message)
	await sio.emit('new_message', {
		'chatId': msg_in.chatId,
		'message': msg_out.model_dump()
	}, room=f'chat_{msg_in.chatId}')
	
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
