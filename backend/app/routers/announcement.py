"""
公告管理模块 (announcement)

功能说明：
    提供公告通知的 CRUD 操作，教师/管理员发布，学生端首页展示。
    公告可绑定到具体课程（课程公告），也可为全平台公告（course_id=null）。

    v5.0 新增：
    - 未读公告红点：GET /unread-count、POST /{id}/read、POST /mark-all-read
    - 需新增 announcement_reads 表（Base.metadata.create_all() 自动创建）

在系统中的角色：
    信息发布层——教师/管理员向学生推送通知，学生首页聚合展示。

API 列表：
    POST   /api/announcements                    — 创建公告
    GET    /api/announcements?course_id=x         — 公告列表
    GET    /api/announcements/unread-count        — 未读公告数量
    POST   /api/announcements/mark-all-read       — 一键全部已读
    GET    /api/announcements/{announcement_id}   — 公告详情
    PUT    /api/announcements/{announcement_id}   — 更新公告
    DELETE /api/announcements/{announcement_id}   — 删除公告
    POST   /api/announcements/{announcement_id}/read — 标记已读

权限矩阵：
    创建公告：teacher / admin
    编辑公告：teacher / admin
    删除公告：teacher / admin
    查看公告：所有人（学生只能看到已发布的公告）
    已读标记：需登录
"""

import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Announcement, AnnouncementRead, Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/announcements", tags=["公告管理"])

ANNOUNCEMENT_UPLOAD_DIR = "uploads/announcements"
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


class AnnouncementCreate(BaseModel):
    """创建公告请求体"""
    course_id: int | None = None        # 关联课程ID，null=全平台公告
    title: str                          # 公告标题（必填）
    content: str = ""                   # 公告正文
    image_urls: list[str] = []          # 公告图片URL列表
    popup: bool = False                 # 是否为强制弹窗公告
    priority: str = "normal"            # 优先级：normal/important/urgent


class AnnouncementUpdate(BaseModel):
    """更新公告请求体（所有字段可选）"""
    course_id: int | None = None
    title: str | None = None
    content: str | None = None
    image_urls: list[str] | None = None
    popup: bool | None = None
    priority: str | None = None


def _parse_image_urls(raw) -> list[str]:
    """安全解析 image_urls 字段（数据库存 JSON 字符串，返回 list）"""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _announcement_to_dict(a: Announcement, created_by_name: str = ""):
    """统一的公告序列化函数"""
    return {
        "id": a.id,
        "course_id": a.course_id,
        "title": a.title,
        "content": a.content,
        "image_urls": _parse_image_urls(a.image_urls),
        "popup": a.popup or False,
        "priority": a.priority,
        "created_by": a.created_by,
        "created_by_name": created_by_name,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


async def _get_creator_name(db: AsyncSession, user_id: int) -> str:
    """查询发布者姓名"""
    result = await db.execute(select(User).where(User.id == user_id))
    creator = result.scalar_one_or_none()
    return creator.name if creator else ""


@router.post("")
async def create_announcement(
    req: AnnouncementCreate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建公告

    请求参数：
        body.course_id (int|null):  关联课程ID，null=全平台公告
        body.title (str):           公告标题（必填）
        body.content (str):         公告正文
        body.priority (str):        优先级 normal/important/urgent

    权限要求：【teacher / admin】
    """
    # 校验课程存在（如果指定了 course_id）
    if req.course_id is not None:
        result = await db.execute(select(Course).where(Course.id == req.course_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="课程不存在")

    # 校验 priority 值合法
    if req.priority not in ("normal", "important", "urgent"):
        raise HTTPException(status_code=400, detail="priority 只能是 normal/important/urgent")

    announcement = Announcement(
        course_id=req.course_id,
        title=req.title,
        content=req.content,
        image_urls=json.dumps(req.image_urls),
        popup=req.popup,
        priority=req.priority,
        created_by=user.id,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    creator_name = await _get_creator_name(db, announcement.created_by)
    return {"code": 0, "data": _announcement_to_dict(announcement, creator_name)}


@router.get("")
async def list_announcements(
    course_id: int | None = Query(None, description="课程ID（可选，不传则查全部）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    公告列表（按 created_at DESC 排序）

    请求参数：
        query.course_id (int|null): 课程ID筛选（可选）

    权限要求：需登录
    过滤规则：学生只能看到已发布的公告（当前全部可见，后续可扩展 status 字段）
    """
    stmt = select(Announcement).order_by(Announcement.created_at.desc())

    if course_id is not None:
        # 筛选指定课程公告 + 全平台公告
        stmt = stmt.where(
            (Announcement.course_id == course_id) | (Announcement.course_id.is_(None))
        )

    result = await db.execute(stmt)
    announcements = result.scalars().all()

    data = []
    for a in announcements:
        creator_name = await _get_creator_name(db, a.created_by)
        data.append(_announcement_to_dict(a, creator_name))

    return {"code": 0, "data": data}


# ============================================================
# 固定路径路由（必须在 /{announcement_id} 之前注册，否则会被参数路由抢先匹配）
# ============================================================

@router.post("/upload-image")
async def upload_announcement_image(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    """
    上传公告图片

    权限要求：【teacher / admin】
    限制：仅 jpg/jpeg/png/gif/webp，单文件最大 10MB
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/gif/webp 格式")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    filename = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(ANNOUNCEMENT_UPLOAD_DIR, exist_ok=True)
    filepath = os.path.join(ANNOUNCEMENT_UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/announcements/{filename}"}}


@router.get("/unread-popups")
async def get_unread_popups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户未读的强制弹窗公告

    权限要求：需登录
    返回：popup=true 且当前用户未读的公告列表，按创建时间升序（先发的先弹）
    """
    # 查询所有 popup=true 的公告ID
    stmt = select(Announcement.id).where(Announcement.popup == True).order_by(Announcement.created_at.asc())
    result = await db.execute(stmt)
    popup_ids = [row[0] for row in result.all()]

    if not popup_ids:
        return {"code": 0, "data": []}

    # 查询该用户已读的公告ID
    read_stmt = select(AnnouncementRead.announcement_id).where(
        AnnouncementRead.user_id == user.id
    )
    read_result = await db.execute(read_stmt)
    read_ids = set(row[0] for row in read_result.all())

    # 过滤出未读的 popup 公告ID
    unread_popup_ids = [pid for pid in popup_ids if pid not in read_ids]

    if not unread_popup_ids:
        return {"code": 0, "data": []}

    # 查询完整公告对象（保持升序）
    stmt = select(Announcement).where(Announcement.id.in_(unread_popup_ids)).order_by(Announcement.created_at.asc())
    result = await db.execute(stmt)
    announcements = result.scalars().all()

    data = []
    for a in announcements:
        creator_name = await _get_creator_name(db, a.created_by)
        data.append(_announcement_to_dict(a, creator_name))

    return {"code": 0, "data": data}


@router.get("/unread-count")
async def get_unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的未读公告数量（排除 popup 公告，popup 有独立的弹窗追踪机制）

    权限要求：需登录
    逻辑：查询所有对该用户可见的非 popup 公告，减去已读记录数
    """
    # 查询所有可见公告的ID（排除 popup=true 的公告）
    stmt = select(Announcement.id).where(
        (Announcement.popup == False) | (Announcement.popup.is_(None))
    ).order_by(Announcement.created_at.desc())
    result = await db.execute(stmt)
    all_ids = [row[0] for row in result.all()]

    if not all_ids:
        return {"code": 0, "data": {"count": 0}}

    # 查询该用户已读的公告ID
    read_stmt = select(AnnouncementRead.announcement_id).where(
        AnnouncementRead.user_id == user.id
    )
    read_result = await db.execute(read_stmt)
    read_ids = set(row[0] for row in read_result.all())

    unread_count = len(all_ids) - len(read_ids.intersection(all_ids))
    return {"code": 0, "data": {"count": unread_count}}


@router.post("/mark-all-read")
async def mark_all_announcements_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    一键标记所有公告为已读（排除强制弹窗公告，popup 公告只能通过用户确认来标记已读）

    权限要求：需登录
    """
    # 查询所有可见公告ID（排除 popup=true 的公告）
    stmt = select(Announcement.id).where(
        (Announcement.popup == False) | (Announcement.popup.is_(None))
    )
    result = await db.execute(stmt)
    all_ids = [row[0] for row in result.all()]

    # 查询已读的公告ID
    read_stmt = select(AnnouncementRead.announcement_id).where(
        AnnouncementRead.user_id == user.id
    )
    read_result = await db.execute(read_stmt)
    read_ids = set(row[0] for row in read_result.all())

    # 批量插入未读公告的已读记录
    new_count = 0
    for aid in all_ids:
        if aid not in read_ids:
            db.add(AnnouncementRead(announcement_id=aid, user_id=user.id))
            new_count += 1

    await db.commit()
    return {"code": 0, "data": {"marked_count": new_count}}


# ============================================================
# 参数路径路由
# ============================================================

@router.get("/{announcement_id}")
async def get_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    公告详情

    权限要求：无需登录
    """
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")

    creator_name = await _get_creator_name(db, announcement.created_by)
    return {"code": 0, "data": _announcement_to_dict(announcement, creator_name)}


@router.put("/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    req: AnnouncementUpdate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新公告（部分更新）

    权限要求：【teacher / admin】
    """
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")

    update_data = req.model_dump(exclude_unset=True)

    # 校验 priority 值合法
    if "priority" in update_data and update_data["priority"] not in ("normal", "important", "urgent"):
        raise HTTPException(status_code=400, detail="priority 只能是 normal/important/urgent")

    # 校验课程存在（如果修改了 course_id）
    if "course_id" in update_data and update_data["course_id"] is not None:
        cr = await db.execute(select(Course).where(Course.id == update_data["course_id"]))
        if not cr.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="课程不存在")

    # image_urls 需要序列化为 JSON 字符串存入数据库
    if "image_urls" in update_data:
        update_data["image_urls"] = json.dumps(update_data["image_urls"])

    for key, value in update_data.items():
        setattr(announcement, key, value)

    await db.commit()
    await db.refresh(announcement)

    creator_name = await _get_creator_name(db, announcement.created_by)
    return {"code": 0, "data": _announcement_to_dict(announcement, creator_name)}


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除公告

    权限要求：【teacher / admin】
    """
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="公告不存在")

    # 先删除关联的已读记录，避免外键约束报错
    await db.execute(
        delete(AnnouncementRead).where(AnnouncementRead.announcement_id == announcement_id)
    )
    await db.delete(announcement)
    await db.commit()
    return {"code": 0, "data": {"id": announcement_id}}


@router.post("/{announcement_id}/read")
async def mark_announcement_read(
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    标记公告为已读

    权限要求：需登录
    逻辑：幂等操作，重复标记不报错
    """
    # 校验公告存在
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="公告不存在")

    # 检查是否已读
    existing = await db.execute(
        select(AnnouncementRead).where(
            (AnnouncementRead.announcement_id == announcement_id)
            & (AnnouncementRead.user_id == user.id)
        )
    )
    if existing.scalar_one_or_none():
        return {"code": 0, "data": {"already_read": True}}

    read_record = AnnouncementRead(
        announcement_id=announcement_id,
        user_id=user.id,
    )
    db.add(read_record)
    await db.commit()

    return {"code": 0, "data": {"already_read": False}}
