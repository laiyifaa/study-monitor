from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/courses", tags=["课程管理"])


class CourseCreate(BaseModel):
    title: str
    description: str = ""
    wukong_url: str = ""
    duration_seconds: int = 0
    require_minutes: int = 60
    start_date: datetime | None = None
    end_date: datetime | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    wukong_url: str | None = None
    duration_seconds: int | None = None
    require_minutes: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None


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
        wukong_url=req.wukong_url,
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
    return {
        "code": 0,
        "data": [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "wukong_url": c.wukong_url,
                "duration_seconds": c.duration_seconds,
                "require_minutes": c.require_minutes,
                "start_date": str(c.start_date) if c.start_date else None,
                "end_date": str(c.end_date) if c.end_date else None,
                "status": c.status,
                "teacher_id": c.teacher_id,
            }
            for c in courses
        ],
    }


@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    """课程详情"""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return {
        "code": 0,
        "data": {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "wukong_url": course.wukong_url,
            "duration_seconds": course.duration_seconds,
            "require_minutes": course.require_minutes,
            "start_date": str(course.start_date) if course.start_date else None,
            "end_date": str(course.end_date) if course.end_date else None,
            "status": course.status,
            "teacher_id": course.teacher_id,
        },
    }


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
    await db.delete(course)
    await db.commit()
    return {"code": 0, "data": {"id": course_id}}
