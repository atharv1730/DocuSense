"""
FastAPI auth dependency for NextAuth JWTs.

Validates the Bearer token with NEXTAUTH_SECRET (HS256), requires an email
claim, upserts the Google user into the users table, and returns that row
for protected routes via get_current_user.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.db import get_db
import uuid

bearer_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.NEXTAUTH_SECRET,
            algorithms=["HS256"],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    email = payload.get("email")
    name = payload.get("name")
    image = payload.get("picture")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing email claim",
        )

    # Upsert user on every authenticated request
    await db.execute(
        text("""
            INSERT INTO users (id, email, name, image, provider)
            VALUES (:id, :email, :name, :image, 'google')
            ON CONFLICT (email) DO UPDATE
            SET name = EXCLUDED.name,
                image = EXCLUDED.image,
                updated_at = now()
        """),
        {"id": str(uuid.uuid4()), "email": email, "name": name, "image": image},
    )
    await db.commit()

    result = await db.execute(
        text("SELECT id, email, name FROM users WHERE email = :email"),
        {"email": email},
    )
    user = result.mappings().one()
    return dict(user)