"""
小节管理模块 (section)

功能说明：
    提供课程小节的 CRUD 操作和视频文件上传服务。
    小节是课程下的视频单元，一门课包含多个小节，学生针对小节学习计时。

在系统中的角色：
    内容管理层——管理课程下的学习资源，是心跳模块（学生学小节）的基础。

API 列表：
    POST   /api/sections                        — 创建小节
    GET    /api/sections?course_id=x             — 课程下的小节列表
    GET    /api/sections/{section_id}            — 小节详情
    PUT    /api/sections/{section_id}            — 更新小节
    DELETE /api/sections/{section_id}            — 删除小节
    POST   /api/sections/{section_id}/upload-video — 上传小节视频

权限矩阵：
    创建小节：teacher / admin
    编辑小节：teacher / admin
    删除小节：teacher / admin
    查看小节：所有人
    上传视频：teacher / admin
"""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Section, Course, User
from app.utils.jwt_helper import require_role
from app.config import get_settings

router = APIRouter(prefix="/api/sections", tags=["小节管理"])

# 视频文件存储目录（与课程共用同一目录）
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}
MAX_FILE_SIZE = 500 * 1024 * 1024


class SectionCreate(BaseModel):
    """创建小节请求体"""
    course_id: int                      # 所属课程ID（必填）
    title: str                          # 小节标题（必填）
    sort_order: int = 0                 # 排序序号，默认0
    video_type: str = "url"             # 视频类型：url 或 local
    video_url: str = ""                 # 视频URL（video_type=url时填写）
    duration_seconds: int = 0           # 视频时长（秒）


class SectionUpdate(BaseModel):
    """更新小节请求体（所有字段可选）"""
    title: str | None = None
    sort_order: int | None = None
    video_type: str | None = None
    video_url: str | None = None
    duration_seconds: int | None = None


def _section_to_dict(s: Section):
    """
    统一的小节序列化函数

    CDN 支持：
        当后端配置了 CDN_DOMAIN 时，本地视频会额外返回 video_cdn_url 字段。
    """
    settings = get_settings()
    video_url_val = s.video_url or ""
    video_cdn_url = ""
    if (s.video_type or "url") == "local" and video_url_val and settings.CDN_DOMAIN:
        cdn_base = settings.CDN_DOMAIN.rstrip("/")
        video_cdn_url = f"{cdn_base}/uploads/videos/{video_url_val}"

    return {
        "id": s.id,
        "course_id": s.course_id,
        "title": s.title,
        "sort_order": s.sort_order,
        "video_type": s.video_type or "url",
        "video_url": video_url_val,
        "video_cdn_url": video_cdn_url,
        "duration_seconds": s.duration_seconds,
    }


@router.post("")
async def create_section(
    req: SectionCreate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建小节

    请求参数：
        body.course_id (int):       所属课程ID（必填）
        body.title (str):           小节标题（必填）
        body.sort_order (int):      排序序号
        body.video_type (str):      视频类型
        body.video_url (str):       视频链接
        body.duration_seconds (int): 视频时长

    权限要求：【teacher / admin】
    """
    # 校验课程存在
    result = await db.execute(select(Course).where(Course.id == req.course_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="课程不存在")

    section = Section(
        course_id=req.course_id,
        title=req.title,
        sort_order=req.sort_order,
        video_type=req.video_type,
        video_url=req.video_url,
        duration_seconds=req.duration_seconds,
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return {"code": 0, "data": {"id": section.id, "title": section.title}}


@router.get("")
async def list_sections(
    course_id: int = Query(..., description="课程ID（必填）"),
    db: AsyncSession = Depends(get_db),
):
    """
    课程下的小节列表（按 sort_order 排序）

    请求参数：
        query.course_id (int): 课程ID（必填）

    权限要求：无需登录
    """
    result = await db.execute(
        select(Section)
        .where(Section.course_id == course_id)
        .order_by(Section.sort_order, Section.id)
    )
    sections = result.scalars().all()
    return {"code": 0, "data": [_section_to_dict(s) for s in sections]}


@router.get("/{section_id}")
async def get_section(section_id: int, db: AsyncSession = Depends(get_db)):
    """
    小节详情

    权限要求：无需登录
    """
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="小节不存在")
    return {"code": 0, "data": _section_to_dict(section)}


@router.put("/{section_id}")
async def update_section(
    section_id: int,
    req: SectionUpdate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新小节（部分更新）

    权限要求：【teacher / admin】
    """
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="小节不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(section, key, value)
    await db.commit()
    return {"code": 0, "data": {"id": section.id}}


@router.delete("/{section_id}")
async def delete_section(
    section_id: int,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除小节（同时删除本地视频文件）

    权限要求：【teacher / admin】
    """
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="小节不存在")

    # 删除本地视频文件
    if section.video_type == "local" and section.video_url:
        local_path = os.path.join(UPLOAD_DIR, section.video_url)
        if os.path.exists(local_path):
            os.remove(local_path)

    await db.delete(section)
    await db.commit()
    return {"code": 0, "data": {"id": section_id}}


@router.post("/{section_id}/upload-video")
async def upload_video(
    section_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    上传小节视频文件

    权限要求：【teacher / admin】
    安全说明：同课程视频上传，格式白名单 + 大小限制 + UUID 文件名
    """
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="小节不存在")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式，允许: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="视频文件不能超过500MB")

    # 删除旧视频
    if section.video_type == "local" and section.video_url:
        old_path = os.path.join(UPLOAD_DIR, section.video_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    # 使用 s_{section_id}_{uuid} 命名，与课程视频命名风格一致
    filename = f"s_{section_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    section.video_type = "local"
    section.video_url = filename
    await db.commit()

    return {"code": 0, "data": {"video_type": "local", "video_url": filename}}
