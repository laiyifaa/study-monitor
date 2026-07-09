"""
认证模块 (auth)

功能说明：
    负责用户身份认证，支持两种登录方式：
    1. 钉钉免登——学生/老师通过钉钉客户端打开系统时，无需输入账号密码
    2. 账号密码登录——通过账号（准考证号等）+ 密码登录

    免登自动绑定逻辑：
    - 钉钉 userid 已绑定 → 直接登录
    - 钉钉手机号匹配到 1 个学生的 contact_phones → 自动绑定
    - 匹配到 0 个或多个 → 前端弹窗手动输入账号绑定

API 列表：
    POST /api/auth/dingtalk       — 钉钉免登：authCode → 用户信息 + JWT / 绑定提示
    POST /api/auth/login          — 账号密码登录：account + password → JWT
    POST /api/auth/bind-account   — 钉钉用户绑定账号（手动输入账号）
    POST /api/auth/forgot-password — 忘记密码：输入账号 → 设置新密码
    GET  /api/auth/me             — 获取当前登录用户信息
    POST /api/auth/set-password   — 设置/修改用户密码（管理员或本人）
    POST /api/auth/change-password — 自助修改密码（需验证旧密码）
"""

import hashlib
import secrets
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.database_redis import get_redis
from app.models.models import User
from app.utils.jwt_helper import create_token, get_current_user, require_role

router = APIRouter(prefix="/api/auth", tags=["认证"])
settings = get_settings()


# ============================================================
# 密码哈希工具函数
# ============================================================

def hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000, dklen=32)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hash_val = stored_hash.split(':')
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000, dklen=32)
        return secrets.compare_digest(dk.hex(), hash_val)
    except (ValueError, AttributeError):
        return False


async def get_access_token() -> str:
    redis = await get_redis()
    cached = await redis.get("dingtalk:access_token")
    if cached:
        return cached

    url = "https://oapi.dingtalk.com/gettoken"
    params = {"appkey": settings.DT_APP_KEY, "appsecret": settings.DT_APP_SECRET}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        await redis.setex("dingtalk:access_token", expires_in - 60, token)
        return token


def _user_dict(user: User) -> dict:
    """统一构建返回给前端的用户信息字典"""
    return {
        "id": user.id,
        "account": user.account,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar,
        "class_name": user.class_name,
        "real_name": user.real_name,
        "phone": user.phone,
        "has_password": bool(user.password_hash),
    }


# ============================================================
# 钉钉免登
# ============================================================

class DingTalkLoginRequest(BaseModel):
    auth_code: str


@router.post("/dingtalk")
async def dingtalk_login(req: DingTalkLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    钉钉免登接口

    返回逻辑：
    1. userid 已绑定用户 → 直接登录，返回 JWT
    2. 手机号匹配到 1 个学生 → 自动绑定 → 返回 JWT
    3. 匹配 0 或多个 → 返回 need_bind_account=True，前端弹窗输入账号
    """
    token = await get_access_token()

    # 第一步：authCode → userid
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

    # 第二步：userid → 钉钉用户详情
    async with httpx.AsyncClient(timeout=10) as client:
        resp2 = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/get",
            params={"access_token": token},
            json={"userid": userid},
        )
        user_info = resp2.json().get("result", {})

    dt_name = user_info.get("name", "")
    dt_mobile = user_info.get("mobile", "")
    dt_avatar = user_info.get("avatar", "")

    # 第三步：检查 dingtalk_user_id 是否已绑定
    result = await db.execute(select(User).where(User.dingtalk_user_id == userid))
    user = result.scalar_one_or_none()

    if user:
        # 已绑定 → 同步钉钉信息 → 直接登录
        if dt_name and user.name != dt_name:
            user.name = dt_name
        if dt_name and user.real_name != dt_name:
            user.real_name = dt_name
        if dt_mobile and user.phone != dt_mobile:
            user.phone = dt_mobile
        if dt_avatar and user.avatar != dt_avatar:
            user.avatar = dt_avatar
        await db.commit()

        jwt_token = create_token(user.id, user.role)
        return {
            "code": 0,
            "data": {
                "token": jwt_token,
                "user": _user_dict(user),
            },
        }

    # 第四步：未绑定 → 尝试用手机号自动匹配 contact_phones
    if dt_mobile:
        matched_users = []
        all_students = await db.execute(
            select(User).where(User.role == "student", User.contact_phones != "")
        )
        for stu in all_students.scalars():
            phones = [p.strip() for p in stu.contact_phones.split(",") if p.strip()]
            if dt_mobile in phones:
                matched_users.append(stu)

        if len(matched_users) == 1:
            # 匹配到 1 个 → 自动绑定
            matched_user = matched_users[0]
            matched_user.dingtalk_user_id = userid
            if dt_name and not matched_user.real_name:
                matched_user.real_name = dt_name
            if dt_mobile and not matched_user.phone:
                matched_user.phone = dt_mobile
            if dt_avatar and not matched_user.avatar:
                matched_user.avatar = dt_avatar
            await db.commit()

            jwt_token = create_token(matched_user.id, matched_user.role)
            return {
                "code": 0,
                "data": {
                    "token": jwt_token,
                    "user": _user_dict(matched_user),
                },
            }

    # 第五步：无法自动绑定 → 返回 need_bind_account，前端弹窗
    return {
        "code": 2,
        "data": {
            "need_bind_account": True,
            "dingtalk_user_id": userid,
            "dingtalk_name": dt_name,
            "dingtalk_mobile": dt_mobile,
            "dingtalk_avatar": dt_avatar,
        },
    }


# ============================================================
# 钉钉绑定账号
# ============================================================

class BindAccountRequest(BaseModel):
    account: str
    dingtalk_user_id: str
    dingtalk_name: str = ""
    dingtalk_mobile: str = ""
    dingtalk_avatar: str = ""


@router.post("/bind-account")
async def bind_account(req: BindAccountRequest, db: AsyncSession = Depends(get_db)):
    """
    钉钉用户手动绑定账号

    流程：用户在免登弹窗中输入账号 → 查到用户 → 绑定 dingtalk_user_id
    """
    if not req.account.strip():
        return {"code": 1, "msg": "请输入账号"}

    # 按账号查找用户
    result = await db.execute(select(User).where(User.account == req.account.strip()))
    user = result.scalar_one_or_none()

    if not user:
        return {"code": 1, "msg": "账号不存在，请检查后重新输入"}

    # 检查该用户是否已绑定其他钉钉账号
    if user.dingtalk_user_id:
        return {"code": 1, "msg": "该账号已绑定其他钉钉，如需更换请联系管理员"}

    # 检查该钉钉ID是否已绑定其他账号
    existing = await db.execute(select(User).where(User.dingtalk_user_id == req.dingtalk_user_id))
    if existing.scalar_one_or_none():
        return {"code": 1, "msg": "该钉钉已绑定其他账号"}

    # 执行绑定
    user.dingtalk_user_id = req.dingtalk_user_id
    if req.dingtalk_name and not user.real_name:
        user.real_name = req.dingtalk_name
    if req.dingtalk_mobile and not user.phone:
        user.phone = req.dingtalk_mobile
    if req.dingtalk_avatar and not user.avatar:
        user.avatar = req.dingtalk_avatar
    await db.commit()

    jwt_token = create_token(user.id, user.role)
    return {
        "code": 0,
        "data": {
            "token": jwt_token,
            "user": _user_dict(user),
        },
    }


# ============================================================
# 账号密码登录
# ============================================================

class LoginRequest(BaseModel):
    username: str  # 前端字段名保持 username，实际传的是 account
    password: str


@router.post("/login")
async def browser_login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    账号密码登录 — 用账号+密码换取 JWT

    请求参数：
        body.username (str): 账号（准考证号等）
        body.password (str): 密码
    """
    account = req.username.strip()

    # 按账号查找用户
    result = await db.execute(select(User).where(User.account == account))
    user = result.scalar_one_or_none()

    if not user:
        return {"code": 1, "msg": "账号或密码错误"}

    if not user.password_hash:
        return {"code": 1, "msg": "该账号未设置密码，请先设置密码"}

    if not verify_password(req.password, user.password_hash):
        return {"code": 1, "msg": "账号或密码错误"}

    jwt_token = create_token(user.id, user.role)
    return {
        "code": 0,
        "data": {
            "token": jwt_token,
            "user": _user_dict(user),
        },
    }


# ============================================================
# 忘记密码
# ============================================================

class ForgotPasswordRequest(BaseModel):
    account: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    忘记密码 — 输入账号即可重置密码

    请求参数：
        body.account (str): 账号
        body.new_password (str): 新密码（至少6位）
    """
    if not req.account.strip():
        return {"code": 1, "msg": "请输入账号"}

    if len(req.new_password) < 6:
        return {"code": 1, "msg": "密码长度不能少于6位"}

    result = await db.execute(select(User).where(User.account == req.account.strip()))
    user = result.scalar_one_or_none()

    if not user:
        return {"code": 1, "msg": "账号不存在"}

    user.password_hash = hash_password(req.new_password)
    await db.commit()

    return {"code": 0, "msg": "密码重置成功，请使用新密码登录"}


# ============================================================
# 获取当前用户信息
# ============================================================

@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return _user_dict(user)


# ============================================================
# 管理员/本人设置密码
# ============================================================

class SetPasswordRequest(BaseModel):
    user_id: int
    new_password: str


@router.post("/set-password")
async def set_password(
    req: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员/教师为用户设置密码，或用户为自己设置密码"""
    if current_user.role not in ("admin", "teacher") and current_user.id != req.user_id:
        raise HTTPException(status_code=403, detail="只能修改自己的密码")

    if len(req.new_password) < 6:
        return {"code": 1, "msg": "密码长度不能少于6位"}

    result = await db.execute(select(User).where(User.id == req.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = hash_password(req.new_password)
    await db.commit()

    return {"code": 0, "msg": "密码设置成功"}


# ============================================================
# 自助修改密码
# ============================================================

class ChangePasswordRequest(BaseModel):
    old_password: str = ""
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已登录用户修改自己的密码，未设密码时跳过旧密码验证"""
    if not current_user.password_hash:
        if len(req.new_password) < 6:
            return {"code": 1, "msg": "新密码长度不能少于6位"}
        current_user.password_hash = hash_password(req.new_password)
        await db.commit()
        return {"code": 0, "msg": "密码设置成功"}

    if not verify_password(req.old_password, current_user.password_hash):
        return {"code": 1, "msg": "当前密码错误"}

    if len(req.new_password) < 6:
        return {"code": 1, "msg": "新密码长度不能少于6位"}

    if verify_password(req.new_password, current_user.password_hash):
        return {"code": 1, "msg": "新密码不能与当前密码相同"}

    current_user.password_hash = hash_password(req.new_password)
    await db.commit()

    return {"code": 0, "msg": "密码修改成功"}


# ============================================================
# API Key 管理
# ============================================================

@router.post("/generate-api-key")
async def generate_api_key(
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    new_key = f"sk_{secrets.token_hex(32)}"
    current_user.api_key = new_key
    await db.commit()
    return {"code": 0, "data": {"api_key": new_key}}


@router.get("/api-key")
async def get_api_key_status(
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.api_key:
        return {"code": 0, "data": {"has_key": False, "masked": ""}}
    key = current_user.api_key
    masked = f"{key[:6]}****{key[-4:]}" if len(key) > 10 else "sk_****"
    return {"code": 0, "data": {"has_key": True, "masked": masked}}
