"""
统计模块 (stats)

功能说明：
    提供学习数据的统计分析接口，覆盖教师看板和学生个人两个视角。
    教师可以查看班级整体学习进度、每日统计汇总、未完成学生名单；
    学生可以查看自己所有课程的学习进度、排行榜、签到日历。

在系统中的角色：
    数据展示层——从 StudySession 聚合有效学习时长，是教师看板前端的核心数据源。
    所有统计均基于 StudySession.effective_seconds（由心跳模块的 StudyEngine 计算），
    而非简单的在线时长，确保"有效学习"的真实性。

API 列表：
    GET /api/stats/class-overview      — 班级学习概览（教师）
    GET /api/stats/my-progress         — 我的学习进度（学生）
    GET /api/stats/daily-summary       — 每日学习统计（教师）
    GET /api/stats/incomplete-students — 未完成学生列表（教师）
    GET /api/stats/leaderboard         — 学习排行榜（按课程/班级，v4.0 新增）
    GET /api/stats/checkin-calendar    — 每日签到日历（v4.0 新增）
    GET /api/stats/study-report        — 学习总结报告（个人/班级/全平台，v4.0 新增）

权限矩阵：
    class-overview:      teacher / admin
    my-progress:         已登录用户（学生看自己的进度）
    daily-summary:       teacher / admin
    incomplete-students: teacher / admin
    leaderboard:         已登录用户
    checkin-calendar:    已登录用户
    study-report:        已登录用户（学生看自己的，教师看班级的，admin看全平台的）
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, case, extract
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

    require_minutes = course.require_minutes  # 可能是 None
    students = []
    for r in rows:
        effective_min = round(r.total_effective / 60, 1) if r.total_effective else 0
        students.append({
            "user_id": r.user_id,
            "name": r.name,
            "class_name": r.class_name,
            "effective_minutes": effective_min,
            "require_minutes": require_minutes,
            "completion_rate": round(min(effective_min / require_minutes, 1), 3) if require_minutes else None,
            "video_progress": round(float(r.max_progress), 1) if r.max_progress else 0,
            "is_completed": effective_min >= require_minutes if require_minutes else None,
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
        require_minutes = course.require_minutes  # 可能是 None

        # 查询该课程下所有小节
        sec_result = await db.execute(
            select(Section).where(Section.course_id == course.id).order_by(Section.sort_order, Section.id)
        )
        sections = sec_result.scalars().all()

        # 计算课程默认要求时长：所有小节视频时长之和（分钟）
        total_section_minutes = sum(sec.duration_seconds or 0 for sec in sections) / 60

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
            # 小节要求时长：默认等于视频时长（秒→分钟）
            sec_require_min = round((sec.duration_seconds or 0) / 60, 1)
            # 小节完成标准（方案C）：视频播放进度 >= 视频时长×90% 即视为完成
            # 优先使用 video_progress 判定（钉钉环境下 effective_seconds 不可靠），
            # 仅无视频时长时回退到 effective_seconds > 0
            if sec.duration_seconds and sec.duration_seconds > 0:
                sec_completed = sec_video_progress >= sec.duration_seconds * 0.9
            else:
                sec_completed = sec_effective > 0
            if sec_completed:
                completed_sections += 1
            section_progress.append({
                "section_id": sec.id,
                "title": sec.title,
                "sort_order": sec.sort_order,
                "effective_minutes": sec_effective,
                "require_minutes": sec_require_min,
                "video_progress": sec_video_progress,
                "is_completed": sec_completed,
            })

        # 课程完成率统一按已完成小节比例计算（方案C）
        # 小节完成判定已改为 video_progress >= duration × 90%，不再依赖 effective_seconds
        completion_rate = round(completed_sections / len(sections), 3) if sections else 0
        is_completed = completed_sections == len(sections) if sections else False

        result_list.append({
            "course_id": course.id,
            "title": course.title,
            "effective_minutes": effective_min,
            "require_minutes": require_minutes,
            "total_section_minutes": round(total_section_minutes, 1),
            "completion_rate": completion_rate,
            "is_completed": is_completed,
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

    require_minutes = course.require_minutes  # 可能是 None

    # 使用 HAVING 子句在聚合后过滤，只保留有效时长不足的学生
    # HAVING SUM(...) < require_minutes * 60  将要求分钟转为秒进行比较
    # 仅在设置了时长要求时过滤
    if require_minutes:
        query = (
            select(
                StudySession.user_id,
                User.name,
                User.class_name,
                func.sum(StudySession.effective_seconds).label("total_effective"),
            )
            .join(User, StudySession.user_id == User.id)
            .where(StudySession.course_id == course_id)
            .where(User.role == "student")
            .group_by(StudySession.user_id, User.name, User.class_name)
            .having(func.sum(StudySession.effective_seconds) < require_minutes * 60)
        )
    else:
        query = (
            select(
                StudySession.user_id,
                User.name,
                User.class_name,
                func.sum(StudySession.effective_seconds).label("total_effective"),
            )
            .join(User, StudySession.user_id == User.id)
            .where(StudySession.course_id == course_id)
            .where(User.role == "student")
            .group_by(StudySession.user_id, User.name, User.class_name)
        )
    result = await db.execute(query)
    incomplete = [
        {"user_id": r.user_id, "name": r.name, "class_name": r.class_name,
         "effective_minutes": round(r.total_effective / 60, 1)}
        for r in result.all()
    ]

    return {"code": 0, "data": {"course_title": course.title, "incomplete": incomplete}}


# ============================================================
# v4.0 新增：排行榜、签到日历、学习报告
# ============================================================


@router.get("/leaderboard")
async def leaderboard(
    course_id: int = Query(..., description="课程ID（必填）"),
    class_name: str | None = Query(None, description="班级名称筛选（可选）"),
    limit: int = Query(50, ge=1, le=200, description="返回人数上限"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    学习排行榜 — 按课程维度展示有效学习时长排名（v4.0 新增）

    请求参数：
        query.course_id (int):    课程ID（必填）
        query.class_name (str):   班级名称筛选（可选）
        query.limit (int):        返回人数上限（默认50）

    返回格式：
        code=0, data: {
            course_title: str,
            ranking: [
                { rank, user_id, name, real_name, class_name, effective_minutes }
            ]
        }

    权限要求：【已登录】

    业务逻辑：
        按 StudySession.effective_seconds 汇总排序，
        相同时长并列排名（如 1,2,2,4 而非 1,2,3,4）。
    """
    # 验证课程存在
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 按用户聚合有效时长
    query = (
        select(
            StudySession.user_id,
            User.name,
            User.real_name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
        )
        .join(User, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        .where(User.role == "student")
        .group_by(StudySession.user_id, User.name, User.real_name, User.class_name)
        .order_by(func.sum(StudySession.effective_seconds).desc())
        .limit(limit)
    )
    if class_name:
        query = (
            select(
                StudySession.user_id,
                User.name,
                User.real_name,
                User.class_name,
                func.sum(StudySession.effective_seconds).label("total_effective"),
            )
            .join(User, StudySession.user_id == User.id)
            .where(StudySession.course_id == course_id)
            .where(User.role == "student")
            .where(User.class_name == class_name)
            .group_by(StudySession.user_id, User.name, User.real_name, User.class_name)
            .order_by(func.sum(StudySession.effective_seconds).desc())
            .limit(limit)
        )

    result = await db.execute(query)
    rows = result.all()

    # 构建排名（并列排名逻辑）
    ranking = []
    prev_effective = None
    rank = 0
    skip = 0
    for i, r in enumerate(rows):
        effective_min = round(r.total_effective / 60, 1) if r.total_effective else 0
        if effective_min != prev_effective:
            rank = i + 1
            skip = 0
        else:
            skip += 1
        prev_effective = effective_min
        ranking.append({
            "rank": rank,
            "user_id": r.user_id,
            "name": r.name,
            "real_name": r.real_name or "",
            "class_name": r.class_name or "",
            "effective_minutes": effective_min,
        })

    return {
        "code": 0,
        "data": {
            "course_title": course.title,
            "ranking": ranking,
        },
    }


@router.get("/checkin-calendar")
async def checkin_calendar(
    year: int = Query(..., description="年份，如 2026"),
    month: int | None = Query(None, description="月份 1-12（可选，不传则查全年）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    每日签到日历 — GitHub 贡献图风格的学习记录（v4.0 新增）

    请求参数：
        query.year (int):   年份（必填）
        query.month (int):  月份 1-12（可选，不传则返回全年）

    返回格式：
        code=0, data: {
            year, month (nullable),
            days: [
                { date: "2026-07-01", has_study: true, effective_minutes: 45.2, study_count: 2 },
                ...
            ]
        }

    权限要求：【已登录】（学生看自己的记录）

    业务逻辑：
        从 StudySession 聚合每日有效学习时长，
        只要有 >0 的有效学习记录就算当日"签到"。
        查询个人数据，用于前端渲染类似 GitHub 贡献热力图。
    """
    if month is not None:
        # 查询单月
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="月份范围 1-12")
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
    else:
        # 查询全年
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)

    # 按日期聚合学习时长
    # MySQL: DATE(start_time) 分组
    result = await db.execute(
        select(
            func.date(StudySession.start_time).label("study_date"),
            func.sum(StudySession.effective_seconds).label("daily_effective"),
            func.count(StudySession.id).label("session_count"),
        )
        .where(
            and_(
                StudySession.user_id == user.id,
                StudySession.start_time >= start_date,
                StudySession.start_time < end_date,
            )
        )
        .group_by(func.date(StudySession.start_time))
        .order_by(func.date(StudySession.start_time))
    )
    rows = result.all()

    # 构建日期字典
    days = []
    for r in rows:
        effective_min = round(r.daily_effective / 60, 1) if r.daily_effective else 0
        days.append({
            "date": str(r.study_date),
            "has_study": effective_min > 0,
            "effective_minutes": effective_min,
            "study_count": r.session_count,
        })

    return {
        "code": 0,
        "data": {
            "year": year,
            "month": month,
            "days": days,
        },
    }


@router.get("/study-report")
async def study_report(
    report_type: str = Query("personal", description="报告类型：personal=个人/class=班级/platform=全平台"),
    course_id: int | None = Query(None, description="课程ID（可选，不传则汇总所有课程）"),
    class_name: str | None = Query(None, description="班级名称（class类型必填）"),
    user_id: int | None = Query(None, description="目标用户ID（personal类型，不填则查自己）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    学习总结报告 — 个人/班级/全平台三维度报告（v4.0 新增）

    请求参数：
        query.report_type (str): 报告类型 personal/class/platform
        query.course_id (int):   课程ID（可选，不传则汇总所有课程）
        query.class_name (str):  班级名称（class类型时使用）
        query.user_id (int):     目标用户ID（personal类型，不填则查自己）

    返回格式：
        code=0, data: {
            report_type, generated_at,
            personal: { ... },       // report_type=personal 时
            class_summary: { ... },  // report_type=class 时
            platform_summary: { ... } // report_type=platform 时
        }

    权限要求：
        - personal: 已登录（学生看自己，admin可指定user_id）
        - class: teacher / admin
        - platform: admin

    业务逻辑：
        按需聚合有效学习时长、完成率、每日分布等维度，
        生成结构化报告数据，前端可直接渲染。
    """
    now = datetime.now()

    if report_type == "personal":
        # 个人报告
        target_user_id = user_id if user_id and user.role in ("admin", "teacher") else user.id

        # 如果指定了课程，查单课程；否则查全部
        if course_id:
            course_filter = StudySession.course_id == course_id
            courses_result = await db.execute(select(Course).where(Course.id == course_id))
            courses = courses_result.scalars().all()
        else:
            course_filter = StudySession.user_id > 0  # 无过滤
            courses_result = await db.execute(select(Course).where(Course.status == "active"))
            courses = courses_result.scalars().all()

        # 总体统计
        total_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
                func.count(StudySession.id).label("total_sessions"),
                func.max(StudySession.last_heartbeat).label("last_study_time"),
            ).where(
                and_(
                    StudySession.user_id == target_user_id,
                    course_filter if course_id else StudySession.user_id > 0,
                )
            )
        )
        total = total_result.one()
        total_effective_min = round(total.total_effective / 60, 1) if total.total_effective else 0

        # 每个课程的进度
        course_progress = []
        for c in courses:
            c_result = await db.execute(
                select(
                    func.sum(StudySession.effective_seconds).label("c_effective"),
                    func.count(StudySession.id).label("c_sessions"),
                ).where(
                    and_(
                        StudySession.user_id == target_user_id,
                        StudySession.course_id == c.id,
                    )
                )
            )
            c_data = c_result.one()
            c_effective = round(c_data.c_effective / 60, 1) if c_data.c_effective else 0
            require_minutes = c.require_minutes  # 可能是 None
            course_progress.append({
                "course_id": c.id,
                "title": c.title,
                "effective_minutes": c_effective,
                "require_minutes": require_minutes,
                "completion_rate": round(min(c_effective / require_minutes, 1), 3) if require_minutes else None,
                "is_completed": c_effective >= require_minutes if require_minutes else None,
            })

        # 最近7天每日学习时长分布
        seven_days_ago = now - timedelta(days=7)
        daily_result = await db.execute(
            select(
                func.date(StudySession.start_time).label("study_date"),
                func.sum(StudySession.effective_seconds).label("daily_effective"),
            ).where(
                and_(
                    StudySession.user_id == target_user_id,
                    StudySession.start_time >= seven_days_ago,
                )
            )
            .group_by(func.date(StudySession.start_time))
            .order_by(func.date(StudySession.start_time))
        )
        daily_distribution = [
            {
                "date": str(r.study_date),
                "effective_minutes": round(r.daily_effective / 60, 1) if r.daily_effective else 0,
            }
            for r in daily_result.all()
        ]

        # 获取用户信息
        user_result = await db.execute(select(User).where(User.id == target_user_id))
        target_user = user_result.scalar_one_or_none()
        user_name = target_user.name if target_user else ""
        user_real_name = target_user.real_name if target_user else ""

        return {
            "code": 0,
            "data": {
                "report_type": "personal",
                "generated_at": now.isoformat(),
                "user_id": target_user_id,
                "user_name": user_name,
                "real_name": user_real_name,
                "total_effective_minutes": total_effective_min,
                "total_sessions": total.total_sessions or 0,
                "last_study_time": str(total.last_study_time) if total.last_study_time else None,
                "course_progress": course_progress,
                "daily_distribution_7d": daily_distribution,
            },
        }

    elif report_type == "class":
        # 班级报告
        if user.role not in ("teacher", "admin"):
            raise HTTPException(status_code=403, detail="仅教师/管理员可查看班级报告")
        if not class_name:
            raise HTTPException(status_code=400, detail="班级报告需指定 class_name")

        # 班级学生数
        student_count = await db.scalar(
            select(func.count(User.id)).where(
                and_(User.class_name == class_name, User.role == "student")
            )
        ) or 0

        # 班级总体学习统计
        session_filter = [
            User.class_name == class_name,
            User.role == "student",
        ]
        if course_id:
            session_filter.append(StudySession.course_id == course_id)

        class_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
                func.count(func.distinct(StudySession.user_id)).label("active_students"),
                func.avg(
                    select(func.sum(StudySession.effective_seconds))
                    .where(StudySession.user_id == User.id)
                    .correlate(User)
                    .scalar_subquery()
                ).label("avg_effective"),
            )
            .join(User, StudySession.user_id == User.id)
            .where(and_(*session_filter))
        )
        class_data = class_result.one()
        total_effective_min = round(class_data.total_effective / 60, 1) if class_data.total_effective else 0
        active_students = class_data.active_students or 0

        # 班级每个学生的学习时长排名
        ranking_query = (
            select(
                StudySession.user_id,
                User.name,
                User.real_name,
                func.sum(StudySession.effective_seconds).label("total_effective"),
            )
            .join(User, StudySession.user_id == User.id)
            .where(and_(*session_filter))
            .group_by(StudySession.user_id, User.name, User.real_name)
            .order_by(func.sum(StudySession.effective_seconds).desc())
        )
        ranking_result = await db.execute(ranking_query)
        ranking = [
            {
                "user_id": r.user_id,
                "name": r.name,
                "real_name": r.real_name or "",
                "effective_minutes": round(r.total_effective / 60, 1) if r.total_effective else 0,
            }
            for r in ranking_result.all()
        ]

        return {
            "code": 0,
            "data": {
                "report_type": "class",
                "generated_at": now.isoformat(),
                "class_name": class_name,
                "total_students": student_count,
                "active_students": active_students,
                "total_effective_minutes": total_effective_min,
                "avg_effective_minutes": round(total_effective_min / max(active_students, 1), 1),
                "participation_rate": round(active_students / max(student_count, 1), 3),
                "ranking": ranking,
            },
        }

    elif report_type == "platform":
        # 全平台报告（仅admin）
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可查看全平台报告")

        # 全局统计
        total_students = await db.scalar(
            select(func.count(User.id)).where(User.role == "student")
        ) or 0

        total_teachers = await db.scalar(
            select(func.count(User.id)).where(User.role == "teacher")
        ) or 0

        total_courses = await db.scalar(
            select(func.count(Course.id)).where(Course.status == "active")
        ) or 0

        # 全平台学习统计
        platform_result = await db.execute(
            select(
                func.sum(StudySession.effective_seconds).label("total_effective"),
                func.count(func.distinct(StudySession.user_id)).label("active_students"),
                func.count(StudySession.id).label("total_sessions"),
            )
        )
        p_data = platform_result.one()
        total_effective_min = round(p_data.total_effective / 60, 1) if p_data.total_effective else 0

        # 各班级统计
        classes_result = await db.execute(
            select(
                User.class_name,
                func.count(func.distinct(StudySession.user_id)).label("active_students"),
                func.sum(StudySession.effective_seconds).label("total_effective"),
            )
            .join(StudySession, StudySession.user_id == User.id)
            .where(and_(User.role == "student", User.class_name != ""))
            .group_by(User.class_name)
            .order_by(User.class_name)
        )
        class_stats = [
            {
                "class_name": r.class_name,
                "active_students": r.active_students or 0,
                "total_effective_minutes": round(r.total_effective / 60, 1) if r.total_effective else 0,
            }
            for r in classes_result.all()
        ]

        return {
            "code": 0,
            "data": {
                "report_type": "platform",
                "generated_at": now.isoformat(),
                "total_students": total_students,
                "total_teachers": total_teachers,
                "total_courses": total_courses,
                "active_students": p_data.active_students or 0,
                "total_effective_minutes": total_effective_min,
                "total_sessions": p_data.total_sessions or 0,
                "class_stats": class_stats,
            },
        }

    else:
        raise HTTPException(status_code=400, detail="report_type 只能是 personal/class/platform")
