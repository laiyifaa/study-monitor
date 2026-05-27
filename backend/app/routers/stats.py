from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import StudySession, Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("/class-overview")
async def class_overview(
    course_id: int = Query(...),
    class_name: str | None = Query(None),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """班级学习概览：每个学生的有效时长和进度"""
    # 获取课程信息
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询所有学生的有效时长（聚合）
    query = (
        select(
            StudySession.user_id,
            User.name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
            func.max(StudySession.video_progress).label("max_progress"),
        )
        .join(User, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        .group_by(StudySession.user_id, User.name, User.class_name)
    )
    if class_name:
        query = query.where(User.class_name == class_name)

    result = await db.execute(query)
    rows = result.all()

    require_minutes = course.require_minutes or 60
    students = []
    for r in rows:
        effective_min = round(r.total_effective / 60, 1) if r.total_effective else 0
        students.append({
            "user_id": r.user_id,
            "name": r.name,
            "class_name": r.class_name,
            "effective_minutes": effective_min,
            "require_minutes": require_minutes,
            "completion_rate": round(min(effective_min / require_minutes, 1), 3) if require_minutes else 0,
            "video_progress": round(float(r.max_progress), 1) if r.max_progress else 0,
            "is_completed": effective_min >= require_minutes,
        })

    total = len(students)
    completed = sum(1 for s in students if s["is_completed"])
    return {
        "code": 0,
        "data": {
            "course_title": course.title,
            "require_minutes": require_minutes,
            "total_students": total,
            "completed_students": completed,
            "completion_rate": round(completed / total, 3) if total else 0,
            "students": students,
        },
    }


@router.get("/my-progress")
async def my_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学生查看自己的学习进度"""
    # 获取所有活跃课程
    courses_result = await db.execute(
        select(Course).where(Course.status == "active")
    )
    courses = courses_result.scalars().all()

    result_list = []
    for course in courses:
        # 查询该学生该课程的聚合数据
        stats_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
                func.max(StudySession.video_progress).label("max_progress"),
                func.max(StudySession.last_heartbeat).label("last_study_time"),
            ).where(
                and_(
                    StudySession.user_id == user.id,
                    StudySession.course_id == course.id,
                )
            )
        )
        stats = stats_result.one()

        effective_min = round(stats.total_effective / 60, 1) if stats.total_effective else 0
        require_minutes = course.require_minutes or 60
        result_list.append({
            "course_id": course.id,
            "title": course.title,
            "effective_minutes": effective_min,
            "require_minutes": require_minutes,
            "completion_rate": round(min(effective_min / require_minutes, 1), 3),
            "video_progress": round(float(stats.max_progress), 1) if stats.max_progress else 0,
            "is_completed": effective_min >= require_minutes,
            "last_study_time": str(stats.last_study_time) if stats.last_study_time else None,
            "end_date": str(course.end_date) if course.end_date else None,
        })

    return {"code": 0, "data": result_list}


@router.get("/daily-summary")
async def daily_summary(
    course_id: int = Query(...),
    date: str | None = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """每日学习统计"""
    target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # 当天学习人数
    active_count = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            and_(
                StudySession.course_id == course_id,
                StudySession.start_time >= day_start,
                StudySession.start_time < day_end,
            )
        )
    )

    # 当天总有效时长
    total_effective = await db.scalar(
        select(func.sum(StudySession.effective_seconds)).where(
            and_(
                StudySession.course_id == course_id,
                StudySession.start_time >= day_start,
                StudySession.start_time < day_end,
            )
        )
    )

    avg_minutes = round((total_effective or 0) / 60 / max(active_count or 1, 1), 1)

    return {
        "code": 0,
        "data": {
            "date": target_date.strftime("%Y-%m-%d"),
            "active_students": active_count or 0,
            "total_effective_minutes": round((total_effective or 0) / 60, 1),
            "avg_effective_minutes": avg_minutes,
        },
    }


@router.get("/incomplete-students")
async def incomplete_students(
    course_id: int = Query(...),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """获取未完成学习的学生列表"""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    require_minutes = course.require_minutes or 60

    # 有学习记录但未完成的学生
    query = (
        select(
            StudySession.user_id,
            User.name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
        )
        .join(User, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        .group_by(StudySession.user_id, User.name, User.class_name)
        .having(func.sum(StudySession.effective_seconds) < require_minutes * 60)
    )
    result = await db.execute(query)
    incomplete = [
        {"user_id": r.user_id, "name": r.name, "class_name": r.class_name,
         "effective_minutes": round(r.total_effective / 60, 1)}
        for r in result.all()
    ]

    return {"code": 0, "data": {"course_title": course.title, "incomplete": incomplete}}
