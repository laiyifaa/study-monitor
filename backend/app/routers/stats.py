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
    """
    班级学习概览 — 每个学生的有效学习时长和完成情况

    请求参数：
        query.course_id (int):    课程ID（必填）
        query.class_name (str):   班级名称过滤（可选，不传则显示所有班级）

    返回格式：
        code=0, data: {
            course_title, require_minutes,
            total_students, completed_students, completion_rate,
            students: [{ user_id, name, class_name, effective_minutes,
                        require_minutes, completion_rate, video_progress,
                        is_completed }, ...]
        }
    错误：404 课程不存在

    权限要求：【teacher / admin】

    核心业务逻辑：
        1. 按用户聚合 StudySession.effective_seconds 计算每人总有效时长
        2. 与课程要求时长(require_minutes)对比计算完成率
        3. 取最大视频进度（百分比）作为学生的视频观看进度
        4. 可按班级名过滤，支持多班级场景
    """
    # 获取课程信息（用于确定要求时长和课程标题）
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 聚合查询：按学生维度汇总有效时长和视频进度
    # 使用 SUM + MAX 聚合，即使有多次学习会话也能正确累计
    query = (
        select(
            StudySession.user_id,
            User.name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
            # 取所有会话中的最大视频进度，表示学生看过的最远位置
            func.max(StudySession.video_progress).label("max_progress"),
        )
        .join(User, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        # 【修复】只统计学生角色的学习数据，排除教师/管理员误入学习页面产生的记录
        .where(User.role == "student")
        .group_by(StudySession.user_id, User.name, User.class_name)
    )
    # 支持按班级过滤——22中有多个班级，教师可能只想看自己班级的数据
    if class_name:
        query = query.where(User.class_name == class_name)

    result = await db.execute(query)
    rows = result.all()

    # 计算每个学生的学习完成情况
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
            # 完成率上限100%，防止超额学习时显示超过100%
            "completion_rate": round(min(effective_min / require_minutes, 1), 3) if require_minutes else 0,
            "video_progress": round(float(r.max_progress), 1) if r.max_progress else 0,
            "is_completed": effective_min >= require_minutes,  # 布尔标记，前端可直接使用
        })

    # 汇总统计数据
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
    """
    我的学习进度 — 学生查看自己所有活跃课程的学习情况

    请求参数：无（通过 JWT Token 自动识别当前学生）

    返回格式：
        code=0, data: [
            { course_id, title, effective_minutes, require_minutes,
              completion_rate, video_progress, is_completed,
              last_study_time, end_date }, ...
        ]

    权限要求：已登录用户（任意角色）

    核心业务逻辑：
        1. 获取所有 active 状态的课程
        2. 对每个课程查询当前学生的聚合数据（总有效时长、最大进度、最后学习时间）
        3. 返回带完成状态标记的进度列表
    """
    # 获取所有活跃课程——学生只能看到 active 状态的课程
    courses_result = await db.execute(
        select(Course).where(Course.status == "active")
    )
    courses = courses_result.scalars().all()

    result_list = []
    for course in courses:
        # 对每个课程单独查询该学生的聚合统计
        # （使用循环而非JOIN，因为需要同时获取每个课程的独立统计）
        stats_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
                func.max(StudySession.video_progress).label("max_progress"),
                func.max(StudySession.last_heartbeat).label("last_study_time"),
            ).where(
                and_(
                    StudySession.user_id == user.id,  # 只查自己的数据
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
            # end_date 用于前端显示倒计时/截止提醒
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
