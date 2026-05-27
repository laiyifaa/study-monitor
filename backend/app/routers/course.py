import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse

from app.database import get_db
from app.models.models import Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/courses", tags=["课程管理"])

# 视频存储目录
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的视频格式
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


class CourseCreate(BaseModel):
    title: str
    description: str = ""
    video_type: str = "url"  # url 或 local
    video_url: str = ""
    duration_seconds: int = 0
    require_minutes: int = 60
    start_date: datetime | None = None
    end_date: datetime | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    video_type: str | None = None
    video_url: str | None = None
    duration_seconds: int | None = None
    require_minutes: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None


def _course_to_dict(c):
    """统一的课程序列化，兼容新旧字段"""
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "video_type": c.video_type or "url",
        # video_url 优先取新字段，兼容旧 wukong_url 数据
        "video_url": c.video_url or c.wukong_url or "",
        "duration_seconds": c.duration_seconds,
        "require_minutes": c.require_minutes,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "status": c.status,
        "teacher_id": c.teacher_id,
    }


@router.post("")
async def create_course(
    req: CourseCreate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """创建课程（老师/管理员）"""
    course = Course(
        title=req.title,
        description=req.description,
        video_type=req.video_type,
        video_url=req.video_url,
        wukong_url=req.video_url if req.video_type == "url" else "",
        duration_seconds=req.duration_seconds,
        teacher_id=user.id,
        require_minutes=req.require_minutes,
        start_date=req.start_date,
        end_date=req.end_date,
        status="active",
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {"code": 0, "data": {"id": course.id, "title": course.title}}


@router.get("")
async def list_courses(
    status: str = Query("active", description="课程状态过滤"),
    db: AsyncSession = Depends(get_db),
):
    """课程列表"""
    query = select(Course).order_by(Course.created_at.desc())
    if status != "all":
        query = query.where(Course.status == status)
    result = await db.execute(query)
    courses = result.scalars().all()
    return {"code": 0, "data": [_course_to_dict(c) for c in courses]}


@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    """课程详情"""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return {"code": 0, "data": _course_to_dict(course)}


@router.put("/{course_id}")
async def update_course(
    course_id: int,
    req: CourseUpdate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """更新课程"""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(course, key, value)
    # 同步 wukong_url 兼容
    if req.video_url is not None and (req.video_type or course.video_type) == "url":
        course.wukong_url = req.video_url
    await db.commit()
    return {"code": 0, "data": {"id": course.id}}


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """删除课程（仅管理员）"""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    # 删除本地视频文件
    if course.video_type == "local" and course.video_url:
        local_path = os.path.join(UPLOAD_DIR, course.video_url)
        if os.path.exists(local_path):
            os.remove(local_path)
    await db.delete(course)
    await db.commit()
    return {"code": 0, "data": {"id": course_id}}


@router.post("/{course_id}/upload-video")
async def upload_video(
    course_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """上传课程视频文件"""
    # 检查课程是否存在
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 检查文件格式
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式，允许: {', '.join(ALLOWED_EXTENSIONS)}")

    # 读取文件内容并检查大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="视频文件不能超过500MB")

    # 删除旧视频
    if course.video_type == "local" and course.video_url:
        old_path = os.path.join(UPLOAD_DIR, course.video_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    # 保存新文件
    filename = f"{course_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # 更新课程
    course.video_type = "local"
    course.video_url = filename
    course.wukong_url = ""
    await db.commit()

    return {"code": 0, "data": {"video_type": "local", "video_url": filename}}


@router.get("/video-file/{filename}")
async def serve_video(filename: str):
    """提供本地视频文件服务（路径独立于课程ID路由）"""
    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(filepath, media_type="video/mp4")
