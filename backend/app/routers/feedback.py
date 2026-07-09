"""
小节评价/反馈模块 (feedback) 

功能说明：
    提供学生对课程小节的评分和文字反馈功能。
    每位学生对每个小节只能评价一次，教师/管理员可查看统计和详情。
    学生仅能提交评价和查看自己的评价，不展示他人评价数据。

在系统中的角色：
    互动反馈层——收集学生对课程内容的满意度数据，辅助教师优化教学质量。

API 列表：
    POST   /api/feedback                    — 提交评价（student，每人对每小节只能评价一次）
    GET    /api/feedback?section_id=x        — 获取某小节的所有评价（teacher/admin）
    GET    /api/feedback/my?section_id=x     — 获取我的评价（登录用户）
    GET    /api/feedback/stats?section_id=x  — 获取小节评价统计（teacher/admin）

权限矩阵：
    提交评价：student
    查看评价列表：teacher / admin
    查看我的评价：登录用户
    查看统计：teacher / admin
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import SectionFeedback, Section, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/feedback", tags=["小节评价"])


class FeedbackCreate(BaseModel):
    """提交评价请求体"""
    section_id: int                          # 小节ID（必填）
    rating: int = Field(default=5, ge=1, le=5)  # 评分1-5星
    comment: str = Field(default="", max_length=500)  # 文字评价


def _feedback_to_dict(fb: SectionFeedback, user_name: str = ""):
    """统一的评价序列化函数"""
    return {
        "id": fb.id,
        "section_id": fb.section_id,
        "user_id": fb.user_id,
        "user_name": user_name,
        "rating": fb.rating,
        "comment": fb.comment,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }


@router.post("")
async def create_feedback(
    req: FeedbackCreate,
    user: User = Depends(require_role("student")),
    db: AsyncSession = Depends(get_db),
):
    """
    提交小节评价

    请求参数：
        body.section_id (int): 小节ID（必填）
        body.rating (int):     评分1-5星
        body.comment (str):    文字评价

    权限要求：【student】
    业务规则：同一学生对同一小节只能评价一次
    """
    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="评分范围为1-5星")

    result = await db.execute(select(Section).where(Section.id == req.section_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="小节不存在")

    result = await db.execute(
        select(SectionFeedback).where(
            and_(
                SectionFeedback.section_id == req.section_id,
                SectionFeedback.user_id == user.id,
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="您已评价过该小节，不能重复评价")

    feedback = SectionFeedback(
        section_id=req.section_id,
        user_id=user.id,
        rating=req.rating,
        comment=req.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return {"code": 0, "data": _feedback_to_dict(feedback, user.name)}


@router.get("")
async def list_feedback(
    section_id: int = Query(..., description="小节ID（必填）"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取某小节的所有评价（按时间倒序）

    请求参数：
        query.section_id (int): 小节ID（必填）

    权限要求：【teacher / admin】
    """
    result = await db.execute(
        select(SectionFeedback, User.name)
        .join(User, SectionFeedback.user_id == User.id, isouter=True)
        .where(SectionFeedback.section_id == section_id)
        .order_by(SectionFeedback.created_at.desc())
    )
    rows = result.all()
    data = [_feedback_to_dict(fb, user_name) for fb, user_name in rows]
    return {"code": 0, "data": data}


@router.get("/my")
async def my_feedback(
    section_id: int = Query(..., description="小节ID（必填）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取我的评价

    请求参数：
        query.section_id (int): 小节ID（必填）

    权限要求：【登录用户】
    """
    result = await db.execute(
        select(SectionFeedback).where(
            and_(
                SectionFeedback.section_id == section_id,
                SectionFeedback.user_id == user.id,
            )
        )
    )
    fb = result.scalar_one_or_none()
    if not fb:
        return {"code": 0, "data": None}
    return {"code": 0, "data": _feedback_to_dict(fb, user.name)}


@router.get("/stats")
async def feedback_stats(
    section_id: int = Query(..., description="小节ID（必填）"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取小节评价统计（平均分、评价数、各星数分布）

    请求参数：
        query.section_id (int): 小节ID（必填）

    权限要求：【teacher / admin】
    """
    result = await db.execute(
        select(
            func.avg(SectionFeedback.rating),
            func.count(SectionFeedback.id),
        ).where(SectionFeedback.section_id == section_id)
    )
    row = result.one()
    avg_rating = round(float(row[0]), 1) if row[0] else 0.0
    total_count = row[1]

    distribution = {}
    for star in range(1, 6):
        r = await db.execute(
            select(func.count(SectionFeedback.id)).where(
                and_(
                    SectionFeedback.section_id == section_id,
                    SectionFeedback.rating == star,
                )
            )
        )
        distribution[str(star)] = r.scalar() or 0

    return {
        "code": 0,
        "data": {
            "avg_rating": avg_rating,
            "total_count": total_count,
            "rating_distribution": distribution,
        },
    }


@router.get("/course-stats")
async def course_feedback_stats(
    course_id: int = Query(..., description="课程ID（必填）"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取某课程下所有小节的评价统计汇总

    请求参数：
        query.course_id (int): 课程ID（必填）

    权限要求：【teacher / admin】

    返回：课程下每个小节的评价统计数据，附带小节标题
    """
    # 查询课程下所有小节
    sections_result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.id)
    )
    sections = sections_result.scalars().all()

    data = []
    for section in sections:
        # 统计该小节评价
        stat_result = await db.execute(
            select(
                func.avg(SectionFeedback.rating),
                func.count(SectionFeedback.id),
            ).where(SectionFeedback.section_id == section.id)
        )
        row = stat_result.one()
        avg_rating = round(float(row[0]), 1) if row[0] else 0.0
        total_count = row[1]

        # 各星分布
        distribution = {}
        for star in range(1, 6):
            r = await db.execute(
                select(func.count(SectionFeedback.id)).where(
                    and_(
                        SectionFeedback.section_id == section.id,
                        SectionFeedback.rating == star,
                    )
                )
            )
            distribution[str(star)] = r.scalar() or 0

        data.append({
            "section_id": section.id,
            "section_title": section.title,
            "avg_rating": avg_rating,
            "total_count": total_count,
            "rating_distribution": distribution,
        })

    return {"code": 0, "data": data}
