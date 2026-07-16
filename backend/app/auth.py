from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import hashlib
import secrets
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from .database import get_connection, AIDERMY_DB
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# === ХЕШИРОВАНИЕ ПАРОЛЯ ===
def get_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    salt, hash_value = hashed_password.split(":")
    return hashlib.sha256((salt + plain_password).encode()).hexdigest() == hash_value

# === JWT ===
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# === ПОЛУЧЕНИЕ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ ===
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    
    return dict(user)

# === РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ===
def get_user_by_email(email: str):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(email: str, password: str, name: str = ""):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    hashed_password = get_password_hash(password)
    
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (email.lower().strip(), hashed_password, name.strip()))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except Exception as e:
        conn.close()
        raise e

def create_user_oauth(email: str, name: str = ""):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (email.lower().strip(), 'oauth_user', name.strip()))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except Exception as e:
        conn.close()
        raise e

def update_user_profile(user_id: int, data: dict):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    allowed_fields = ["name", "skin_type", "age", "concerns", "allergies", "custom_text"]
    updates = []
    values = []
    
    for field in allowed_fields:
        if field in data and data[field] is not None:
            updates.append(f"{field} = ?")
            if field in ["concerns", "allergies"] and isinstance(data[field], list):
                values.append(','.join(data[field]))
            else:
                values.append(data[field])
    
    if not updates:
        return
    
    values.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()
