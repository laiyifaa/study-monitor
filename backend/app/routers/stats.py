"""
统计模块 (stats)

功能说明：
    提供学习数据的统计分析接口，覆盖教师看板和学生个人两个视角。
    教师可以查看班级整体学习进度、每日统计汇总、未完成学生名单；
    学生可以查看自己所有课程的学习进度。

在系统中的角色：
    数据展示层——从 StudySession 聚合有效学习时长，是教师看板前端的核心数据源。
    所有统计均基于 StudySession.effective_seconds（由心跳模块的 StudyEngine 计算），
    而非简单的在线时长，确保"有效学习"的真实性。

API 列表：
    GET /api/stats/class-overview      — 班级学习概览（教师）
    GET /api/stats/my-progress         — 我的学习进度（学生）
    GET /api/stats/daily-summary       — 每日学习统计（教师）
    GET /api/stats/incomplete-students — 未完成学生列表（教师）

权限矩阵：
    class-overview:      teacher / admin
    my-progress:         已登录用户（学生看自己的进度）
    daily-summary:       teacher / admin
    incomplete-students: teacher / admin
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import StudySession, Course, Section, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("/class-overview")
async def class_overview(
    course_id: int = Query(...),
    class_name: str | None = Query(None),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    班级学习概览 — 每个学生的有效学习时长和完成情况（按课程维度聚合）

    权限要求：【teacher / admin】
    """
    # 获取课程信息
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询小节数量
    section_count = await db.scalar(
        select(func.count(Section.id)).where(Section.course_id == course_id)
    ) or 0

    # 聚合查询：按学生维度汇总有效时长和视频进度
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
        .where(User.role == "student")
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
            "section_count": section_count,
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
    """
    我的学习进度 — 学生查看自己所有活跃课程的学习情况（按课程聚合，含小节子进度）

    返回格式：
        code=0, data: [
            { course_id, title, effective_minutes, require_minutes,
              completion_rate, is_completed, section_count, completed_sections,
              sections: [{ section_id, title, effective_minutes, video_progress,
                           is_completed }], ... },
        ]

    权限要求：已登录用户
    """
    # 获取所有活跃课程
    courses_result = await db.execute(
        select(Course).where(Course.status == "active")
    )
    courses = courses_result.scalars().all()

    result_list = []
    for course in courses:
        # 课程维度聚合
        stats_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
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

        # 查询该课程下所有小节
        sec_result = await db.execute(
            select(Section).where(Section.course_id == course.id).order_by(Section.sort_order, Section.id)
        )
        sections = sec_result.scalars().all()

        # 每个小节的进度
        section_progress = []
        completed_sections = 0
        for sec in sections:
            sec_stats = await db.execute(
                select(
                    func.sum(StudySession.effective_seconds).label("sec_effective"),
                    func.max(StudySession.video_progress).label("sec_progress"),
                ).where(
                    and_(
                        StudySession.user_id == user.id,
                        StudySession.section_id == sec.id,
                    )
                )
            )
            sec_s = sec_stats.one()
            sec_effective = round(sec_s.sec_effective / 60, 1) if sec_s.sec_effective else 0
            sec_video_progress = round(float(sec_s.sec_progress), 1) if sec_s.sec_progress else 0
            # 小节完成标准：有有效学习时长（>0）即视为已学习
            sec_completed = sec_effective > 0
            if sec_completed:
                completed_sections += 1
            section_progress.append({
                "section_id": sec.id,
                "title": sec.title,
                "sort_order": sec.sort_order,
                "effective_minutes": sec_effective,
                "video_progress": sec_video_progress,
                "is_completed": sec_completed,
            })

        result_list.append({
            "course_id": course.id,
            "title": course.title,
            "effective_minutes": effective_min,
            "require_minutes": require_minutes,
            "completion_rate": round(min(effective_min / require_minutes, 1), 3),
            "is_completed": effective_min >= require_minutes,
            "last_study_time": str(stats.last_study_time) if stats.last_study_time else None,
            "end_date": str(course.end_date) if course.end_date else None,
            "section_count": len(sections),
            "completed_sections": completed_sections,
            "sections": section_progress,
        })

    return {"code": 0, "data": result_list}


@router.get("/daily-summary")
async def daily_summary(
    course_id: int = Query(...),
    date: str | None = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    每日学习统计 — 某一天的班级学习概况

    请求参数：
        query.course_id (int):  课程ID（必填）
        query.date (str):       日期字符串 YYYY-MM-DD（可选，默认今天）

    返回格式：
        code=0, data: {
            date, active_students, total_effective_minutes, avg_effective_minutes
        }

    权限要求：【teacher / admin】

    核心业务逻辑：
        统计指定日期内的：
        1. 活跃学习人数（当天有学习记录的不重复学生数）
        2. 全班总有效学习时长
        3. 人均有效学习时长

    注意事项：
        按 start_time 筛选日期范围（而非 last_heartbeat），
        因为 start_time 代表会话开始日期，更符合"当天学习"的语义。
    """
    # 解析目标日期，默认为今天
    target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    # 构造当天的起止时间范围 [day_start, day_end)
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # 当天学习人数（去重计数，同一学生多次会话只计一次）
    active_count = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            and_(
                StudySession.course_id == course_id,
                StudySession.start_time >= day_start,
                StudySession.start_time < day_end,
            )
        )
    )

    # 当天总有效学习时长（所有学生所有会话的累计）
    total_effective = await db.scalar(
        select(func.sum(StudySession.effective_seconds)).where(
            and_(
                StudySession.course_id == course_id,
                StudySession.start_time >= day_start,
                StudySession.start_time < day_end,
            )
        )
    )

    # 人均有效时长：总时长/活跃人数，分母为0时返回0避免除零错误
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
    """
    未完成学生列表 — 获取有效学习时长未达到要求的学生

    请求参数：
        query.course_id (int): 课程ID（必填）

    返回格式：
        code=0, data: { course_title, incomplete: [{ user_id, name, class_name, effective_minutes }] }
    错误：404 课程不存在

    权限要求：【teacher / admin】

    核心业务逻辑：
        1. 获取课程的要求时长
        2. 聚合每个学生的总有效时长
        3. 用 HAVING 子句过滤出未达标的学生
        4. 用于教师针对性催促未完成的学生

    注意事项：
        此接口只返回"有学习记录但未完成"的学生，完全未开始学习的学生不会出现在结果中。
        这是设计选择——零记录学生通常需要另外的处理方式（如单独通知）。
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    require_minutes = course.require_minutes or 60

    # 使用 HAVING 子句在聚合后过滤，只保留有效时长不足的学生
    # HAVING SUM(...) < require_minutes * 60  将要求分钟转为秒进行比较
    query = (
        select(
            StudySession.user_id,
            User.name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
        )
        .join(User, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        # 【修复】只统计学生角色，排除教师/管理员
        .where(User.role == "student")
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
