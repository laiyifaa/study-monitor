"""
认证模块 (auth)

功能说明：
    负责用户身份认证，支持两种登录方式：
    1. 钉钉免登——学生/老师通过钉钉客户端打开系统时，无需输入账号密码
    2. 浏览器登录——在非钉钉环境（如PC浏览器），通过用户名+密码登录
    同时提供当前登录用户信息查询接口和密码管理接口。

在系统中的角色：
    认证网关——所有需要身份的接口都依赖本模块签发的 JWT Token。
    新用户首次钉钉免登时自动创建本地账户（默认角色 student），后续免登直接匹配。
    浏览器登录需要管理员预先为用户设置密码（可通过 /auth/set-password 接口）。

API 列表：
    POST /api/auth/dingtalk      — 钉钉免登：authCode → 用户信息 + JWT
    POST /api/auth/login         — 浏览器登录：用户名 + 密码 → JWT
    GET  /api/auth/me            — 获取当前登录用户信息
    POST /api/auth/set-password  — 设置/修改用户密码（管理员或本人）

安全说明：
    - 钉钉 access_token 通过 Redis 缓存，提前60秒过期防止使用过期token
    - JWT 由 jwt_helper 模块签发，携带用户ID和角色信息
    - auth_code 只能用一次（钉钉侧保证），防止重放攻击
    - 密码使用 PBKDF2-SHA256 + 随机盐 哈希存储，不存明文
"""

import hashlib
import secrets
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
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
    """
    对明文密码进行哈希处理，使用 PBKDF2-HMAC-SHA256 + 随机盐
    
    算法选择：
        - PBKDF2 是 NIST 推荐的密码派生函数，Python 内置支持
        - 迭代次数 100,000 次，在安全性和性能间取得平衡
        - 每次生成 32 字节随机盐，确保相同密码的哈希值不同
    
    Args:
        password: 明文密码字符串
    
    Returns:
        格式为 "盐(hex):哈希值(hex)" 的字符串，便于数据库存储和验证
    """
    salt = secrets.token_hex(32)  # 64字符的十六进制盐
    # PBKDF2：将密码+盐迭代哈希100000次，生成32字节密钥
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000, dklen=32)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    验证明文密码是否与存储的哈希值匹配
    
    流程：
        1. 从存储值中提取盐和哈希
        2. 用相同盐对输入密码做 PBKDF2 哈希
        3. 比较两个哈希值是否一致（使用 secrets.compare_bytes 防止时序攻击）
    
    Args:
        password: 用户输入的明文密码
        stored_hash: 数据库中存储的哈希值（格式 "盐:哈希值"）
    
    Returns:
        True 密码正确，False 密码错误或格式无效
    """
    try:
        salt, hash_val = stored_hash.split(':')
        # 用相同的盐和参数重新计算哈希
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000, dklen=32)
        # secrets.compare_bytes 防止时序攻击，避免通过响应时间推断正确字符数
        return secrets.compare_digest(dk.hex(), hash_val)
    except (ValueError, AttributeError):
        return False


async def get_access_token() -> str:
    """
    获取钉钉企业内部应用的 access_token（带 Redis 缓存）

    安全/性能考虑：
        - access_token 有效期7200秒，全局缓存避免频繁请求钉钉服务器
        - 提前60秒过期缓存，防止在临界时间使用已过期的 token 调用钉钉API
        - 使用 Redis 集中管理缓存，多进程/多实例共享同一个 token

    Returns:
        str: 钉钉 access_token
    """
    import time
    redis = await get_redis()

    # 优先从 Redis 读取缓存的 token，避免不必要的网络请求
    cached = await redis.get("dingtalk:access_token")
    if cached:
        return cached

    # 缓存未命中，向钉钉服务器申请新 token
    url = "https://oapi.dingtalk.com/gettoken"
    params = {"appkey": settings.DT_APP_KEY, "appsecret": settings.DT_APP_SECRET}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        # 提前60秒写入缓存，留出缓冲窗口防止边界情况使用过期token
        await redis.setex("dingtalk:access_token", expires_in - 60, token)
        return token


class DingTalkLoginRequest(BaseModel):
    """钉钉免登请求体：前端通过钉钉JSAPI获取的授权码"""
    auth_code: str


@router.post("/dingtalk")
async def dingtalk_login(req: DingTalkLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    钉钉免登接口 — 前端用 authCode 换取用户身份和 JWT

    请求参数：
        body.auth_code (str): 钉钉JSAPI返回的免登授权码（一次性有效）

    返回格式：
        code=0 成功时返回 token 和用户基本信息
        code=1 失败时返回错误信息

    核心业务逻辑：
        1. 用 authCode 调用钉钉API换取 userid
        2. 用 userid 查询钉钉用户详情（姓名、头像等）
        3. 在本地数据库查找或自动创建用户记录
        4. 签发 JWT Token 返回给前端

    权限要求：无（免登本身就是认证过程，不需要已有token）

    安全说明：
        - auth_code 由钉钉客户端生成，一次性使用，无法伪造
        - 新用户自动创建为 student 角色，管理员/教师角色需手动修改
    """
    token = await get_access_token()

    # 第一步：用 authCode 换取钉钉 userid（标识用户的唯一ID）
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/getuserinfo",
            params={"access_token": token},
            json={"code": req.auth_code},
        )
        result = resp.json().get("result", {})
        userid = result.get("userid")
        if not userid:
            # auth_code 无效或已过期，返回错误让前端重新获取
            return {"code": 1, "msg": "免登失败，无法获取用户ID"}

    # 第二步：用 userid 获取用户详细信息（姓名、头像等）
    async with httpx.AsyncClient(timeout=10) as client:
        resp2 = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/get",
            params={"access_token": token},
            json={"userid": userid},
        )
        user_info = resp2.json().get("result", {})

    # 第三步：在本地数据库查找已有用户，不存在则自动创建
    # ——采用"首次登录自动注册"策略，降低使用门槛
    # ——每次免登都从钉钉同步最新用户信息（姓名、头像），
    #   这样用户在钉钉改名/换头像后，系统会自动更新，无需手动修改
    result = await db.execute(select(User).where(User.dingtalk_user_id == userid))
    user = result.scalar_one_or_none()

    # 从钉钉API响应中提取最新用户信息
    dt_name = user_info.get("name", "")
    dt_avatar = user_info.get("avatar", "")

    if not user:
        user = User(
            dingtalk_user_id=userid,
            name=dt_name or "未知",
            role="student",  # 默认角色为学生，管理员角色需后续手动配置
            avatar=dt_avatar or "",
        )
        db.add(user)
        await db.flush()       # 获取自增ID，但不提交事务
        await db.refresh(user) # 刷新对象以获取数据库生成的字段
    else:
        # 已有用户：同步钉钉最新姓名和头像（不覆盖角色，角色由管理员管理）
        if dt_name and user.name != dt_name:
            user.name = dt_name
        if dt_avatar and user.avatar != dt_avatar:
            user.avatar = dt_avatar

    # 第四步：签发 JWT Token（包含用户ID和角色，用于后续接口鉴权）
    jwt_token = create_token(user.id, user.role)
    await db.commit()  # 用户创建/更新和token签发原子提交

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
    """
    获取当前登录用户信息

    请求参数：无（通过 JWT Token 自动识别用户）

    返回格式：用户基本信息对象（id, name, role, avatar, class_name）

    权限要求：已登录用户（任意角色）

    安全说明：
        - 通过 get_current_user 依赖注入自动解析 JWT 并查询用户
        - 无效/过期 token 会自动返回 401 错误
    """
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar,
        "class_name": user.class_name,
    }


class LoginRequest(BaseModel):
    """浏览器登录请求体：用户名（即系统中的用户姓名）+ 密码"""
    username: str
    password: str


class SetPasswordRequest(BaseModel):
    """设置密码请求体：目标用户ID + 新密码"""
    user_id: int
    new_password: str


@router.post("/login")
async def browser_login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    浏览器登录接口 — 用用户名+密码换取 JWT

    使用场景：
        非钉钉环境（如PC浏览器开发调试、管理员后台操作），
        用户通过输入姓名和密码登录系统。钉钉环境优先走免登流程。

    请求参数：
        body.username (str): 用户姓名（对应 User.name 字段）
        body.password (str): 用户密码

    返回格式：
        code=0 成功时返回 token 和用户信息（与钉钉免登返回格式一致）
        code=1 失败时返回错误信息

    权限要求：无（登录本身就是认证过程）

    安全说明：
        - 密码传输依赖 HTTPS 加密（生产环境必须开启）
        - 登录失败不区分"用户不存在"和"密码错误"，防止枚举攻击
        - 连续失败可后续扩展限流（如5次失败锁定15分钟）
    """
    # 按姓名查找用户（姓名在系统中唯一标识，用作登录名）
    result = await db.execute(select(User).where(User.name == req.username))
    user = result.scalar_one_or_none()

    # 安全设计：不分别提示"用户不存在"和"密码错误"，统一返回"用户名或密码错误"
    # 防止攻击者通过不同错误消息枚举有效用户名
    if not user:
        return {"code": 1, "msg": "用户名或密码错误"}

    # 检查用户是否已设置密码（钉钉免登用户没有密码，需管理员先设置）
    if not user.password_hash:
        return {"code": 1, "msg": "该用户未设置密码，请联系管理员"}

    # 验证密码哈希
    if not verify_password(req.password, user.password_hash):
        return {"code": 1, "msg": "用户名或密码错误"}

    # 签发 JWT Token
    jwt_token = create_token(user.id, user.role)

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


@router.post("/set-password")
async def set_password(
    req: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    设置/修改用户密码

    使用场景：
        1. 管理员为新创建的用户或钉钉用户设置浏览器登录密码
        2. 用户修改自己的密码（通过 user_id=self 验证）

    请求参数：
        body.user_id (int):       目标用户ID
        body.new_password (str):  新密码（至少6位）

    权限要求：
        - 管理员/教师：可为任意用户设置密码
        - 普通学生：只能修改自己的密码

    安全说明：
        - 即使是管理员也无法查看用户原密码（哈希不可逆）
        - 密码最短6位，防止过弱的密码
    """
    # 权限校验：非管理员/教师只能改自己的密码
    if current_user.role not in ("admin", "teacher") and current_user.id != req.user_id:
        raise HTTPException(status_code=403, detail="只能修改自己的密码")

    # 密码强度校验
    if len(req.new_password) < 6:
        return {"code": 1, "msg": "密码长度不能少于6位"}

    # 查找目标用户
    result = await db.execute(select(User).where(User.id == req.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 哈希并存储新密码
    user.password_hash = hash_password(req.new_password)
    await db.commit()

    return {"code": 0, "msg": "密码设置成功"}


class ChangePasswordRequest(BaseModel):
    """自助修改密码请求体：需验证旧密码"""
    old_password: str       # 当前密码
    new_password: str       # 新密码


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    自助修改密码 — 已登录用户修改自己的密码，需验证旧密码

    请求参数：
        body.old_password (str): 当前密码
        body.new_password (str): 新密码（至少6位）

    权限要求：已登录（任意角色）

    与 /auth/set-password 的区别：
        - set-password：管理员/教师可为他人设置密码，无需旧密码
        - change-password：只能改自己，且必须验证旧密码，更安全
    """
    # 检查是否设置了密码（钉钉免登用户可能没有密码）
    if not current_user.password_hash:
        return {"code": 1, "msg": "您尚未设置密码，请联系管理员设置初始密码"}

    # 验证旧密码
    if not verify_password(req.old_password, current_user.password_hash):
        return {"code": 1, "msg": "当前密码错误"}

    # 新密码强度校验
    if len(req.new_password) < 6:
        return {"code": 1, "msg": "新密码长度不能少于6位"}

    # 新旧密码不能相同
    if verify_password(req.new_password, current_user.password_hash):
        return {"code": 1, "msg": "新密码不能与当前密码相同"}

    # 哈希并存储新密码
    current_user.password_hash = hash_password(req.new_password)
    await db.commit()

    return {"code": 0, "msg": "密码修改成功"}


# ============================================================
# API Key 管理 —— 供智能体/外部程序调用系统接口
# ============================================================

@router.post("/generate-api-key")
async def generate_api_key(
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    生成 API Key —— 为当前用户创建一个长期有效的调用密钥

    用途：
        教师/管理员生成后，可将此 Key 配置给智能体（如 TeleClaw）或外部程序，
        智能体携带 X-API-Key 请求头即可代替 JWT 访问系统所有 API，
        例如查看统计、发送提醒、导出报表等。

    权限要求：teacher 或 admin

    返回格式：
        code=0 成功，返回 api_key 字符串
        code=1 失败

    安全说明：
        - API Key 以 "sk_" 开头，后接 32 字节随机十六进制，共 67 字符
        - 每次调用会重新生成，旧 Key 立即失效
        - 生成后仅返回一次完整值，请妥善保存
    """
    # 生成 API Key: sk_ + 32字节随机十六进制
    new_key = f"sk_{secrets.token_hex(32)}"
    current_user.api_key = new_key
    await db.commit()

    return {"code": 0, "data": {"api_key": new_key}}


@router.get("/api-key")
async def get_api_key_status(
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    查看 API Key 状态 —— 检查当前用户是否已生成 API Key

    用途：
        前端管理界面展示 API Key 状态（是否已生成、部分掩码值）

    权限要求：teacher 或 admin

    安全说明：
        不返回完整 Key 值，仅返回掩码形式（如 sk_a3f2****8b1c）
        完整 Key 仅在生成时返回一次
    """
    if not current_user.api_key:
        return {"code": 0, "data": {"has_key": False, "masked": ""}}

    # 掩码处理：保留前6位和后4位
    key = current_user.api_key
    masked = f"{key[:6]}****{key[-4:]}" if len(key) > 10 else "sk_****"
    return {"code": 0, "data": {"has_key": True, "masked": masked}}
