import httpx
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import User
from app.utils.jwt_helper import create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])
settings = get_settings()

# --- 缓存 access_token ---
_access_token_cache = {"token": "", "expires": 0}


async def get_access_token() -> str:
    import time
    now = time.time()
    if _access_token_cache["token"] and now < _access_token_cache["expires"]:
        return _access_token_cache["token"]

    url = "https://oapi.dingtalk.com/gettoken"
    params = {"appkey": settings.DT_APP_KEY, "appsecret": settings.DT_APP_SECRET}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        token = data["access_token"]
        _access_token_cache["token"] = token
        _access_token_cache["expires"] = now + data.get("expires_in", 7200) - 60
        return token


class DingTalkLoginRequest(BaseModel):
    auth_code: str


@router.post("/dingtalk")
async def dingtalk_login(req: DingTalkLoginRequest, db: AsyncSession = Depends(get_db)):
    """钉钉免登：authCode 换取用户信息"""
    token = await get_access_token()

    # 用 authCode 获取 userid
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/getuserinfo",
            params={"access_token": token},
            json={"code": req.auth_code},
        )
        result = resp.json().get("result", {})
        userid = result.get("userid")
        if not userid:
            return {"code": 1, "msg": "免登失败，无法获取用户ID"}

    # 查询用户详情
    async with httpx.AsyncClient(timeout=10) as client:
        resp2 = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/get",
            params={"access_token": token},
            json={"userid": userid},
        )
        user_info = resp2.json().get("result", {})

    # 查找或创建本地用户
    result = await db.execute(select(User).where(User.dingtalk_user_id == userid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            dingtalk_user_id=userid,
            name=user_info.get("name", "未知"),
            role="student",
            avatar=user_info.get("avatar", ""),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    # 生成 JWT
    jwt_token = create_token(user.id, user.role)
    await db.commit()

    return {
        "code": 0,
        "data": {
            "token": jwt_token,
            "user": {
                "id": user.id,
                "name": user.name,
                "role": user.role,
                "avatar": user.avatar,
                "class_name": user.class_name,
            },
        },
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar,
        "class_name": user.class_name,
    }
