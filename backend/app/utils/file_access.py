from datetime import datetime, timedelta

from fastapi import HTTPException
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()
ANSWER_FILE_ACCESS_SCOPE = "homework_answer_file"
ANSWER_FILE_ACCESS_EXPIRE_MINUTES = 5


def create_answer_file_access_token(payload: dict, expires_minutes: int = ANSWER_FILE_ACCESS_EXPIRE_MINUTES) -> str:
    claims = {
        **payload,
        "scope": ANSWER_FILE_ACCESS_SCOPE,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_answer_file_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="无效的答案附件访问令牌") from exc

    if payload.get("scope") != ANSWER_FILE_ACCESS_SCOPE:
        raise HTTPException(status_code=401, detail="无效的答案附件访问范围")
    return payload
