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
import random
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.database_redis import get_redis
from app.models.models import User, DingTalkBinding, LoginLog
from app.utils.jwt_helper import create_token, get_current_user, require_role

router = APIRouter(prefix="/api/auth", tags=["认证"])
settings = get_settings()


# ============================================================
# 设备信息 schema（前端上报）+ 登录日志辅助函数
# ============================================================

class DeviceInfo(BaseModel):
    """前端采集的设备信息（可选，所有字段 default 空字符串）"""
    platform: str = ""             # navigator.platform, 如 "iPhone" / "Win32"
    os: str = ""                   # 解析后的 OS, 如 "iOS 15.2" / "Android 12"
    browser: str = ""              # 浏览器或 WebView, 如 "DingTalk-iOS 6.5.20" / "Chrome 102"
    screen: str = ""               # 屏幕分辨率, 如 "390x844"
    in_dingtalk: bool = False      # 是否在钉钉容器内
    in_wechat: bool = False        # 是否在微信容器内
    is_mobile: bool = False        # 是否移动端
    network_type: str = ""         # 网络类型, 如 "wifi" / "4g"


def _extract_ip(request: Request) -> str:
    """从 Request 中取出客户端真实 IP，优先取 X-Forwarded-For（Nginx 反代后）"""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        # X-Forwarded-For 可能是 "client, proxy1, proxy2" 链式格式，取第一个
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


async def _log_login(
    db: AsyncSession,
    *,
    user_id: Optional[int],
    account: str,
    login_type: str,
    request: Request,
    device_info: Optional[DeviceInfo],
    success: bool,
    message: str,
) -> None:
    """
    统一写登录日志（所有登录端点调用）。

    任何写入异常都不阻断登录流程——日志失败只 console.warn，不让用户登录失败。
    """
    try:
        ua = request.headers.get("user-agent", "")[:500]
        ip = _extract_ip(request)
        di = device_info  # 可能为 None
        log = LoginLog(
            user_id=user_id,
            account=account[:50],
            login_type=login_type,
            ip=ip,
            user_agent_raw=ua,
            device_platform=(di.platform if di else "")[:50],
            device_os=(di.os if di else "")[:100],
            browser=(di.browser if di else "")[:100],
            screen_size=(di.screen if di else "")[:20],
            in_dingtalk=(di.in_dingtalk if di else False),
            in_wechat=(di.in_wechat if di else False),
            is_mobile=(di.is_mobile if di else False),
            network_type=(di.network_type if di else "")[:20],
            success=success,
            message=message[:200] if message else "",
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        # 日志写入失败不影响登录流程
        import sys
        print(f"[login_log] 写入登录日志失败: {e}", file=sys.stderr)


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
        "must_change_password": bool(user.must_change_password),
    }


# ============================================================
# 钉钉免登
# ============================================================

class DingTalkLoginRequest(BaseModel):
    auth_code: str
    device_info: Optional[DeviceInfo] = None


@router.post("/dingtalk")
async def dingtalk_login(req: DingTalkLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
            await _log_login(db, user_id=None, account="", login_type="dingtalk",
                             request=request, device_info=req.device_info,
                             success=False, message="免登失败，无法获取用户ID")
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

    # 第三步：检查 dingtalk_bindings 表是否已绑定（支持一个学生绑定多个钉钉）
    binding_result = await db.execute(
        select(DingTalkBinding).where(DingTalkBinding.dingtalk_user_id == userid)
    )
    binding = binding_result.scalar_one_or_none()

    if binding:
        # 已绑定 → 查出关联用户 → 同步钉钉信息 → 直接登录
        user_result = await db.execute(select(User).where(User.id == binding.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            if dt_name and user.name != dt_name:
                user.name = dt_name
            if dt_name and user.real_name != dt_name:
                user.real_name = dt_name
            if dt_mobile and user.phone != dt_mobile:
                user.phone = dt_mobile
            if dt_avatar and user.avatar != dt_avatar:
                user.avatar = dt_avatar
            # 同步更新绑定记录中的钉钉信息
            if dt_name and binding.dingtalk_name != dt_name:
                binding.dingtalk_name = dt_name
            if dt_mobile and binding.dingtalk_mobile != dt_mobile:
                binding.dingtalk_mobile = dt_mobile
            if dt_avatar and binding.dingtalk_avatar != dt_avatar:
                binding.dingtalk_avatar = dt_avatar
            await db.commit()

            jwt_token = create_token(user.id, user.role)
            await _log_login(db, user_id=user.id, account=user.account, login_type="dingtalk",
                             request=request, device_info=req.device_info,
                             success=True, message="免登成功(已绑定)")
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
            # 匹配到 1 个 → 自动绑定（写入 dingtalk_bindings 表）
            matched_user = matched_users[0]
            new_binding = DingTalkBinding(
                user_id=matched_user.id,
                dingtalk_user_id=userid,
                dingtalk_name=dt_name,
                dingtalk_mobile=dt_mobile,
                dingtalk_avatar=dt_avatar,
            )
            db.add(new_binding)
            if dt_name and not matched_user.real_name:
                matched_user.real_name = dt_name
            if dt_mobile and not matched_user.phone:
                matched_user.phone = dt_mobile
            if dt_avatar and not matched_user.avatar:
                matched_user.avatar = dt_avatar
            await db.commit()

            jwt_token = create_token(matched_user.id, matched_user.role)
            await _log_login(db, user_id=matched_user.id, account=matched_user.account, login_type="dingtalk",
                             request=request, device_info=req.device_info,
                             success=True, message="免登成功(手机号自动绑定)")
            return {
                "code": 0,
                "data": {
                    "token": jwt_token,
                    "user": _user_dict(matched_user),
                },
            }

    # 第五步：无法自动绑定 → 返回 need_bind_account，前端弹窗
    await _log_login(db, user_id=None, account="", login_type="dingtalk",
                     request=request, device_info=req.device_info,
                     success=False, message="需要手动绑定账号")
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
    password: str = ""  # 绑定需要密码验证，防止未授权绑定
    dingtalk_user_id: str
    dingtalk_name: str = ""
    dingtalk_mobile: str = ""
    dingtalk_avatar: str = ""
    device_info: Optional[DeviceInfo] = None


@router.post("/bind-account")
async def bind_account(req: BindAccountRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    钉钉用户手动绑定账号

    流程：用户在免登弹窗中输入账号+密码 → 查到用户 → 验证密码 → 绑定到 dingtalk_bindings 表
    支持一个学生绑定多个钉钉账号（父亲、母亲），但每个钉钉只能绑一个学生
    """
    if not req.account.strip():
        await _log_login(db, user_id=None, account=req.account, login_type="bind",
                         request=request, device_info=req.device_info,
                         success=False, message="请输入账号")
        return {"code": 1, "msg": "请输入账号"}

    # 按账号查找用户
    result = await db.execute(select(User).where(User.account == req.account.strip()))
    user = result.scalar_one_or_none()

    if not user:
        await _log_login(db, user_id=None, account=req.account, login_type="bind",
                         request=request, device_info=req.device_info,
                         success=False, message="账号不存在")
        return {"code": 1, "msg": "账号不存在，请检查后重新输入"}

    # 验证密码（防止未授权绑定）
    if user.password_hash:
        if not req.password:
            await _log_login(db, user_id=user.id, account=req.account, login_type="bind",
                             request=request, device_info=req.device_info,
                             success=False, message="请输入密码")
            return {"code": 1, "msg": "请输入密码"}
        if not verify_password(req.password, user.password_hash):
            await _log_login(db, user_id=user.id, account=req.account, login_type="bind",
                             request=request, device_info=req.device_info,
                             success=False, message="密码错误")
            return {"code": 1, "msg": "密码错误，请检查后重新输入"}
    # 无密码的账号（纯钉钉用户）不需要验证密码，允许直接绑定

    # 检查该钉钉ID是否已绑定其他账号（一个钉钉只能绑一个学生）
    existing_binding = await db.execute(
        select(DingTalkBinding).where(DingTalkBinding.dingtalk_user_id == req.dingtalk_user_id)
    )
    if existing_binding.scalar_one_or_none():
        await _log_login(db, user_id=user.id, account=req.account, login_type="bind",
                         request=request, device_info=req.device_info,
                         success=False, message="该钉钉已绑定其他账号")
        return {"code": 1, "msg": "该钉钉已绑定其他账号"}

    # 检查该用户是否已绑定过这个钉钉（防止重复绑定）
    dup_check = await db.execute(
        select(DingTalkBinding).where(
            DingTalkBinding.user_id == user.id,
            DingTalkBinding.dingtalk_user_id == req.dingtalk_user_id,
        )
    )
    if dup_check.scalar_one_or_none():
        await _log_login(db, user_id=user.id, account=req.account, login_type="bind",
                         request=request, device_info=req.device_info,
                         success=False, message="该账号已绑定此钉钉")
        return {"code": 1, "msg": "该账号已绑定此钉钉"}

    # 写入 dingtalk_bindings 表（允许多个钉钉绑定同一个学生）
    new_binding = DingTalkBinding(
        user_id=user.id,
        dingtalk_user_id=req.dingtalk_user_id,
        dingtalk_name=req.dingtalk_name or "",
        dingtalk_mobile=req.dingtalk_mobile or "",
        dingtalk_avatar=req.dingtalk_avatar or "",
    )
    db.add(new_binding)

    # 同步更新用户表中的实名信息（仅当字段为空时填充）
    if req.dingtalk_name and not user.real_name:
        user.real_name = req.dingtalk_name
    if req.dingtalk_mobile and not user.phone:
        user.phone = req.dingtalk_mobile
    if req.dingtalk_avatar and not user.avatar:
        user.avatar = req.dingtalk_avatar
    await db.commit()

    jwt_token = create_token(user.id, user.role)
    await _log_login(db, user_id=user.id, account=user.account, login_type="bind",
                     request=request, device_info=req.device_info,
                     success=True, message="绑定账号成功")
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
    device_info: Optional[DeviceInfo] = None


@router.post("/login")
async def browser_login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
        await _log_login(db, user_id=None, account=account, login_type="password",
                         request=request, device_info=req.device_info,
                         success=False, message="账号或密码错误")
        return {"code": 1, "msg": "账号或密码错误"}

    if not user.password_hash:
        await _log_login(db, user_id=user.id, account=account, login_type="password",
                         request=request, device_info=req.device_info,
                         success=False, message="账号未设置密码")
        return {"code": 1, "msg": "该账号未设置密码，请先设置密码"}

    if not verify_password(req.password, user.password_hash):
        await _log_login(db, user_id=user.id, account=account, login_type="password",
                         request=request, device_info=req.device_info,
                         success=False, message="账号或密码错误")
        return {"code": 1, "msg": "账号或密码错误"}

    jwt_token = create_token(user.id, user.role)
    await _log_login(db, user_id=user.id, account=user.account, login_type="password",
                     request=request, device_info=req.device_info,
                     success=True, message="账号密码登录成功")
    return {
        "code": 0,
        "data": {
            "token": jwt_token,
            "user": _user_dict(user),
        },
    }


# ============================================================
# 忘记密码 — 三步流程
#   步骤1: /forgot-password-check — 查账号 → 老师跳过验证 / 学生返回掩码手机号
#   步骤2: /forgot-password-verify — 学生验证手机号缺失的4位
#   步骤3: /forgot-password — 验证通过后重置密码
# ============================================================

class ForgotPasswordCheckRequest(BaseModel):
    account: str


class ForgotPasswordVerifyRequest(BaseModel):
    verify_token: str
    digits: str


class ForgotPasswordRequest(BaseModel):
    verify_token: str
    new_password: str


@router.post("/forgot-password-check")
async def forgot_password_check(req: ForgotPasswordCheckRequest, db: AsyncSession = Depends(get_db)):
    """
    步骤1：输入账号，查询用户是否存在，判断角色
    - 老师：直接返回 need_verify=false，跳过手机验证
    - 学生：返回掩码后的家长手机号，need_verify=true
    """
    account = req.account.strip()
    if not account:
        return {"code": 1, "msg": "请输入账号"}

    result = await db.execute(select(User).where(User.account == account))
    user = result.scalar_one_or_none()
    if not user:
        return {"code": 1, "msg": "账号不存在"}

    # 生成 verify_token
    verify_token = secrets.token_hex(32)

    if user.role in ("teacher", "admin"):
        # 老师/管理员跳过手机验证，token 直接标记为已验证
        redis = await get_redis()
        await redis.setex(
            f"forgot_pw:verify:{verify_token}",
            600,  # 10 分钟有效期
            f"{user.id}|verified"
        )
        return {
            "code": 0,
            "data": {
                "need_verify": False,
                "verify_token": verify_token,
            },
        }

    # 学生：从 contact_phones 中随机选一个家长手机号
    phones_str = (user.contact_phones or "").strip()
    if not phones_str:
        return {"code": 1, "msg": "该账号未绑定家长手机号，请联系老师重置密码"}

    phones = [p.strip() for p in phones_str.split(",") if p.strip()]
    if not phones:
        return {"code": 1, "msg": "该账号未绑定家长手机号，请联系老师重置密码"}

    phone = random.choice(phones)
    if len(phone) < 11:
        return {"code": 1, "msg": "绑定的手机号格式不正确，请联系老师"}

    # 随机选择连续 4 位作为隐藏位（从第 3 位之后开始，避免遮挡前 3 位运营商号段）
    mask_start = random.randint(3, len(phone) - 4)
    correct_digits = phone[mask_start:mask_start + 4]

    # 构建掩码手机号
    masked = list(phone)
    for i in range(mask_start, mask_start + 4):
        masked[i] = "*"
    masked_phone = "".join(masked)

    # 存入 Redis
    redis = await get_redis()
    await redis.setex(
        f"forgot_pw:verify:{verify_token}",
        600,
        f"{user.id}|{correct_digits}|{mask_start}"
    )

    return {
        "code": 0,
        "data": {
            "need_verify": True,
            "verify_token": verify_token,
            "masked_phone": masked_phone,
        },
    }


@router.post("/forgot-password-verify")
async def forgot_password_verify(req: ForgotPasswordVerifyRequest):
    """
    步骤2（仅学生）：验证手机号缺失的 4 位数字
    """
    if not req.verify_token or len(req.digits) != 4:
        return {"code": 1, "msg": "请输入完整的四位数字"}

    redis = await get_redis()
    key = f"forgot_pw:verify:{req.verify_token}"
    data = await redis.get(key)
    if not data:
        return {"code": 1, "msg": "验证已过期，请重新开始"}

    parts = data.split("|")
    if len(parts) == 2 and parts[1] == "verified":
        # 老师/管理员已跳过验证
        return {"code": 0, "msg": "验证成功"}

    if len(parts) != 3:
        return {"code": 1, "msg": "验证数据异常，请重新开始"}

    correct_digits = parts[1]
    if req.digits != correct_digits:
        return {"code": 1, "msg": "号码输入错误，请重新输入"}

    # 验证通过，更新 token 标记
    await redis.setex(key, 600, f"{parts[0]}|verified")

    return {"code": 0, "msg": "验证成功"}


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    步骤3：验证通过后重置密码
    """
    if not req.verify_token:
        return {"code": 1, "msg": "验证信息缺失"}

    if len(req.new_password) < 6:
        return {"code": 1, "msg": "密码长度不能少于6位"}

    redis = await get_redis()
    key = f"forgot_pw:verify:{req.verify_token}"
    data = await redis.get(key)
    if not data:
        return {"code": 1, "msg": "验证已过期，请重新开始"}

    parts = data.split("|")
    if len(parts) == 2 and parts[1] == "verified":
        user_id = int(parts[0])
    elif len(parts) == 3:
        parts2 = parts[0].split("::")
        if len(parts2) == 2 and parts2[1] == "verified":
            user_id = int(parts2[0])
        else:
            return {"code": 1, "msg": "请先完成手机号验证"}
    else:
        return {"code": 1, "msg": "请先完成手机号验证"}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"code": 1, "msg": "用户不存在"}

    user.password_hash = hash_password(req.new_password)
    await db.commit()

    # 删除 Redis 中的 token
    await redis.delete(key)

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
        current_user.must_change_password = False
        await db.commit()
        return {"code": 0, "msg": "密码设置成功"}

    if not verify_password(req.old_password, current_user.password_hash):
        return {"code": 1, "msg": "当前密码错误"}

    if len(req.new_password) < 6:
        return {"code": 1, "msg": "新密码长度不能少于6位"}

    if verify_password(req.new_password, current_user.password_hash):
        return {"code": 1, "msg": "新密码不能与当前密码相同"}

    current_user.password_hash = hash_password(req.new_password)
    current_user.must_change_password = False
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
