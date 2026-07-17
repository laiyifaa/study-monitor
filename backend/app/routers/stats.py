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
from sqlalchemy import select, func, and_, case, extract, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import StudySession, Course, Section, User, ClassDef
from app.utils.datetime_helper import now_cn_naive
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("/class-overview")
async def class_overview(
    course_id: int = Query(...),
    class_name: str | None = Query(None),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    search: str | None = Query(None, description="按姓名搜索"),
    sort_by: str = Query("name", description="排序：name/completion_desc/completion_asc/minutes_desc"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    班级学习概览 — 每个学生的有效学习时长和完成情况（按小节数量维度聚合）

    v5.1 改动：
      - 完成率从时间维度改为小节数量维度（completed_sections / total_sections）
      - 新增分页（page / page_size）
      - 新增搜索（search）和排序（sort_by），改为后端处理
      - "未开始"学生通过 LEFT JOIN 一并返回，不再需要前端差集

    权限要求：【teacher / admin】
    """
    # 获取课程信息
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询该课程下所有小节（用于完成判定）
    sec_result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.sort_order, Section.id)
    )
    sections = sec_result.scalars().all()
    section_count = len(sections)
    # 构建 section_id → duration_seconds 映射（小节完成判定用）
    section_duration_map = {s.id: s.duration_seconds or 0 for s in sections}

    # 子查询：按 (user_id, section_id) 取每小节最大 video_progress
    subq = (
        select(
            StudySession.user_id,
            StudySession.section_id,
            func.max(StudySession.video_progress).label("max_progress"),
            func.sum(StudySession.effective_seconds).label("sec_effective"),
        )
        .where(StudySession.course_id == course_id)
        .group_by(StudySession.user_id, StudySession.section_id)
        .subquery()
    )

    # 子查询2：按 user_id 聚合——统计完成小节数 + 总有效时长 + 最大视频进度
    user_stats = (
        select(
            subq.c.user_id,
            func.sum(subq.c.sec_effective).label("total_effective"),
            func.max(subq.c.max_progress).label("max_progress"),
        )
        .group_by(subq.c.user_id)
        .subquery()
    )

    # 完成 JSON 标量：标记每个 section 是否完成（用于统计 completed_sections）
    # 用 case when 在 SQL 层面判定，避免 N+1
    # 但 MySQL 不支持在子查询外用窗口函数累积计数，这里改为在应用层计算

    # 主查询：LEFT JOIN users 表，确保"未开始"学生也出现在列表中
    # 注意：LEFT JOIN 需要 users.role='student' 作为基础，study_session 为可选
    base_query = (
        select(
            User.id.label("user_id"),
            User.name,
            User.class_name,
            func.coalesce(user_stats.c.total_effective, 0).label("total_effective"),
            func.coalesce(user_stats.c.max_progress, 0).label("max_progress"),
        )
        .outerjoin(user_stats, user_stats.c.user_id == User.id)
        .where(User.role == "student")
    )

    # 班级筛选
    if class_name:
        base_query = base_query.where(User.class_name == class_name)

    # 姓名搜索
    if search:
        base_query = base_query.where(User.name.like(f"%{search}%"))

    # 先查总数（不分页）
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # ---- 排序 + 分页 ----
    # 由于完成小节数需要在应用层计算（依赖 section_duration_map），
    # 对于 completion 相关排序，需要先取全量再排序再分页。
    # 但学生数最多781，全量取出后内存排序完全可行。
    if sort_by in ("completion_desc", "completion_asc", "minutes_desc"):
        # 需要全量取出来在应用层排序
        result = await db.execute(base_query)
        rows = result.all()

        # 计算每个学生的小节完成数
        student_list = []
        for r in rows:
            effective_min = round(float(r.total_effective) / 60, 1) if r.total_effective else 0
            # 查询该学生各小节完成情况
            sec_progress_result = await db.execute(
                select(subq.c.section_id, subq.c.max_progress)
                .where(subq.c.user_id == r.user_id)
            )
            completed_sections = 0
            for sr in sec_progress_result.all():
                dur = section_duration_map.get(sr.section_id, 0)
                if dur and dur > 0:
                    if float(sr.max_progress or 0) >= dur * 0.9:
                        completed_sections += 1
                else:
                    # 无视频时长的小节，有学习记录就算完成
                    if float(sr.max_progress or 0) > 0:
                        completed_sections += 1

            student_list.append({
                "user_id": r.user_id,
                "name": r.name,
                "class_name": r.class_name,
                "effective_minutes": effective_min,
                "require_minutes": course.require_minutes,
                "completed_sections": completed_sections,
                "total_sections": section_count,
                "completion_rate": round(completed_sections / section_count, 3) if section_count else 0,
                "video_progress": round(float(r.max_progress), 1) if r.max_progress else 0,
                "is_completed": completed_sections >= section_count if section_count else False,
            })

        # 排序
        if sort_by == "completion_desc":
            student_list.sort(key=lambda x: x["completion_rate"], reverse=True)
        elif sort_by == "completion_asc":
            student_list.sort(key=lambda x: x["completion_rate"])
        elif sort_by == "minutes_desc":
            student_list.sort(key=lambda x: x["effective_minutes"], reverse=True)

        # 分页切片
        offset = (page - 1) * page_size
        students = student_list[offset:offset + page_size]

    else:
        # 默认按姓名排序，可以直接在SQL层分页
        base_query = base_query.order_by(User.name)
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await db.execute(base_query)
        rows = result.all()

        students = []
        for r in rows:
            effective_min = round(float(r.total_effective) / 60, 1) if r.total_effective else 0
            # 查询该学生各小节完成情况
            sec_progress_result = await db.execute(
                select(subq.c.section_id, subq.c.max_progress)
                .where(subq.c.user_id == r.user_id)
            )
            completed_sections = 0
            for sr in sec_progress_result.all():
                dur = section_duration_map.get(sr.section_id, 0)
                if dur and dur > 0:
                    if float(sr.max_progress or 0) >= dur * 0.9:
                        completed_sections += 1
                else:
                    if float(sr.max_progress or 0) > 0:
                        completed_sections += 1

            students.append({
                "user_id": r.user_id,
                "name": r.name,
                "class_name": r.class_name,
                "effective_minutes": effective_min,
                "require_minutes": course.require_minutes,
                "completed_sections": completed_sections,
                "total_sections": section_count,
                "completion_rate": round(completed_sections / section_count, 3) if section_count else 0,
                "video_progress": round(float(r.max_progress), 1) if r.max_progress else 0,
                "is_completed": completed_sections >= section_count if section_count else False,
            })

    # 概览统计（基于全量数据，不受分页影响）
    # 需要单独计算全量的完成人数
    all_completed = 0
    all_total_students = 0
    # 查询全量学生数（不分页不搜索）
    all_count_query = (
        select(func.count(User.id))
        .where(User.role == "student")
    )
    if class_name:
        all_count_query = all_count_query.where(User.class_name == class_name)
    all_total_students = await db.scalar(all_count_query) or 0

    # 全量完成人数：用一个聚合查询统计 completed_sections == section_count 的学生数
    # 由于完成判定依赖应用层逻辑，这里用一个简化的近似：
    # 查询每个学生的 max(video_progress) 按 section 分组，再统计完成数
    if section_count > 0 and all_total_students > 0:
        # 获取所有学生的 section 完成情况（一次性查全量）
        all_sec_result = await db.execute(
            select(subq.c.user_id, subq.c.section_id, subq.c.max_progress)
        )
        all_sec_rows = all_sec_result.all()

        # 按学生分组统计完成数
        student_section_complete = {}  # user_id → completed_count
        for sr in all_sec_rows:
            uid = sr.user_id
            if uid not in student_section_complete:
                student_section_complete[uid] = 0
            dur = section_duration_map.get(sr.section_id, 0)
            if dur and dur > 0:
                if float(sr.max_progress or 0) >= dur * 0.9:
                    student_section_complete[uid] += 1
            else:
                if float(sr.max_progress or 0) > 0:
                    student_section_complete[uid] += 1

        # 统计完成人数（所有小节都完成的）
        all_completed = sum(1 for cnt in student_section_complete.values() if cnt >= section_count)

        # 构建完成进度分布：0/N ~ N/N 各档人数
        completion_distribution = {}
        for i in range(section_count + 1):
            completion_distribution[str(i)] = 0
        for cnt in student_section_complete.values():
            key = str(min(cnt, section_count))
            completion_distribution[key] += 1
        # 未开始的学生（不在 student_section_complete 中）归入 0 档
        no_record_count = all_total_students - len(student_section_complete)
        completion_distribution["0"] += no_record_count

    return {
        "code": 0,
        "data": {
            "course_title": course.title,
            "require_minutes": course.require_minutes,
            "section_count": section_count,
            "total_students": all_total_students,
            "completed_students": all_completed,
            "completion_rate": round(all_completed / max(all_total_students, 1), 3),
            "completion_distribution": completion_distribution if section_count > 0 else {},
            "students": students,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
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
    target_date = datetime.strptime(date, "%Y-%m-%d") if date else now_cn_naive()
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
    未完成学生列表 — 获取未完成所有小节的学生（v5.1 改为小节数量维度判定）

    完成判定口径（与 class-overview、my-progress 统一）：
        每小节完成标准 video_progress >= duration_seconds × 90%，
        completed_sections < total_sections 即视为未完成。

    返回格式：
        code=0, data: { course_title, total_sections, incomplete: [{ user_id, name, class_name,
                                                                     completed_sections, total_sections }] }

    权限要求：【teacher / admin】

    注意：此接口只返回"有学习记录但未完成"的学生，完全未开始学习的学生不会出现在结果中。
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询课程所有小节
    sec_result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.sort_order, Section.id)
    )
    sections = sec_result.scalars().all()
    section_count = len(sections)
    section_duration_map = {s.id: s.duration_seconds or 0 for s in sections}

    if section_count == 0:
        return {"code": 0, "data": {"course_title": course.title, "total_sections": 0, "incomplete": []}}

    # 子查询：按 (user_id, section_id) 取每小节最大 video_progress
    subq_result = await db.execute(
        select(
            StudySession.user_id,
            StudySession.section_id,
            func.max(StudySession.video_progress).label("max_progress"),
        )
        .where(StudySession.course_id == course_id)
        .group_by(StudySession.user_id, StudySession.section_id)
    )
    sub_rows = subq_result.all()

    # 按学生分组，计算每人的完成小节数
    user_sections = {}  # user_id → [(section_id, max_progress), ...]
    for r in sub_rows:
        user_sections.setdefault(r.user_id, []).append((r.section_id, r.max_progress))

    if not user_sections:
        return {"code": 0, "data": {"course_title": course.title, "total_sections": section_count, "incomplete": []}}

    # 批量查用户信息
    user_ids = list(user_sections.keys())
    user_result = await db.execute(
        select(User.id, User.name, User.class_name)
        .where(and_(User.id.in_(user_ids), User.role == "student"))
    )
    user_map = {r.id: r for r in user_result.all()}

    # 筛选未完成的学生
    incomplete = []
    for uid, sec_list in user_sections.items():
        if uid not in user_map:
            continue
        u = user_map[uid]
        completed_sections = 0
        for section_id, max_progress in sec_list:
            dur = section_duration_map.get(section_id, 0)
            if dur and dur > 0:
                if float(max_progress or 0) >= dur * 0.9:
                    completed_sections += 1
            else:
                if float(max_progress or 0) > 0:
                    completed_sections += 1
        if completed_sections < section_count:
            incomplete.append({
                "user_id": uid,
                "name": u.name,
                "class_name": u.class_name,
                "completed_sections": completed_sections,
                "total_sections": section_count,
            })

    # 按完成数升序排（完成数越少越优先提醒）
    incomplete.sort(key=lambda x: x["completed_sections"])

    return {
        "code": 0,
        "data": {
            "course_title": course.title,
            "total_sections": section_count,
            "incomplete": incomplete,
        },
    }


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
    学习排行榜 — 按课程维度展示有效学习时长排名（v5.1 增加完成小节数维度）

    排名主键：总观看时长（每小节取 MAX(video_progress) 后求和）
    新增字段：completed_sections / total_sections（完成小节维度，口径与教师看板统一）

    权限要求：【已登录】
    """
    # 验证课程存在
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询课程所有小节（用于完成判定）
    sec_result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.sort_order, Section.id)
    )
    sections = sec_result.scalars().all()
    section_count = len(sections)
    section_duration_map = {s.id: s.duration_seconds or 0 for s in sections}

    # 子查询：按 (user_id, section_id) 取每小节最大 video_progress
    subq_result = await db.execute(
        select(
            StudySession.user_id,
            StudySession.section_id,
            func.max(StudySession.video_progress).label("max_progress"),
        )
        .where(StudySession.course_id == course_id)
        .group_by(StudySession.user_id, StudySession.section_id)
    )
    sub_rows = subq_result.all()

    # 按学生分组，同时计算总观看时长和完成小节数
    user_data = {}  # user_id → {total_watched: float, completed_sections: int}
    for r in sub_rows:
        uid = r.user_id
        if uid not in user_data:
            user_data[uid] = {"total_watched": 0.0, "completed_sections": 0}
        progress = float(r.max_progress or 0)
        user_data[uid]["total_watched"] += progress
        dur = section_duration_map.get(r.section_id, 0)
        if dur and dur > 0:
            if progress >= dur * 0.9:
                user_data[uid]["completed_sections"] += 1
        else:
            if progress > 0:
                user_data[uid]["completed_sections"] += 1

    if not user_data:
        return {
            "code": 0,
            "data": {"course_title": course.title, "total_sections": section_count, "ranking": []},
        }

    # 批量查用户信息（支持班级筛选）
    user_ids = list(user_data.keys())
    user_query = (
        select(User.id, User.name, User.real_name, User.class_name)
        .where(and_(User.id.in_(user_ids), User.role == "student"))
    )
    if class_name:
        user_query = user_query.where(User.class_name == class_name)
    user_result = await db.execute(user_query)
    user_info = {r.id: r for r in user_result.all()}

    # 构建排名列表
    ranking_entries = []
    for uid, data in user_data.items():
        if uid not in user_info:
            continue
        u = user_info[uid]
        watched_min = round(data["total_watched"] / 60, 1)
        ranking_entries.append({
            "user_id": uid,
            "name": u.name,
            "real_name": u.real_name or "",
            "class_name": u.class_name or "",
            "watched_minutes": watched_min,
            "completed_sections": data["completed_sections"],
            "total_sections": section_count,
        })

    # 按总观看时长降序排名
    ranking_entries.sort(key=lambda x: x["watched_minutes"], reverse=True)
    ranking_entries = ranking_entries[:limit]

    # 构建并列排名（如 1,2,2,4 而非 1,2,3,4）
    ranking = []
    prev_watched = None
    rank = 0
    for i, entry in enumerate(ranking_entries):
        if entry["watched_minutes"] != prev_watched:
            rank = i + 1
        prev_watched = entry["watched_minutes"]
        entry["rank"] = rank
        ranking.append(entry)

    return {
        "code": 0,
        "data": {
            "course_title": course.title,
            "total_sections": section_count,
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
    now = now_cn_naive()

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
                    func.max(StudySession.video_progress).label("c_max_progress"),
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
            require_seconds = (require_minutes or 0) * 60
            c_progress = float(c_data.c_max_progress) if c_data.c_max_progress else 0.0
            course_progress.append({
                "course_id": c.id,
                "title": c.title,
                "effective_minutes": c_effective,
                "require_minutes": require_minutes,
                # 完成率基于 video_progress，与前端进度条一致
                "completion_rate": round(min(c_progress / require_seconds, 1), 3) if require_seconds else None,
                # 完成判定：video_progress >= 要求时长的90%
                "is_completed": c_progress >= require_seconds * 0.90 if require_seconds else None,
            })

        # 最近7天每日学习时长分布（补全7天，无数据的天返回0）
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
        # 构建日期→时长的映射
        daily_map = {}
        for r in daily_result.all():
            daily_map[str(r.study_date)] = round(r.daily_effective / 60, 1) if r.daily_effective else 0
        # 补全近7天（含今天），使用北京时间日期
        cn_now = now_cn_naive()
        daily_distribution = []
        for i in range(6, -1, -1):
            d = cn_now - timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            daily_distribution.append({
                "date": date_str,
                "effective_minutes": daily_map.get(date_str, 0),
            })

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


# ============================================================
# v5.1 新增：班级列表、学生小节级进度
# ============================================================


@router.get("/class-list")
async def class_list(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取班级列表（供前端班级筛选下拉框使用）

    数据来源：class_defs 表 + users 表中 distinct class_name 取并集

    权限要求：【已登录】
    """
    # 从 class_defs 表获取已定义的班级
    cd_result = await db.execute(select(ClassDef.class_name).order_by(ClassDef.class_name))
    class_names_set = {r[0] for r in cd_result.all() if r[0]}

    # 从 users 表补充有学生但未在 class_defs 中的班级
    u_result = await db.execute(
        select(User.class_name)
        .where(and_(User.role == "student", User.class_name != ""))
        .distinct()
        .order_by(User.class_name)
    )
    for r in u_result.all():
        if r[0]:
            class_names_set.add(r[0])

    classes = sorted(class_names_set)
    return {"code": 0, "data": classes}


@router.get("/student-sections")
async def student_sections(
    course_id: int = Query(..., description="课程ID"),
    user_id: int = Query(..., description="学生用户ID"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    查看指定学生在指定课程下各小节的学习进度（教师懒加载用）

    返回格式：
        code=0, data: {
            sections: [
                { section_id, title, sort_order, video_progress, duration_seconds,
                  effective_minutes, is_completed, open_time }
            ],
            total_effective_minutes
        }

    权限要求：【teacher / admin】
    """
    # 查询该课程所有小节
    sec_result = await db.execute(
        select(Section)
        .where(Section.course_id == course_id)
        .order_by(Section.sort_order, Section.id)
    )
    sections = sec_result.scalars().all()

    # 查询该学生各小节的学习数据
    stats_result = await db.execute(
        select(
            StudySession.section_id,
            func.sum(StudySession.effective_seconds).label("sec_effective"),
            func.max(StudySession.video_progress).label("sec_progress"),
        )
        .where(
            and_(
                StudySession.user_id == user_id,
                StudySession.course_id == course_id,
            )
        )
        .group_by(StudySession.section_id)
    )
    sec_stats_map = {}
    total_effective = 0
    for r in stats_result.all():
        sec_stats_map[r.section_id] = {
            "effective": r.sec_effective or 0,
            "progress": float(r.sec_progress) if r.sec_progress else 0.0,
        }
        total_effective += r.sec_effective or 0

    sections_data = []
    for sec in sections:
        stats = sec_stats_map.get(sec.id, {"effective": 0, "progress": 0.0})
        sec_effective_min = round(stats["effective"] / 60, 1) if stats["effective"] else 0
        sec_progress = round(stats["progress"], 1)
        dur = sec.duration_seconds or 0
        # 完成判定：video_progress >= duration * 90%
        if dur and dur > 0:
            is_completed = stats["progress"] >= dur * 0.9
        else:
            is_completed = stats["progress"] > 0
        sections_data.append({
            "section_id": sec.id,
            "title": sec.title,
            "sort_order": sec.sort_order,
            "video_progress": sec_progress,
            "duration_seconds": dur,
            "effective_minutes": sec_effective_min,
            "is_completed": is_completed,
            "open_time": sec.open_time.isoformat() if sec.open_time else None,
        })

    return {
        "code": 0,
        "data": {
            "sections": sections_data,
            "total_effective_minutes": round(total_effective / 60, 1) if total_effective else 0,
        },
    }
