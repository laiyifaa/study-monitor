"""
课程管理模块 (course)

功能说明：
    提供课程的 CRUD 操作。视频内容通过 Section（小节）模块管理，
    一门课包含多个小节，每个小节有独立的视频源。

在系统中的角色：
    内容管理层——管理课程元数据（标题、描述、要求时长等），
    小节级别的管理由 section router 负责。

API 列表：
    POST   /api/courses                    — 创建课程
    GET    /api/courses                    — 课程列表（支持状态过滤）
    GET    /api/courses/{course_id}        — 课程详情（含小节列表）
    PUT    /api/courses/{course_id}        — 更新课程
    DELETE /api/courses/{course_id}        — 删除课程（级联删除小节）

权限矩阵：
    创建课程：teacher / admin
    编辑课程：teacher / admin
    删除课程：admin（仅管理员可删除，防止误删影响学生数据）
    查看课程：所有人（无需登录）
"""

import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Course, Section, User
from app.utils.jwt_helper import get_current_user, require_role
from app.config import get_settings

router = APIRouter(prefix="/api/courses", tags=["课程管理"])

# 视频文件存储目录（删除课程时需要清理小节视频）
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")


class CourseCreate(BaseModel):
    """创建课程请求体"""
    title: str                        # 课程标题（必填）
    description: str = ""             # 课程描述
    require_minutes: int | None = None  # 要求学习时长（分钟），null或未传=不设要求
    start_date: datetime | None = None  # 学习开始日期
    end_date: datetime | None = None    # 学习截止日期


class CourseUpdate(BaseModel):
    """
    更新课程请求体（所有字段可选，只更新传入的字段）
    """
    title: str | None = None
    description: str | None = None
    require_minutes: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None


def _course_to_dict(c: Course, section_count: int = 0, sections: list | None = None):
    """
    统一的课程序列化函数

    v3.0 改造：
        视频数据已迁移到 Section 表，课程序列化不再输出视频字段。
        新增 section_count 和 sections 字段，前端用于展示课程结构。
    """
    result = {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "require_minutes": c.require_minutes,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "status": c.status,
        "teacher_id": c.teacher_id,
        "section_count": section_count,
    }
    # 仅在请求详情时嵌入小节数据（节省列表查询的开销）
    if sections is not None:
        result["sections"] = sections
    return result


@router.post("")
async def create_course(
    req: CourseCreate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建课程

    请求参数：
        body.title (str):              课程标题（必填）
        body.description (str):        课程描述
        body.require_minutes (int):     要求学习时长（分钟），null=不设要求
        body.start_date (datetime):     学习开始日期
        body.end_date (datetime):       学习截止日期

    返回格式：code=0, data.id/title

    权限要求：【teacher / admin】
    """
    course = Course(
        title=req.title,
        description=req.description,
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
    status: str = Query("active", description="课程状态过滤：active/inactive/all"),
    db: AsyncSession = Depends(get_db),
):
    """
    课程列表

    请求参数：
        query.status (str): 状态过滤，"active"（默认）、"inactive"、"all"

    返回格式：code=0, data: 课程对象数组（含 section_count）

    权限要求：无需登录
    """
    query = select(Course).order_by(Course.created_at.desc())
    if status != "all":
        query = query.where(Course.status == status)
    result = await db.execute(query)
    courses = result.scalars().all()

    # 批量查询每个课程的小节数
    course_ids = [c.id for c in courses]
    section_counts = {}
    if course_ids:
        count_result = await db.execute(
            select(Section.course_id, func.count(Section.id))
            .where(Section.course_id.in_(course_ids))
            .group_by(Section.course_id)
        )
        section_counts = dict(count_result.all())

    return {"code": 0, "data": [_course_to_dict(c, section_count=section_counts.get(c.id, 0)) for c in courses]}


@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    """
    课程详情（含小节列表）

    权限要求：无需登录
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 查询该课程下所有小节（按排序序号）
    from app.routers.section import _section_to_dict
    sec_result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.sort_order, Section.id)
    )
    sections = [_section_to_dict(s) for s in sec_result.scalars().all()]

    return {"code": 0, "data": _course_to_dict(course, section_count=len(sections), sections=sections)}


@router.put("/{course_id}")
async def update_course(
    course_id: int,
    req: CourseUpdate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新课程（部分更新，只修改传入的字段）

    权限要求：【teacher / admin】
    """
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
    """
    删除课程（级联删除所有关联数据）

    级联删除顺序（从叶子到根）：
    grading_reports → grading_tasks → submissions → assignments → section_feedbacks
    → heartbeat_logs → study_sessions → announcements(含已读) → sections(含视频) → course

    权限要求：【仅 admin】
    """
    from app.models.models import (
        Assignment, Submission, GradingReport, GradingTask,
        SectionFeedback, StudySession, HeartbeatLog,
        Announcement, AnnouncementRead,
    )

    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 1. 查找该课程下所有小节
    sec_result = await db.execute(select(Section).where(Section.course_id == course_id))
    sections = sec_result.scalars().all()
    section_ids = [s.id for s in sections]

    # 2. 作业 → 提交 → 批改报告/批改任务
    # 旧数据里可能仍有只通过 course_id 关联的课程级作业。
    assignment_filter = Assignment.course_id == course_id
    if section_ids:
        assignment_filter = or_(Assignment.section_id.in_(section_ids), assignment_filter)

    asgn_result = await db.execute(select(Assignment).where(assignment_filter))
    assignments = asgn_result.scalars().all()
    assignment_ids = [a.id for a in assignments]

    if assignment_ids:
        sub_result = await db.execute(
            select(Submission).where(Submission.assignment_id.in_(assignment_ids))
        )
        submissions = sub_result.scalars().all()
        submission_ids = [s.id for s in submissions]

        if submission_ids:
            # 批改报告
            await db.execute(
                GradingReport.__table__.delete().where(
                    GradingReport.submission_id.in_(submission_ids)
                )
            )
            # 批改任务
            await db.execute(
                GradingTask.__table__.delete().where(
                    GradingTask.submission_id.in_(submission_ids)
                )
            )
        # 提交
        await db.execute(
            Submission.__table__.delete().where(
                Submission.assignment_id.in_(assignment_ids)
            )
        )
        # 作业（同时匹配 section_id 和 course_id 冗余字段）
        await db.execute(
            Assignment.__table__.delete().where(assignment_filter)
        )

    if section_ids:
        # 小节反馈
        await db.execute(
            SectionFeedback.__table__.delete().where(
                SectionFeedback.section_id.in_(section_ids)
            )
        )

    # 3. 学习会话和心跳日志
    sess_result = await db.execute(
        select(StudySession).where(StudySession.course_id == course_id)
    )
    sessions = sess_result.scalars().all()
    session_uuids = [s.session_id for s in sessions]

    if session_uuids:
        await db.execute(
            HeartbeatLog.__table__.delete().where(
                HeartbeatLog.session_id.in_(session_uuids)
            )
        )
    await db.execute(
        StudySession.__table__.delete().where(StudySession.course_id == course_id)
    )

    # 4. 公告及已读记录
    ann_result = await db.execute(
        select(Announcement).where(Announcement.course_id == course_id)
    )
    announcements = ann_result.scalars().all()
    announcement_ids = [a.id for a in announcements]

    if announcement_ids:
        await db.execute(
            AnnouncementRead.__table__.delete().where(
                AnnouncementRead.announcement_id.in_(announcement_ids)
            )
        )
        await db.execute(
            Announcement.__table__.delete().where(
                Announcement.id.in_(announcement_ids)
            )
        )

    # 5. 删除小节及本地视频文件
    for sec in sections:
        if sec.video_type == "local" and sec.video_url:
            local_path = os.path.join(UPLOAD_DIR, sec.video_url)
            if os.path.exists(local_path):
                os.remove(local_path)
    if section_ids:
        await db.execute(
            Section.__table__.delete().where(Section.course_id == course_id)
        )

    # 6. 删除旧的视频文件（兼容 v2.x 数据）
    if course.video_type == "local" and course.video_url:
        local_path = os.path.join(UPLOAD_DIR, course.video_url)
        if os.path.exists(local_path):
            os.remove(local_path)

    # 7. 删除课程
    await db.delete(course)
    await db.commit()
    return {"code": 0, "data": {"id": course_id}}
