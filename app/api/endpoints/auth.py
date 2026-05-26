from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, Token, UserOut, LoginResponse, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token

from app.api.deps import get_current_user

router = APIRouter()

@router.get("/me", response_model=UserOut)
def read_user_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/user/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, 
    user_in: UserUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure users can only update their own profile (or admin)
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    
    if "displayName" in update_data:
        update_data["display_name"] = update_data.pop("displayName")
        
    for field, value in update_data.items():
        setattr(user, field, value)
        
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/register", response_model=LoginResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        if verify_password(user_in.password, user.hashed_password):
            access_token = create_access_token(user.email)
            user.access_token = access_token
            db.add(user)
            db.commit()
            db.refresh(user)
            return {
                "user": user,
                "access_token": access_token
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system.",
            )
    
    new_user = User(
        email=user_in.email,
        display_name=user_in.displayName,
        hashed_password=get_password_hash(user_in.password),
        system_user=user_in.system_user,
        hostname=user_in.hostname,
        platform=user_in.platform,
        os_release=user_in.os_release,
        arch=user_in.arch,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token(new_user.email)
    new_user.access_token = access_token
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "user": new_user,
        "access_token": access_token
    }

@router.post("/login", response_model=LoginResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token = create_access_token(user.email)
    user.access_token = access_token
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {
        "user": user,
        "access_token": access_token
    }
