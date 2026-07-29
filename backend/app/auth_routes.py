from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from starlette.requests import Request
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
import yagmail
import os
import json

from .database import get_connection, AIDERMY_DB, PRODUCTS_DB
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
from .services import generate_slug

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

class PendingProductRequest(BaseModel):
    product_name: str
    ingredients: str

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
            create_user_oauth(email, name)
            user = get_user_by_email(email)
        
        access_token = create_access_token(data={"sub": str(user['id'])})
        
        redirect_url = f"http://aidermy.ru?token={access_token}"
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === РЕГИСТРАЦИЯ ===
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
    
    try:
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

# === ФУНКЦИЯ ДЛЯ PENDING ===
def save_pending_product(product_name: str, ingredients: str, user_id: int = None):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    slug = generate_slug(product_name)
    
    cursor.execute("SELECT id FROM pending_products WHERE product_name = ? AND status = 'pending'", (product_name,))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return existing['id']
    
    cursor.execute('''
        INSERT INTO pending_products (product_name, ingredients, slug, user_id, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (product_name, ingredients, slug, user_id))
    
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

# === ПОЛЬЗОВАТЕЛЬ ОТПРАВЛЯЕТ ПРОДУКТ ===
@router.post("/submit-product")
async def submit_product(
    product_data: PendingProductRequest,
    current_user: dict = Depends(get_current_user)
):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE name = ?", (product_data.product_name,))
    exists = cursor.fetchone()
    conn.close()
    
    if exists:
        raise HTTPException(
            status_code=400,
            detail="Этот продукт уже есть в базе"
        )
    
    pending_id = save_pending_product(
        product_name=product_data.product_name,
        ingredients=product_data.ingredients,
        user_id=current_user['id']
    )
    
    return {
        "message": "Продукт отправлен на модерацию. Спасибо за вклад! 🙌",
        "pending_id": pending_id
    }

# === СОХРАНЕНИЕ ПРОФИЛЯ ===
@router.post("/profile")
async def save_profile(request: Request):
    data = await request.json()
    user_id = data.get('user_id')
    profile = data.get('profile')
    
    if not user_id or not profile:
        raise HTTPException(status_code=400, detail="Missing data")
    
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    # Проверяем, есть ли таблица
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                name TEXT,
                skin_type TEXT,
                age TEXT,
                concerns TEXT,
                allergies TEXT,
                custom_text TEXT,
                quiz_answers TEXT,
                skin_type_determined TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
    
    # Сначала проверяем, есть ли запись
    cursor.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        # Обновляем
        cursor.execute('''
            UPDATE user_profiles SET
                name = ?,
                skin_type = ?,
                age = ?,
                concerns = ?,
                allergies = ?,
                custom_text = ?,
                quiz_answers = ?,
                skin_type_determined = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (
            profile.get('name'),
            profile.get('skinType'),
            profile.get('age'),
            ','.join(profile.get('concerns', [])),
            ','.join(profile.get('allergies', [])),
            profile.get('customText'),
            json.dumps(profile.get('quizAnswers', {})),
            profile.get('skinTypeDetermined'),
            user_id
        ))
    else:
        # Вставляем
        cursor.execute('''
            INSERT INTO user_profiles (user_id, name, skin_type, age, concerns, allergies, custom_text, quiz_answers, skin_type_determined)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            profile.get('name'),
            profile.get('skinType'),
            profile.get('age'),
            ','.join(profile.get('concerns', [])),
            ','.join(profile.get('allergies', [])),
            profile.get('customText'),
            json.dumps(profile.get('quizAnswers', {})),
            profile.get('skinTypeDetermined')
        ))
    
    conn.commit()
    conn.close()
    
    return {"status": "ok"}

# === МОЙ ПРОФИЛЬ ===
@router.get("/profile/me")
async def get_my_profile(request: Request):
    from .auth import get_current_user_from_token
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1] if " " in auth_header else auth_header
    user = await get_current_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT name, skin_type, age, concerns, allergies, custom_text, quiz_answers, skin_type_determined
        FROM user_profiles
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
    ''', (user['id'],))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"profile": None}
    
    return {
        "profile": {
            "name": row[0],
            "skinType": row[1],
            "age": row[2],
            "concerns": row[3].split(',') if row[3] else [],
            "allergies": row[4].split(',') if row[4] else [],
            "customText": row[5],
            "quizAnswers": json.loads(row[6]) if row[6] else {},
            "skinTypeDetermined": row[7]
        }
    }
# === ИСТОРИЯ ===
# === ИСТОРИЯ ===
@router.post("/history")
async def save_history(request: Request):
    data = await request.json()
    user_id = data.get('user_id')
    result = data.get('result')
    
    if not user_id or not result:
        raise HTTPException(status_code=400, detail="Missing data")
    
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO check_history (user_id, product_name, skin_type, score, verdict, summary, ingredients, slug, image_url, active_ingredients, how_to_use, expectations, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (
        user_id,
        result.get('product'),
        result.get('skinType'),
        result.get('score'),
        result.get('verdict'),
        result.get('summary'),
        result.get('ingredients'),
        result.get('slug'),
        result.get('image_url'),
        json.dumps(result.get('active_ingredients')),
        json.dumps(result.get('how_to_use')),
        json.dumps(result.get('expectations'))
    ))
    
    conn.commit()
    conn.close()
    
    return {"status": "ok"}

# auth_routes.py

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    """Получить историю проверок текущего пользователя"""
    from .database import get_user_check_history
    
    history = get_user_check_history(current_user['id'])
    return {"history": history}