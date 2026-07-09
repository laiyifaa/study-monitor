"""
管理模块 (admin)

功能说明：
    管理后台的 API 接口，提供用户管理和班级管理两大功能。
    仅管理员和教师角色可访问，用于维护系统基础数据。

在系统中的角色：
    运维管理层——日常运营中需要频繁使用的管理功能：
    - 用户管理：查看用户列表、修改角色、重置密码、按班级筛选
    - 班级管理：班级的增删改查、学生分配到班级

API 列表：
    用户管理：
        GET    /api/admin/users                    — 获取用户列表（支持角色/班级/搜索过滤）
        GET    /api/admin/users/{id}               — 获取用户详情（v4.0 新增）
        POST   /api/admin/users                    — 创建用户
        PUT    /api/admin/users/{id}               — 更新用户信息（v4.0 新增）
        PUT    /api/admin/users/{id}/role          — 修改用户角色
        POST   /api/admin/users/{id}/reset-password — 重置用户密码
        DELETE /api/admin/users/{id}               — 删除用户（v4.0 新增，仅admin）
    
    班级管理：
        GET    /api/admin/classes                  — 获取班级列表（含学生人数统计）
        POST   /api/admin/classes                  — 创建班级
        PUT    /api/admin/classes/{id}             — 更新班级信息
        DELETE /api/admin/classes/{id}             — 删除班级
        PUT    /api/admin/classes/{id}/students    — 批量分配学生到班级

权限矩阵：
    所有接口支持 API Key 认证（X-API-Key 请求头）和 JWT 认证
    用户管理：admin / teacher
    用户删除：仅 admin
    班级管理：admin / teacher
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.models import User
from app.routers.auth import hash_password
from app.utils.jwt_helper import require_role

router = APIRouter(prefix="/api/admin", tags=["管理"])


# ============================================================
# 用户管理接口
# ============================================================

@router.get("/users")
async def list_users(
    role: Optional[str] = Query(None, description="按角色过滤：student/teacher/admin"),
    class_name: Optional[str] = Query(None, description="按班级名称过滤"),
    search: Optional[str] = Query(None, description="按姓名或账号搜索（模糊匹配）"),
    user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户列表（支持多条件过滤）

    请求参数：
        query.role (str):       角色过滤（可选）
        query.class_name (str): 班级名称过滤（可选）
        query.search (str):     姓名或账号模糊搜索（可选）

    返回格式：
        code=0, data: [{ id, account, name, role, class_name, avatar, has_password, created_at }, ...]

    权限要求：【admin / teacher】
    
    说明：
        has_password 字段标识用户是否设置了浏览器登录密码，
        管理员可通过此字段判断是否需要为用户重置密码。
    """
    query = select(User).order_by(User.id)

    # 按角色过滤
    if role:
        query = query.where(User.role == role)
    # 按班级过滤
    if class_name:
        query = query.where(User.class_name == class_name)
    # 姓名或账号模糊搜索
    if search:
        query = query.where(or_(User.name.like(f"%{search}%"), User.account.like(f"%{search}%")))

    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "code": 0,
        "data": [
            {
                "id": u.id,
                "account": u.account,
                "name": u.name,
                "real_name": u.real_name or "",
                "phone": u.phone or "",
                "role": u.role,
                "class_name": u.class_name,
                "avatar": u.avatar,
                # 布尔值：是否已设置浏览器登录密码
                "has_password": bool(u.password_hash),
                "created_at": str(u.created_at) if u.created_at else None,
            }
            for u in users
        ],
    }


class RoleUpdateRequest(BaseModel):
    """角色修改请求体"""
    role: str  # 目标角色：student / teacher / admin


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    req: RoleUpdateRequest,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    修改用户角色

    请求参数：
        path.user_id (int):    目标用户ID
        body.role (str):       新角色（student/teacher/admin）

    权限要求：【admin 或 teacher】

    安全说明：
        - admin 可设置任意角色（含 admin）
        - teacher 只能设置 student 或 teacher（不能设置 admin）
        - 不能降低自己的角色（防止误操作把自己变成学生后无法恢复）
        - 只允许设置合法的角色值
    """
    # 合法角色校验
    if req.role not in ("student", "teacher", "admin"):
        return {"code": 1, "msg": "无效的角色"}

    # 教师不能设置管理员角色
    if current_user.role == "teacher" and req.role == "admin":
        return {"code": 1, "msg": "教师不能设置管理员角色"}

    # 查找目标用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 防止管理员降低自身权限
    if user.id == current_user.id and req.role != current_user.role:
        return {"code": 1, "msg": "不能修改自己的角色"}

    user.role = req.role
    await db.commit()
    return {"code": 0, "msg": "角色修改成功"}


class ResetPasswordRequest(BaseModel):
    """重置密码请求体"""
    new_password: str  # 新密码


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    req: ResetPasswordRequest,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    重置用户密码

    请求参数：
        path.user_id (int):       目标用户ID
        body.new_password (str):  新密码（至少6位）

    权限要求：【admin / teacher】

    使用场景：
        - 管理员为新注册用户设置初始密码
        - 用户忘记密码时由管理员重置
    """
    if len(req.new_password) < 6:
        return {"code": 1, "msg": "密码长度不能少于6位"}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"code": 0, "msg": "密码重置成功"}


# ============================================================
# 班级管理接口
# ============================================================
# 班级信息目前存储在 User.class_name 字段中（字符串），
# 此处提供结构化的班级管理 API，支持班级维度的聚合操作。
# 后续可迁移到独立的 Class 表。

@router.get("/classes")
async def list_classes(
    user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取班级列表（含学生人数统计）

    返回格式：
        code=0, data: [
            { class_name: "高一1班", student_count: 30, teacher_count: 2 },
            ...
        ]

    权限要求：【admin / teacher】

    说明：
        班级列表从用户表的 class_name 字段聚合生成，而非独立的班级表。
        这样设计是因为当前系统规模小（1-2个年级，5-10个班），
        避免引入额外的 Class 表和关联关系的复杂度。
    """
    # 按班级名聚合，统计每个班级的学生数和教师数
    result = await db.execute(
        select(
            User.class_name,
            func.sum(func.if_(User.role == "student", 1, 0)).label("student_count"),
            func.sum(func.if_(User.role == "teacher", 1, 0)).label("teacher_count"),
        )
        .where(User.class_name != "")
        .group_by(User.class_name)
        .order_by(User.class_name)
    )
    rows = result.all()

    return {
        "code": 0,
        "data": [
            {
                "class_name": r.class_name,
                "student_count": int(r.student_count or 0),
                "teacher_count": int(r.teacher_count or 0),
            }
            for r in rows
        ],
    }


class ClassCreateRequest(BaseModel):
    """创建班级请求体：指定班级名称"""
    class_name: str


@router.post("/classes")
async def create_class(
    req: ClassCreateRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建班级（实际上是检查班级名是否已存在）

    权限要求：【仅 admin】

    说明：
        由于班级信息存储在 User.class_name 中，创建班级不需要建表，
        只需确保班级名不与现有班级重复即可。学生分配到班级后，
        班级自动出现在班级列表中。
    """
    if not req.class_name.strip():
        return {"code": 1, "msg": "班级名称不能为空"}

    # 检查是否已存在同名班级
    result = await db.execute(
        select(User).where(User.class_name == req.class_name.strip()).limit(1)
    )
    if result.scalar_one_or_none():
        return {"code": 1, "msg": "该班级名称已存在"}

    return {"code": 0, "msg": f"班级 '{req.class_name}' 创建成功，请分配学生"}


class ClassUpdateRequest(BaseModel):
    """更新班级名称请求体"""
    new_name: str


@router.put("/classes/{class_name}")
async def update_class(
    class_name: str,
    req: ClassUpdateRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新班级名称（批量修改该班级所有用户的 class_name）

    请求参数：
        path.class_name (str):   原班级名称（URL编码）
        body.new_name (str):     新班级名称

    权限要求：【仅 admin】
    """
    if not req.new_name.strip():
        return {"code": 1, "msg": "班级名称不能为空"}

    # 批量更新该班级所有用户的 class_name
    from sqlalchemy import update
    stmt = update(User).where(User.class_name == class_name).values(class_name=req.new_name.strip())
    result = await db.execute(stmt)
    await db.commit()

    if result.rowcount == 0:
        return {"code": 1, "msg": "未找到该班级的用户"}

    return {"code": 0, "msg": f"已更新 {result.rowcount} 名用户的班级名称"}


@router.delete("/classes/{class_name}")
async def delete_class(
    class_name: str,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除班级（将该班级所有用户的 class_name 置空，而非删除用户）

    请求参数：
        path.class_name (str): 要删除的班级名称（URL编码）

    权限要求：【仅 admin】

    安全说明：
        删除班级只是将学生从班级中移出（class_name 置空），
        不会删除用户账号和学习数据，学生仍可登录和使用系统。
    """
    from sqlalchemy import update
    stmt = update(User).where(User.class_name == class_name).values(class_name="")
    result = await db.execute(stmt)
    await db.commit()

    if result.rowcount == 0:
        return {"code": 1, "msg": "未找到该班级的用户"}

    return {"code": 0, "msg": f"已将 {result.rowcount} 名用户移出班级 '{class_name}'"}


class AssignStudentsRequest(BaseModel):
    """分配学生到班级请求体"""
    user_ids: list[int]  # 要分配的用户ID列表


@router.put("/classes/{class_name}/students")
async def assign_students(
    class_name: str,
    req: AssignStudentsRequest,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    批量分配学生到指定班级

    请求参数：
        path.class_name (str): 目标班级名称
        body.user_ids (list):  用户ID列表

    权限要求：【admin / teacher】

    说明：
        将指定的用户（通常是学生）的 class_name 统一设置为指定班级。
        已在其他班级的学生会被移动到新班级。
    """
    from sqlalchemy import update
    stmt = update(User).where(User.id.in_(req.user_ids)).values(class_name=class_name)
    result = await db.execute(stmt)
    await db.commit()

    return {"code": 0, "msg": f"已将 {result.rowcount} 名用户分配到班级 '{class_name}'"}


# ============================================================
# 新增用户接口
# ============================================================

class CreateUserRequest(BaseModel):
    """创建新用户请求体"""
    account: str                 # 登录账号（必填，唯一标识）
    name: str                    # 用户姓名
    role: str = "student"        # 角色，默认学生
    class_name: str = ""         # 班级名称
    password: str = "123456"     # 初始密码，默认123456


@router.post("/users")
async def create_user(
    req: CreateUserRequest,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新用户

    请求参数：
        body.account (str):     登录账号（必填，如准考证号）
        body.name (str):        用户姓名
        body.role (str):        角色（student/teacher/admin），默认student
        body.class_name (str):  班级名称，默认空
        body.password (str):    初始密码，默认123456

    权限要求：【admin / teacher】
    """
    if not req.account.strip():
        return {"code": 1, "msg": "账号不能为空"}

    if not req.name.strip():
        return {"code": 1, "msg": "用户姓名不能为空"}

    if req.role not in ("student", "teacher", "admin"):
        return {"code": 1, "msg": "无效的角色"}

    if len(req.password) < 6:
        return {"code": 1, "msg": "密码至少6位"}

    # 检查账号是否已存在
    result = await db.execute(select(User).where(User.account == req.account.strip()))
    if result.scalar_one_or_none():
        return {"code": 1, "msg": f"账号 '{req.account}' 已存在"}

    user = User(
        account=req.account.strip(),
        name=req.name.strip(),
        role=req.role,
        class_name=req.class_name.strip(),
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()

    return {
        "code": 0,
        "msg": "用户创建成功",
        "data": {
            "id": user.id,
            "account": user.account,
            "name": user.name,
            "real_name": user.real_name or "",
            "phone": user.phone or "",
            "role": user.role,
            "class_name": user.class_name,
        },
    }


class UserUpdateRequest(BaseModel):
    """更新用户信息请求体（部分更新）"""
    account: Optional[str] = None
    name: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None
    class_name: Optional[str] = None
    role: Optional[str] = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新用户信息（部分更新，v4.0 新增）

    请求参数：
        path.user_id (int):          目标用户ID
        body.name (str):             用户名（可选）
        body.real_name (str):        真实姓名（可选）
        body.phone (str):            手机号（可选）
        body.class_name (str):       班级名称（可选）
        body.role (str):             角色（可选，需admin权限）

    权限要求：【admin / teacher】
    安全说明：
        - teacher 不能修改角色字段
        - admin 可修改所有字段
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = req.model_dump(exclude_unset=True)

    # 账号修改：检查唯一性
    if "account" in update_data and update_data["account"] is not None:
        new_account = update_data["account"].strip()
        if not new_account:
            return {"code": 1, "msg": "账号不能为空"}
        existing = await db.execute(select(User).where(User.account == new_account, User.id != user_id))
        if existing.scalar_one_or_none():
            return {"code": 1, "msg": f"账号 '{new_account}' 已被占用"}
        user.account = new_account
        del update_data["account"]

    # 角色修改权限控制
    if "role" in update_data:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可修改角色")
        if update_data["role"] not in ("student", "teacher", "admin"):
            raise HTTPException(status_code=400, detail="无效的角色")
        # 不能修改自己的角色
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="不能修改自己的角色")

    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    return {
        "code": 0,
        "msg": "用户信息更新成功",
        "data": {
            "id": user.id,
            "account": user.account,
            "name": user.name,
            "real_name": user.real_name or "",
            "phone": user.phone or "",
            "role": user.role,
            "class_name": user.class_name,
        },
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: User = Depends(require_role("admin", "teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户详情（v4.0 新增）

    请求参数：
        path.user_id (int): 目标用户ID

    权限要求：【admin / teacher】
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "code": 0,
        "data": {
            "id": user.id,
            "account": user.account,
            "name": user.name,
            "real_name": user.real_name or "",
            "phone": user.phone or "",
            "role": user.role,
            "class_name": user.class_name,
            "avatar": user.avatar,
            "dingtalk_user_id": user.dingtalk_user_id,
            "contact_phones": user.contact_phones or "",
            "has_password": bool(user.password_hash),
            "has_api_key": bool(user.api_key),
            "created_at": str(user.created_at) if user.created_at else None,
            "updated_at": str(user.updated_at) if user.updated_at else None,
        },
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除用户（v4.0 新增，仅管理员）

    请求参数：
        path.user_id (int): 目标用户ID

    权限要求：【仅 admin】

    安全说明：
        - 不能删除自己
        - 删除用户会级联影响其学习记录、作业提交等数据
        - 建议优先使用角色降级或密码重置，而非删除
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    await db.delete(user)
    await db.commit()
    return {"code": 0, "msg": f"用户 '{user.name}' 已删除"}
