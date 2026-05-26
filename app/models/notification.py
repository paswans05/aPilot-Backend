from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(50), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    icon = Column(String(100), nullable=True)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    time = Column(String(100), nullable=True)
    read = Column(Boolean, default=False)
    link = Column(String(255), nullable=True)
    use_router = Column(Boolean, default=False)
    variant = Column(String(50), nullable=True)
    image = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
