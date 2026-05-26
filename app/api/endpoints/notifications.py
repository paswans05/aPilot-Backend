from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.db.session import get_db
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationOut
from app.api.deps import get_current_user

router = APIRouter()

@router.get("", response_model=List[NotificationOut])
def get_all_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retrieve all notifications for the current authenticated user."""
    notifications = db.query(Notification).filter(Notification.user_id == current_user.id).all()
    return notifications

@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def create_notification(notification: NotificationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new notification for the current user."""
    notif_id = notification.id or str(uuid.uuid4())
    db_notif = Notification(
        id=notif_id,
        user_id=current_user.id,
        icon=notification.icon,
        title=notification.title,
        description=notification.description,
        time=notification.time,
        read=notification.read,
        link=notification.link,
        use_router=notification.useRouter,
        variant=notification.variant,
        image=notification.image
    )
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    return db_notif

@router.delete("")
def delete_notifications(notification_ids: List[str], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete multiple notifications by their IDs."""
    db.query(Notification).filter(
        Notification.id.in_(notification_ids),
        Notification.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.commit()
    return {"success": True}

@router.get("/{id}", response_model=NotificationOut)
def get_notification(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retrieve a single notification by ID."""
    notification = db.query(Notification).filter(
        Notification.id == id,
        Notification.user_id == current_user.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.delete("/{id}")
def delete_notification(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a single notification by ID."""
    notification = db.query(Notification).filter(
        Notification.id == id,
        Notification.user_id == current_user.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(notification)
    db.commit()
    return {"message": "Deleted successfully"}
