"""
作业管理模块 (homework)

功能说明：
    负责作业发布、提交、批改报告的完整流程管理。
    支持教师发布作业、学生上传作业图片、智能体回调批改结果。

    一个课程对应一个作业（1:1 关系）。

在系统中的角色：
    作业管理网关 — 协调 assignments、submissions、grading_reports 三张表。
    智能体回调入口 — 接收智能体的批改结果并写入数据库。

API 列表：
    教师端：
        POST   /api/homework/assignments/{course_id}  — 创建课程作业
        PUT    /api/homework/assignments/{course_id}  — 编辑课程作业
        GET    /api/homework/assignments/{course_id}  — 获取课程作业
        GET    /api/homework/assignments/{course_id}/submissions — 查看提交列表
        GET    /api/homework/reports/{submission_id}  — 查看批改报告

    学生端：
        GET    /api/homework/assignments/{course_id}  — 获取课程作业
        POST   /api/homework/submissions              — 提交作业（上传图片）
        GET    /api/homework/my-submissions           — 查看我的提交列表

    智能体回调：
        POST   /api/homework/grading-callback         — 智能体批改完成回调（需 API Key）

    文件上传：
        POST   /api/homework/upload                   — 上传作业图片
"""

import os
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.config import get_settings
from app.database import get_db
from app.models.models import Assignment, Submission, GradingReport, Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/homework", tags=["作业管理"])
settings = get_settings()

HOMEWORK_UPLOAD_DIR = "uploads/homework"


class CreateAssignmentRequest(BaseModel):
    title: str
    description: str = ""
    grading_prompt: str = ""
    deadline: Optional[str] = None


class UpdateAssignmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    grading_prompt: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None


class CreateSubmissionRequest(BaseModel):
    assignment_id: int
    images: List[str]


class GradingCallbackRequest(BaseModel):
    submission_id: int
    score: int
    feedback: str = ""
    detail: str = "{}"
    generated_by: str = "unknown"


@router.post("/upload")
async def upload_homework_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/gif/webp 格式")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(HOMEWORK_UPLOAD_DIR, filename)

    os.makedirs(HOMEWORK_UPLOAD_DIR, exist_ok=True)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/homework/{filename}"}}


@router.get("/assignments/{course_id}")
async def get_assignment(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    assignment = result.scalar_one_or_none()

    if not assignment:
        return {"code": 0, "data": None}

    return {
        "code": 0,
        "data": {
            "id": assignment.id,
            "course_id": assignment.course_id,
            "title": assignment.title,
            "description": assignment.description,
            "grading_prompt": assignment.grading_prompt,
            "deadline": assignment.deadline.isoformat() if assignment.deadline else None,
            "status": assignment.status,
            "created_at": assignment.created_at.isoformat(),
        },
    }


@router.post("/assignments/{course_id}")
async def create_assignment(
    course_id: int,
    req: CreateAssignmentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    existing = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该课程已有作业")

    deadline_dt = None
    if req.deadline:
        try:
            deadline_dt = datetime.fromisoformat(req.deadline.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="截止时间格式错误")

    assignment = Assignment(
        course_id=course_id,
        title=req.title,
        description=req.description,
        grading_prompt=req.grading_prompt,
        deadline=deadline_dt,
        status="draft",
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return {
        "code": 0,
        "data": {
            "id": assignment.id,
            "course_id": assignment.course_id,
            "title": assignment.title,
            "description": assignment.description,
            "grading_prompt": assignment.grading_prompt,
            "deadline": assignment.deadline.isoformat() if assignment.deadline else None,
            "status": assignment.status,
            "created_at": assignment.created_at.isoformat(),
        },
    }


@router.put("/assignments/{course_id}")
async def update_assignment(
    course_id: int,
    req: UpdateAssignmentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if req.title is not None:
        assignment.title = req.title
    if req.description is not None:
        assignment.description = req.description
    if req.grading_prompt is not None:
        assignment.grading_prompt = req.grading_prompt
    if req.deadline is not None:
        try:
            assignment.deadline = datetime.fromisoformat(req.deadline.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="截止时间格式错误")
    if req.status is not None:
        if req.status not in ["draft", "published", "closed"]:
            raise HTTPException(status_code=400, detail="状态值无效")
        assignment.status = req.status

    await db.commit()
    return {"code": 0, "data": {"id": assignment.id}}


@router.get("/assignments/{course_id}/submissions")
async def list_submissions(
    course_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    assignment_result = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    assignment = assignment_result.scalar_one_or_none()
    if not assignment:
        return {"code": 0, "data": []}

    result = await db.execute(
        select(Submission).where(Submission.assignment_id == assignment.id).order_by(Submission.submitted_at.desc())
    )
    submissions = result.scalars().all()

    data = []
    for s in submissions:
        user_result = await db.execute(select(User).where(User.id == s.user_id))
        user = user_result.scalar_one_or_none()

        report_result = await db.execute(
            select(GradingReport).where(GradingReport.submission_id == s.id)
        )
        report = report_result.scalar_one_or_none()

        data.append({
            "id": s.id,
            "user": {"id": user.id, "name": user.name} if user else None,
            "images": json.loads(s.images),
            "status": s.status,
            "submitted_at": s.submitted_at.isoformat(),
            "report": {
                "score": report.score,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat(),
            } if report else None,
        })

    return {"code": 0, "data": data}


@router.get("/reports/{submission_id}")
async def get_grading_report(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if current_user.role == "student" and submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此报告")

    report_result = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == submission_id)
    )
    report = report_result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="批改报告尚未生成")

    return {
        "code": 0,
        "data": {
            "submission_id": submission_id,
            "score": report.score,
            "feedback": report.feedback,
            "detail": json.loads(report.detail),
            "generated_by": report.generated_by,
            "created_at": report.created_at.isoformat(),
        },
    }


@router.post("/submissions")
async def create_submission(
    req: CreateSubmissionRequest,
    current_user: User = Depends(require_role("student")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.id == req.assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if assignment.status != "published":
        raise HTTPException(status_code=400, detail="作业未发布或已关闭")

    existing = await db.execute(
        select(Submission).where(
            and_(Submission.assignment_id == req.assignment_id, Submission.user_id == current_user.id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="已提交过作业，不可重复提交")

    submission = Submission(
        assignment_id=req.assignment_id,
        user_id=current_user.id,
        images=json.dumps(req.images),
        status="pending",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {
        "code": 0,
        "data": {
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "images": req.images,
            "status": submission.status,
            "submitted_at": submission.submitted_at.isoformat(),
        },
    }


@router.get("/my-submissions")
async def list_my_submissions(
    assignment_id: Optional[int] = None,
    current_user: User = Depends(require_role("student")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Submission).where(Submission.user_id == current_user.id)
    if assignment_id:
        query = query.where(Submission.assignment_id == assignment_id)
    query = query.order_by(Submission.submitted_at.desc())

    result = await db.execute(query)
    submissions = result.scalars().all()

    data = []
    for s in submissions:
        assignment_result = await db.execute(select(Assignment).where(Assignment.id == s.assignment_id))
        assignment = assignment_result.scalar_one_or_none()

        report_result = await db.execute(
            select(GradingReport).where(GradingReport.submission_id == s.id)
        )
        report = report_result.scalar_one_or_none()

        data.append({
            "id": s.id,
            "assignment": {
                "id": assignment.id,
                "title": assignment.title,
                "course_id": assignment.course_id,
            } if assignment else None,
            "images": json.loads(s.images),
            "status": s.status,
            "submitted_at": s.submitted_at.isoformat(),
            "report": {
                "score": report.score,
                "feedback": report.feedback,
            } if report else None,
        })

    return {"code": 0, "data": data}


@router.post("/grading-callback")
async def grading_callback(
    req: GradingCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == req.submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    existing_report = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == req.submission_id)
    )
    if existing_report.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该提交已有批改报告")

    if req.score < 0 or req.score > 100:
        raise HTTPException(status_code=400, detail="分数必须在 0-100 之间")

    report = GradingReport(
        submission_id=req.submission_id,
        score=req.score,
        feedback=req.feedback,
        detail=req.detail,
        generated_by=req.generated_by,
    )
    db.add(report)

    submission.status = "graded"

    await db.commit()
    await db.refresh(report)

    return {"code": 0, "data": {"report_id": report.id}}
