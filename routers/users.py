from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from database import get_db
from schemas import UserCreate, UserInDB, Token, Checkout
from models import User
from auth import get_password_hash, authenticate_user, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/users", tags=["Пользователи"])


@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username уже занят")
    hashed_password = get_password_hash(user.password)
    new_user = User(
        username=user.username,
        hashed_password=hashed_password,
        delivery_address=user.delivery_address,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Пользователь зарегистрирован"}


@router.post('/login', response_model=Token)
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail='Неверный логин или пароль')

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    response.set_cookie(key='access_token', value=access_token, httponly=True, max_age=60*60*24, path='/')
    return {"access_token": access_token, "token_type": "bearer"}


@router.post('/logout')
def logout(response: Response):
    # Удаляем cookie access_token на сервере (HttpOnly)
    response.delete_cookie(key='access_token', path='/')
    return {"message": "Вы вышли"}


@router.get("/me", response_model=UserInDB)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/address")
def update_address(
    address: Checkout, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    current_user.delivery_address = address.delivery_address
    db.commit()
    return {"message": "Адрес обновлён"}