from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from starlette.requests import Request
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
import yagmail
import os

from .database import get_connection, AIDERMY_DB
from .auth import (
    get_user_by_email,
    create_user,
    verify_password,
    create_access_token,
    get_current_user,
    update_user_profile,
    create_user_oauth,
    create_user_with_verification,
    verify_user,
    resend_verification,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# === OAuth настройка ===
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# === МОДЕЛИ ===
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = ""

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    skin_type: Optional[str] = None
    age: Optional[str] = None
    concerns: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    custom_text: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    skin_type: Optional[str] = None
    age: Optional[str] = None
    concerns: List[str] = []
    allergies: List[str] = []
    custom_text: Optional[str] = None
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# === GOOGLE OAuth ===
@router.get("/google")
async def google_login(request: Request):
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:3000/api/auth/google/callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Could not get user info")
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        user = get_user_by_email(email)
        if not user:
            user_id = create_user_oauth(email, name)
            user = get_user_by_email(email)
        
        access_token = create_access_token(data={"sub": str(user['id'])})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"] or "",
                skin_type=user.get("skin_type"),
                age=user.get("age"),
                concerns=user.get("concerns", "").split(",") if user.get("concerns") else [],
                allergies=user.get("allergies", "").split(",") if user.get("allergies") else [],
                custom_text=user.get("custom_text"),
                created_at=user["created_at"]
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === РЕГИСТРАЦИЯ С ОТПРАВКОЙ ПИСЬМА ===
# === РЕГИСТРАЦИЯ С ВЕРИФИКАЦИЕЙ ===
@router.post("/register")
async def register(user_data: UserRegister):
    existing = get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует"
        )
    
    user_id, verification_token = create_user_with_verification(
        email=user_data.email,
        password=user_data.password,
        name=user_data.name
    )
    
    # === ОТПРАВКА ПИСЬМА ===
    try:
        import yagmail
        yag = yagmail.SMTP(
            user=os.getenv('EMAIL_USER'),
            password=os.getenv('EMAIL_PASSWORD'),
            host=os.getenv('EMAIL_HOST', 'smtp.gmail.com'),
            port=int(os.getenv('EMAIL_PORT', 587))
        )
        
        link = f"http://138.124.231.42/api/auth/verify?token={verification_token}"
        
        yag.send(
            to=user_data.email,
            subject="Подтверждение email — Aidermy",
            contents=f"""
            <h1>Добро пожаловать в Aidermy!</h1>
            <p>Перейдите по ссылке, чтобы подтвердить email:</p>
            <a href="{link}">{link}</a>
            <p>Ссылка действительна 24 часа.</p>
            """
        )
        print(f"✅ Письмо отправлено на {user_data.email}")
    except Exception as e:
        print(f"❌ Ошибка отправки письма: {e}")
        raise HTTPException(status_code=500, detail="Ошибка отправки письма. Попробуйте позже.")
    
    return {
        "message": "Письмо с подтверждением отправлено на ваш email. Перейдите по ссылке, чтобы активировать аккаунт.",
        "email": user_data.email
    }

# === ВЕРИФИКАЦИЯ ===
@router.get("/verify")
async def verify_email(token: str):
    success = verify_user(token)
    if success:
        return {"message": "Email успешно подтверждён!"}
    else:
        raise HTTPException(status_code=400, detail="Неверный или просроченный токен")

@router.post("/resend-verification")
async def resend_verification_email(email: EmailStr):
    new_token = resend_verification(email)
    if not new_token:
        raise HTTPException(status_code=404, detail="Пользователь не найден или уже верифицирован")
    
    print(f"🔑 Новый токен для {email}: {new_token}")
    return {"message": "Новое письмо отправлено"}

# === ЛОГИН ===
@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_email(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )
    
    if not user.get("is_verified", 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email не подтверждён. Проверьте почту."
        )
    
    if not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )
    
    access_token = create_access_token(data={"sub": str(user["id"])})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(
            id=user["id"],
            email=user["email"],
            name=user["name"] or "",
            skin_type=user.get("skin_type"),
            age=user.get("age"),
            concerns=user.get("concerns", "").split(",") if user.get("concerns") else [],
            allergies=user.get("allergies", "").split(",") if user.get("allergies") else [],
            custom_text=user.get("custom_text"),
            created_at=user["created_at"]
        )
    }
@router.get("/google/callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Could not get user info")
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        user = get_user_by_email(email)
        if not user:
            user_id = create_user_oauth(email, name)
            user = get_user_by_email(email)
        
        access_token = create_access_token(data={"sub": str(user['id'])})
        
        # РЕДИРЕКТ НА ФРОНТЕНД С ТОКЕНОМ
        redirect_url = f"http://aidermy.ru?token={access_token}"
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# === ТЕКУЩИЙ ПОЛЬЗОВАТЕЛЬ ===
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user["name"] or "",
        skin_type=current_user.get("skin_type"),
        age=current_user.get("age"),
        concerns=current_user.get("concerns", "").split(",") if current_user.get("concerns") else [],
        allergies=current_user.get("allergies", "").split(",") if current_user.get("allergies") else [],
        custom_text=current_user.get("custom_text"),
        created_at=current_user["created_at"]
    )