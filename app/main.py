from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import auth, messenger, notifications
from app.db.session import engine, Base, SessionLocal
from app.models.user import User
from app.models.messenger import Chat, ChatParticipant, Message
from app.models.notification import Notification
from sqlalchemy import inspect, text
import os
from dotenv import load_dotenv
import socketio

load_dotenv()

# Check and perform table migrations / updates
try:
    inspector = inspect(engine)
    if inspector.has_table('users'):
        columns = [col['name'] for col in inspector.get_columns('users')]
        db = SessionLocal()
        try:
            if 'avatar' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(255) NULL"))
            if 'about' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN about VARCHAR(255) NULL"))
            if 'system_user' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN system_user VARCHAR(100) NULL"))
            if 'hostname' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN hostname VARCHAR(100) NULL"))
            if 'platform' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN platform VARCHAR(50) NULL"))
            if 'os_release' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN os_release VARCHAR(50) NULL"))
            if 'arch' not in columns:
                db.execute(text("ALTER TABLE users ADD COLUMN arch VARCHAR(20) NULL"))
            db.commit()
        except Exception as e:
            print(f"Error altering users table: {e}")
            db.rollback()
        finally:
            db.close()
except Exception as e:
    print(f"Error inspecting database: {e}")

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title=os.getenv("PROJECT_NAME", "aPilot API"))

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(messenger.router, prefix="/api/messenger", tags=["messenger"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])

@app.get("/")
def read_root():
    return {"message": "Welcome to aPilot API"}

# Wrap FastAPI with Socket.IO ASGI app
# The Socket.IO server is created in messenger.py and imported here
socket_app = socketio.ASGIApp(messenger.sio, app)

if __name__ == "__main__":
    import uvicorn
    # Run the socket_app (which wraps FastAPI) so both REST and Socket.IO work
    uvicorn.run("app.main:socket_app", host="0.0.0.0", port=8000, reload=True)
