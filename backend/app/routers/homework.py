"""
作业管理模块 (homework)

功能说明：
    负责作业发布、提交、批改报告的完整流程管理。
    支持教师发布作业、学生上传作业图片、智能体回调批改结果。

    v4.0: 一个小节对应一个作业（1:1 关系），从课程级迁移到小节级。
    迟交机制：截止时间后仍可提交，但自动标记 is_late=True。

在系统中的角色：
    作业管理网关 — 协调 assignments、submissions、grading_reports 三张表。
    智能体回调入口 — 接收智能体的批改结果并写入数据库。

API 列表：
    教师端：
        POST   /api/homework/assignments/{section_id}  — 创建小节作业
        PUT    /api/homework/assignments/{section_id}  — 编辑小节作业
        GET    /api/homework/assignments/{section_id}  — 获取小节作业
        GET    /api/homework/course/{course_id}         — 获取课程下所有小节作业
        GET    /api/homework/assignments/{section_id}/submissions — 查看提交列表
        GET    /api/homework/reports/{submission_id}   — 查看批改报告

    学生端：
        GET    /api/homework/assignments/{section_id}  — 获取小节作业
        POST   /api/homework/submissions               — 提交作业（上传图片）
        GET    /api/homework/my-submissions            — 查看我的提交列表

    智能体回调：
        POST   /api/homework/grading-callback          — 智能体批改完成回调（需 API Key）

    文件上传：
        POST   /api/homework/upload                    — 上传作业图片
"""

import os
import re
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.config import get_settings
from app.database import get_db
from app.models.models import Assignment, Submission, GradingReport, GradingTask, Course, Section, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/homework", tags=["作业管理"])
settings = get_settings()

HOMEWORK_UPLOAD_DIR = "uploads/homework"


async def _refresh_grading_status(assignment_id: int, db: AsyncSession):
    pending_count = await db.scalar(
        select(func.count()).select_from(Submission).where(
            and_(Submission.assignment_id == assignment_id, Submission.status == "pending")
        )
    )
    if pending_count == 0:
        assignment = (await db.execute(select(Assignment).where(Assignment.id == assignment_id))).scalar_one_or_none()
        if assignment and assignment.grading_status != "graded":
            assignment.grading_status = "graded"


class CreateAssignmentRequest(BaseModel):
    title: str
    description: str = ""
    question_files: List[str] = []
    grading_prompt: str = ""
    reference_answer: str = ""  # v5.0: 参考答案
    deadline: Optional[str] = None
    grading_mode: str = "auto"


class UpdateAssignmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    question_files: Optional[List[str]] = None
    grading_prompt: Optional[str] = None
    reference_answer: Optional[str] = None  # v5.0: 参考答案
    deadline: Optional[str] = None
    status: Optional[str] = None
    grading_mode: Optional[str] = None


class CreateSubmissionRequest(BaseModel):
    assignment_id: int
    images: List[str]


class GradingCallbackData(BaseModel):
    submission_id: int
    score: int
    feedback: str = ""
    detail: str = "{}"
    generated_by: str = "unknown"

    @field_validator("detail", mode="before")
    @classmethod
    def normalize_detail(cls, v):
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return v


class GradingCallbackRequest(BaseModel):
    data: GradingCallbackData


class ManualGradeRequest(BaseModel):
    score: int
    feedback: str = ""


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


@router.post("/upload-question")
async def upload_question_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"]:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/gif/webp/pdf 格式")

    question_dir = os.path.join(HOMEWORK_UPLOAD_DIR, "questions")
    os.makedirs(question_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(question_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/homework/questions/{filename}"}}


def _assignment_to_dict(a: Assignment):
    """统一作业序列化函数（v4.0 section 级）"""
    return {
        "id": a.id,
        "section_id": a.section_id,
        "course_id": a.course_id,
        "title": a.title,
        "description": a.description,
        "question_files": json.loads(a.question_files),
        "grading_prompt": a.grading_prompt,
        "reference_answer": a.reference_answer or "",
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "status": a.status,
        "grading_mode": a.grading_mode,
        "grading_status": a.grading_status,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/course/{course_id}")
async def list_course_assignments(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程下所有小节的作业列表 — v4.0 新增

    请求参数：
        path.course_id (int): 课程ID

    返回格式：
        code=0, data: [assignment_dict, ...]
    """
    result = await db.execute(
        select(Assignment).where(Assignment.course_id == course_id)
    )
    assignments = result.scalars().all()
    return {"code": 0, "data": [_assignment_to_dict(a) for a in assignments]}


@router.get("/assignments/{section_id}")
async def get_assignment(
    section_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取小节作业 — 按 section_id 查询

    v4.0: 从 course_id 切换到 section_id
    """
    result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = result.scalar_one_or_none()

    if not assignment:
        return {"code": 0, "data": None}

    return {
        "code": 0,
        "data": _assignment_to_dict(assignment),
    }


@router.post("/assignments/{section_id}")
async def create_assignment(
    section_id: int,
    req: CreateAssignmentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建小节作业 — v4.0: 绑定到 section

    请求参数：
        path.section_id: 目标小节ID
    """
    # 校验小节存在并获取 course_id
    section_result = await db.execute(select(Section).where(Section.id == section_id))
    section = section_result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="小节不存在")

    # 检查该小节是否已有作业
    existing = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该小节已有作业")

    deadline_dt = None
    if req.deadline:
        try:
            deadline_dt = datetime.fromisoformat(req.deadline.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="截止时间格式错误")

    if req.grading_mode not in ["auto", "manual", "hybrid"]:
        raise HTTPException(status_code=400, detail="批改模式无效")

    assignment = Assignment(
        section_id=section_id,
        course_id=section.course_id,  # 冗余字段，从 section 自动填入
        title=req.title,
        description=req.description,
        question_files=json.dumps(req.question_files),
        grading_prompt=req.grading_prompt,
        reference_answer=req.reference_answer,
        deadline=deadline_dt,
        status="draft",
        grading_mode=req.grading_mode,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return {"code": 0, "data": _assignment_to_dict(assignment)}


@router.put("/assignments/{section_id}")
async def update_assignment(
    section_id: int,
    req: UpdateAssignmentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    编辑小节作业 — v4.0: 按 section_id 查找
    """
    result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if req.title is not None:
        assignment.title = req.title
    if req.description is not None:
        assignment.description = req.description
    if req.question_files is not None:
        assignment.question_files = json.dumps(req.question_files)
    if req.grading_prompt is not None:
        assignment.grading_prompt = req.grading_prompt
    if req.reference_answer is not None:
        assignment.reference_answer = req.reference_answer
    if req.deadline is not None:
        try:
            assignment.deadline = datetime.fromisoformat(req.deadline.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="截止时间格式错误")
    if req.status is not None:
        if req.status not in ["draft", "published", "closed"]:
            raise HTTPException(status_code=400, detail="状态值无效")
        assignment.status = req.status
    if req.grading_mode is not None:
        if req.grading_mode not in ["auto", "manual", "hybrid"]:
            raise HTTPException(status_code=400, detail="批改模式无效")
        assignment.grading_mode = req.grading_mode

    await db.commit()
    return {"code": 0, "data": {"id": assignment.id}}


@router.get("/assignments/{section_id}/submissions")
async def list_submissions(
    section_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    查看小节作业的提交列表 — v4.0: 按 section_id 查找
    """
    assignment_result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
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

        task_result = await db.execute(
            select(GradingTask).where(GradingTask.submission_id == s.id)
        )
        task = task_result.scalar_one_or_none()

        data.append({
            "id": s.id,
            "user": {"id": user.id, "name": user.name} if user else None,
            "images": json.loads(s.images),
            "status": s.status,
            "is_late": s.is_late,  # v4.0: 迟交标记
            "submitted_at": s.submitted_at.isoformat(),
            "report": {
                "score": report.score,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat(),
            } if report else None,
            "task": {
                "status": task.status,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "sent_at": task.sent_at.isoformat() if task.sent_at else None,
                "graded_at": task.graded_at.isoformat() if task.graded_at else None,
            } if task else None,
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

    # v4.0: 截止时间后仍可提交，但标记 is_late=True
    is_late = False
    if assignment.deadline and datetime.utcnow() > assignment.deadline:
        is_late = True  # 迟交但仍允许提交

    existing_result = await db.execute(
        select(Submission)
        .where(
            and_(
                Submission.assignment_id == req.assignment_id,
                Submission.user_id == current_user.id,
                Submission.is_latest == True,
            )
        )
        .order_by(Submission.version.desc())
    )
    existing = existing_result.scalar_one_or_none()

    next_version = 1
    if existing:
        existing.is_latest = False
        next_version = existing.version + 1

    submission = Submission(
        assignment_id=req.assignment_id,
        user_id=current_user.id,
        images=json.dumps(req.images),
        status="pending",
        is_late=is_late,  # v4.0: 迟交标记
        version=next_version,
        is_latest=True,
    )
    db.add(submission)

    assignment.grading_status = "pending"

    await db.commit()
    await db.refresh(submission)

    return {
        "code": 0,
        "data": {
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "images": req.images,
            "status": submission.status,
            "is_late": submission.is_late,  # v4.0
            "version": submission.version,
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
                "section_id": assignment.section_id,  # v4.0
                "course_id": assignment.course_id,
            } if assignment else None,
            "images": json.loads(s.images),
            "status": s.status,
            "is_late": s.is_late,  # v4.0
            "submitted_at": s.submitted_at.isoformat(),
            "report": {
                "score": report.score,
                "feedback": report.feedback,
            } if report else None,
        })

    return {"code": 0, "data": data}


@router.post("/manual-grade/{submission_id}")
async def manual_grade(
    submission_id: int,
    req: ManualGradeRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    existing_report = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == submission_id)
    )
    if existing_report.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该提交已有批改报告，不可重复批改")

    if req.score < 0 or req.score > 100:
        raise HTTPException(status_code=400, detail="分数必须在 0-100 之间")

    report = GradingReport(
        submission_id=submission_id,
        score=req.score,
        feedback=req.feedback,
        detail="{}",
        generated_by="teacher",
        review_status="confirmed",
    )
    db.add(report)

    submission.status = "graded"

    await _refresh_grading_status(submission.assignment_id, db)

    await db.commit()
    await db.refresh(report)

    return {"code": 0, "data": {"report_id": report.id}}


# ── 不安全 JSON 的兼容解析 ──
# 智能体平台发送的回调 body 可能包含未转义控制字符、不可见空白、单引号等
_INVISIBLE_WS = re.compile(
    r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f'
    r'\u00a0\u200b\u200c\u200d\u200e\u200f\ufeff\u3000]'
)
_TRAILING_COMMA = re.compile(r',\s*([}\]])')


def _try_json(text: str) -> dict | None:
    """用 strict=False 尝试解析（允许未转义的控制字符）"""
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return None


def _sanitize_text(text: str) -> str:
    """移除不可见控制字符和特殊空白，保留合法换行和制表符"""
    return _INVISIBLE_WS.sub('', text)


def _fix_single_quotes(text: str) -> str:
    """将单引号替换为双引号（仅在 JSON 结构区域操作）"""
    return text.replace("'", '"')


def _fix_trailing_commas(text: str) -> str:
    """去除数组/对象末尾多余逗号"""
    return _TRAILING_COMMA.sub(r'\1', text)


def _unwrap_double_encoded_data(obj: dict) -> dict:
    """如果 data 字段是 JSON 字符串，二次解码"""
    d = obj.get("data")
    if isinstance(d, str):
        try:
            obj["data"] = json.loads(d, strict=False)
        except (json.JSONDecodeError, TypeError):
            pass
    return obj


def parse_callback_body(raw: bytes) -> dict:
    """
    解析智能体回调请求体，最大程度兼容各种不规范的 JSON。

    处理顺序：
      1. UTF-8 解码 + 移除 BOM
      2. 移除不可见控制字符和特殊空白
      3. 依次尝试多种修复策略
    """
    text = raw.decode("utf-8-sig").strip()
    if not text:
        raise HTTPException(status_code=400, detail="回调请求体为空")

    # 先清理特殊字符
    text = _sanitize_text(text)

    steps = [
        ("原始 body", lambda t: t),
        ("单引号→双引号", _fix_single_quotes),
        ("去尾部逗号", _fix_trailing_commas),
        ("单引号→双引号 + 去尾部逗号",
         lambda t: _fix_trailing_commas(_fix_single_quotes(t))),
    ]

    for label, fix in steps:
        result = _try_json(fix(text))
        if result:
            result = _unwrap_double_encoded_data(result)
            return result

    # 全部策略都失败，尝试按行分段提取关键字段（最坏情况）
    try:
        fields = {}
        for key in ("submission_id", "score", "feedback", "detail", "generated_by"):
            m = re.search(rf'["\']?{key}["\']?\s*[:=]\s*["\']?([^"\'}}\]]+)["\']?', text)
            if m:
                fields[key] = m.group(1).strip()
        if fields.get("submission_id") and fields.get("score"):
            return {
                "data": {
                    "submission_id": int(fields["submission_id"]),
                    "score": int(fields["score"]),
                    "feedback": fields.get("feedback", ""),
                    "detail": fields.get("detail", "{}"),
                    "generated_by": fields.get("generated_by", "unknown"),
                }
            }
    except (ValueError, TypeError):
        pass

    raise HTTPException(
        status_code=400,
        detail=f"回调 JSON 解析失败，已尝试所有兼容策略。前200字符: {text[:200]}"
    )


@router.post("/grading-callback")
async def grading_callback(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw = await request.body()
    print("=" * 60)
    print("[GRADING CALLBACK] 收到回调请求")
    print("-" * 60)
    print(f"[HEADERS]:")
    for k, v in request.headers.items():
        print(f"  {k}: {v}")
    print("-" * 60)
    print(f"[QUERY PARAMS]: {dict(request.query_params)}")
    print("-" * 60)
    print(f"[RAW BODY] ({len(raw)} bytes):")
    print(raw.decode("utf-8", errors="replace"))
    print("-" * 60)
    parsed = parse_callback_body(raw)
    print(f"[PARSED RESULT]: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
    print("=" * 60)
    body = GradingCallbackData(**parsed["data"])

    result = await db.execute(select(Submission).where(Submission.id == body.submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    existing_report = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == body.submission_id)
    )
    if existing_report.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该提交已有批改报告")

    if body.score < 0 or body.score > 100:
        raise HTTPException(status_code=400, detail="分数必须在 0-100 之间")

    assignment_result = await db.execute(
        select(Assignment).where(Assignment.id == submission.assignment_id)
    )
    assignment = assignment_result.scalar_one_or_none()

    review_status = "confirmed"
    feedback = body.feedback

    if assignment and assignment.grading_mode == "hybrid":
        review_status = "pending_review"
        try:
            detail_obj = json.loads(body.detail) if isinstance(body.detail, str) else body.detail
            confidence = detail_obj.get("confidence", 1.0)
            if confidence < 0.8:
                feedback += f"\n\n[系统提示：智能体置信度 {confidence:.0%}，建议人工复核]"
        except:
            pass

    report = GradingReport(
        submission_id=body.submission_id,
        score=body.score,
        feedback=feedback,
        detail=body.detail,
        generated_by=body.generated_by,
        review_status=review_status,
    )
    db.add(report)

    if review_status == "confirmed":
        submission.status = "graded"

    task_result = await db.execute(
        select(GradingTask).where(GradingTask.submission_id == body.submission_id)
    )
    task = task_result.scalar_one_or_none()
    if task:
        task.status = "graded"
        task.graded_at = datetime.utcnow()

    await _refresh_grading_status(submission.assignment_id, db)

    await db.commit()
    await db.refresh(report)

    return {"code": 0, "data": {"report_id": report.id}}


class ReviewGradeRequest(BaseModel):
    score: Optional[int] = None
    feedback: Optional[str] = None
    action: str = "confirm"


@router.post("/review/{submission_id}")
async def review_grade(
    submission_id: int,
    req: ReviewGradeRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    report_result = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == submission_id)
    )
    report = report_result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="批改报告不存在")

    if report.review_status == "confirmed":
        raise HTTPException(status_code=400, detail="该报告已确认，无需复核")

    if req.action == "confirm":
        report.review_status = "confirmed"
        submission.status = "graded"
    elif req.action == "modify":
        if req.score is not None:
            if req.score < 0 or req.score > 100:
                raise HTTPException(status_code=400, detail="分数必须在 0-100 之间")
            report.score = req.score
        if req.feedback is not None:
            report.feedback = req.feedback
        report.review_status = "modified"
        report.generated_by = f"{report.generated_by}+teacher"
        submission.status = "graded"
    else:
        raise HTTPException(status_code=400, detail="无效的操作类型")

    await _refresh_grading_status(submission.assignment_id, db)

    await db.commit()
    await db.refresh(report)

    return {
        "code": 0,
        "data": {
            "report_id": report.id,
            "review_status": report.review_status,
        },
    }


@router.get("/tasks/{submission_id}")
async def get_grading_task_status(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if current_user.role == "student" and submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此任务")

    task_result = await db.execute(
        select(GradingTask).where(GradingTask.submission_id == submission_id)
    )
    task = task_result.scalar_one_or_none()

    report_result = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == submission_id)
    )
    report = report_result.scalar_one_or_none()

    return {
        "code": 0,
        "data": {
            "submission_id": submission_id,
            "status": task.status if task else None,
            "agent_task_id": task.agent_task_id if task else None,
            "sent_at": task.sent_at.isoformat() if task and task.sent_at else None,
            "graded_at": task.graded_at.isoformat() if task and task.graded_at else None,
            "error_message": task.error_message if task else None,
            "retry_count": task.retry_count if task else 0,
            "report": {
                "score": report.score,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
            } if report else None,
        },
    }


# ============================================================
# 智能体专用接口（API Key 认证）
# ============================================================

class BatchAssignmentItem(BaseModel):
    """批量创建作业的单项"""
    section_id: int
    title: str
    description: str = ""
    question_files: List[str] = []
    grading_prompt: str = ""
    reference_answer: str = ""
    deadline: Optional[str] = None
    grading_mode: str = "auto"


class BatchCreateAssignmentRequest(BaseModel):
    """批量创建作业请求体"""
    assignments: List[BatchAssignmentItem]


@router.post("/batch-assignments")
async def batch_create_assignments(
    req: BatchCreateAssignmentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    批量创建作业（智能体友好接口）

    一次请求为多个小节创建作业，适合智能体批量导入场景。

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    results = []
    errors = []

    for item in req.assignments:
        # 校验小节存在
        section_result = await db.execute(select(Section).where(Section.id == item.section_id))
        section = section_result.scalar_one_or_none()
        if not section:
            errors.append({"section_id": item.section_id, "error": "小节不存在"})
            continue

        # 检查该小节是否已有作业
        existing = await db.execute(select(Assignment).where(Assignment.section_id == item.section_id))
        if existing.scalar_one_or_none():
            errors.append({"section_id": item.section_id, "error": "该小节已有作业"})
            continue

        deadline_dt = None
        if item.deadline:
            try:
                deadline_dt = datetime.fromisoformat(item.deadline.replace("Z", "+00:00"))
            except:
                errors.append({"section_id": item.section_id, "error": "截止时间格式错误"})
                continue

        if item.grading_mode not in ["auto", "manual", "hybrid"]:
            errors.append({"section_id": item.section_id, "error": "批改模式无效"})
            continue

        assignment = Assignment(
            section_id=item.section_id,
            course_id=section.course_id,
            title=item.title,
            description=item.description,
            question_files=json.dumps(item.question_files),
            grading_prompt=item.grading_prompt,
            reference_answer=item.reference_answer,
            deadline=deadline_dt,
            status="draft",
            grading_mode=item.grading_mode,
        )
        db.add(assignment)
        results.append({"section_id": item.section_id, "title": item.title})

    await db.commit()

    return {
        "code": 0,
        "data": {
            "created": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
    }


@router.get("/course/{course_id}/assignment-details")
async def list_course_assignment_details(
    course_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程下所有作业的完整详情（含参考答案）— 智能体专用

    与 /course/{course_id} 的区别：
    - 返回 reference_answer 字段
    - 需 teacher/admin 权限
    - 适合智能体查看已有作业并据此批改

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    result = await db.execute(
        select(Assignment).where(Assignment.course_id == course_id)
    )
    assignments = result.scalars().all()
    return {"code": 0, "data": [_assignment_to_dict(a) for a in assignments]}
