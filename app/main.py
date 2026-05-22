from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import auth, messenger
from app.db.session import engine, Base, SessionLocal
from app.models.user import User
from app.models.messenger import Chat, ChatParticipant, Message
from app.api.endpoints.messenger import seed_dummy_users
from sqlalchemy import inspect, text
import os
from dotenv import load_dotenv

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

# Seed dummy users
db = SessionLocal()
try:
    seed_dummy_users(db)
except Exception as e:
    print(f"Error seeding dummy users: {e}")
finally:
    db.close()

app = FastAPI(title=os.getenv("PROJECT_NAME", "aPilot API"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(messenger.router, prefix="/api/messenger", tags=["messenger"])

@app.get("/")
def read_root():
    return {"message": "Welcome to aPilot API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
