"""
公告管理模块 (announcement)

功能说明：
    提供公告通知的 CRUD 操作，教师/管理员发布，学生端首页展示。
    公告可绑定到具体课程（课程公告），也可为全平台公告（course_id=null）。

在系统中的角色：
    信息发布层——教师/管理员向学生推送通知，学生首页聚合展示。

API 列表：
    POST   /api/announcements                    — 创建公告
    GET    /api/announcements?course_id=x         — 公告列表
    GET    /api/announcements/{announcement_id}   — 公告详情
    PUT    /api/announcements/{announcement_id}   — 更新公告
    DELETE /api/announcements/{announcement_id}   — 删除公告

权限矩阵：
    创建公告：teacher / admin
    编辑公告：teacher / admin
    删除公告：teacher / admin
    查看公告：所有人（学生只能看到已发布的公告）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Announcement, AnnouncementRead, Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/announcements", tags=["公告管理"])


class AnnouncementCreate(BaseModel):
    """创建公告请求体"""
    course_id: int | None = None        # 关联课程ID，null=全平台公告
    title: str                          # 公告标题（必填）
    content: str = ""                   # 公告正文
    priority: str = "normal"            # 优先级：normal/important/urgent


class AnnouncementUpdate(BaseModel):
    """更新公告请求体（所有字段可选）"""
    course_id: int | None = None
    title: str | None = None
    content: str | None = None
    priority: str | None = None


def _announcement_to_dict(a: Announcement, created_by_name: str = ""):
    """统一的公告序列化函数"""
    return {
        "id": a.id,
        "course_id": a.course_id,
        "title": a.title,
        "content": a.content,
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

    await db.delete(announcement)
    await db.commit()
    return {"code": 0, "data": {"id": announcement_id}}


@router.get("/unread-count")
async def get_unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的未读公告数量

    权限要求：需登录
    逻辑：查询所有对该用户可见的公告，减去已读记录数
    """
    # 查询所有可见公告的ID（与列表接口同样的过滤规则）
    stmt = select(Announcement.id).order_by(Announcement.created_at.desc())
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


@router.post("/mark-all-read")
async def mark_all_announcements_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    一键标记所有公告为已读

    权限要求：需登录
    """
    # 查询所有可见公告ID
    stmt = select(Announcement.id)
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
