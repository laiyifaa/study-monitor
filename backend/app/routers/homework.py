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
        POST   /api/homework/trigger-grading/{assignment_id} — 手动触发智能体批改

    学生端：
        GET    /api/homework/assignments/{section_id}  — 获取小节作业
        POST   /api/homework/submissions               — 提交作业（上传图片）
        GET    /api/homework/my-submissions            — 查看我的提交列表

    文件上传：
        POST   /api/homework/upload                    — 上传作业图片
"""

import os
import re
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional, List

from app.config import get_settings
from app.database import get_db
from app.models.models import Assignment, Submission, GradingReport, GradingTask, Course, Section, User
from app.services.agent_caller import parse_answer_file_with_agent, call_grading_agent
from app.services.image_stitcher import stitch_images, image_url_to_local_path
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/homework", tags=["作业管理"])
settings = get_settings()

HOMEWORK_UPLOAD_DIR = "uploads/homework"
ANSWER_UPLOAD_DIR = os.path.join(HOMEWORK_UPLOAD_DIR, "answers")
ANSWER_TYPES = {"option_letter", "true_false", "fill_blank"}
ANSWER_TYPE_ALIASES = {
    "choice": "option_letter",
    "single_choice": "option_letter",
    "multiple_choice": "option_letter",
    "option_letter": "option_letter",
    "judge": "true_false",
    "true_false": "true_false",
    "fill": "fill_blank",
    "fill_blank": "fill_blank",
}
ANSWER_DEFAULT_SCORES = {
    "option_letter": 2,
    "true_false": 1,
    "fill_blank": 2,
}


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
    auto_grade_at: Optional[str] = None
    grading_mode: str = "auto"


class UpdateAssignmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    question_files: Optional[List[str]] = None
    grading_prompt: Optional[str] = None
    reference_answer: Optional[str] = None  # v5.0: 参考答案
    deadline: Optional[str] = None
    auto_grade_at: Optional[str] = None
    status: Optional[str] = None
    grading_mode: Optional[str] = None


class CreateSubmissionRequest(BaseModel):
    assignment_id: int
    images: List[str]


class ManualGradeRequest(BaseModel):
    score: int
    feedback: str = ""


class SaveAnswerRequest(BaseModel):
    answer: Any  # 支持新旧答案 JSON 结构


def _normalize_answer_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return ANSWER_TYPE_ALIASES.get(normalized, normalized)


def _normalize_answer_text(answer_type: str, value: Any) -> str:
    text = str(value if value is not None else "")
    if answer_type == "option_letter":
        return re.sub(r"[\s,，、]+", "", text).upper()
    if answer_type == "true_false":
        cleaned = text.strip().upper()
        if cleaned in {"T", "TRUE", "1", "Y", "YES", "对", "正确"}:
            return "T"
        if cleaned in {"F", "FALSE", "0", "N", "NO", "错", "错误"}:
            return "F"
        return cleaned
    return text.replace("\r\n", "\n").strip()


def _normalize_answer_score(answer_type: str, value: Any) -> int:
    if value is None:
        return ANSWER_DEFAULT_SCORES.get(answer_type, 2)

    if isinstance(value, str) and not value.strip():
        return ANSWER_DEFAULT_SCORES.get(answer_type, 2)

    try:
        score = int(float(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="答案分数格式错误")

    if score < 0:
        raise HTTPException(status_code=400, detail="答案分数不能小于 0")
    return score


def _iter_answer_entries(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield str(item.get("no", "")).strip(), item
        return

    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="答案必须是 JSON 对象")

    items = obj.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                yield str(item.get("no", "")).strip(), item
        return

    for key, value in obj.items():
        if key in {"version", "items"}:
            continue
        yield str(key).strip(), value


def _normalize_answer_object(value: Any) -> dict:
    if value is None or value == "":
        return {}

    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="答案 JSON 格式错误")
    else:
        obj = value

    if not isinstance(obj, (dict, list)):
        raise HTTPException(status_code=400, detail="答案必须是 JSON 对象")

    normalized = {}
    seen_nos = set()
    for index, (no, item) in enumerate(_iter_answer_entries(obj), start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"第 {index} 题格式错误")

        entry_no = no or str(item.get("no", "")).strip()
        if not entry_no:
            raise HTTPException(status_code=400, detail=f"第 {index} 题缺少题号")
        if entry_no in seen_nos:
            raise HTTPException(status_code=400, detail=f"第 {entry_no} 题重复")

        qtype = _normalize_answer_type(item.get("type") or item.get("question_type"))
        if qtype not in ANSWER_TYPES:
            raise HTTPException(status_code=400, detail=f"第 {entry_no} 题题型无效")

        answer = _normalize_answer_text(qtype, item.get("answer"))
        if not answer:
            raise HTTPException(status_code=400, detail=f"第 {entry_no} 题缺少答案")
        if qtype == "option_letter" and not re.fullmatch(r"[A-Z]+", answer):
            raise HTTPException(status_code=400, detail=f"第 {entry_no} 题选项字母答案格式无效")
        if qtype == "true_false" and answer not in {"T", "F"}:
            raise HTTPException(status_code=400, detail=f"第 {entry_no} 题判断题答案只能是 T 或 F")

        score = _normalize_answer_score(qtype, item.get("score"))
        normalized[entry_no] = {
            "answer": answer,
            "type": qtype,
            "score": score,
        }
        seen_nos.add(entry_no)

    return normalized


def _normalize_answer_json(value: Any) -> str:
    normalized = _normalize_answer_object(value)
    return json.dumps(normalized, ensure_ascii=False) if normalized else ""


def _answer_to_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return _normalize_answer_object(raw)
    except (HTTPException, json.JSONDecodeError, TypeError, ValueError):
        return {}


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
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".doc", ".docx"]:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/gif/webp/pdf/doc/docx 格式")

    question_dir = os.path.join(HOMEWORK_UPLOAD_DIR, "questions")
    os.makedirs(question_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(question_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/homework/questions/{filename}"}}


def _assignment_to_dict(a: Assignment, include_answer: bool = False):
    """统一作业序列化函数（v4.0 section 级）"""
    data = {
        "id": a.id,
        "section_id": a.section_id,
        "course_id": a.course_id,
        "title": a.title,
        "description": a.description,
        "question_files": json.loads(a.question_files),
        "grading_prompt": a.grading_prompt,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "auto_grade_at": a.auto_grade_at.isoformat() if a.auto_grade_at else None,
        "status": a.status,
        "grading_mode": a.grading_mode,
        "grading_status": a.grading_status,
        "created_at": a.created_at.isoformat(),
    }
    if include_answer:
        data["reference_answer"] = a.reference_answer or ""
    return data


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
    include_answer = current_user.role in ["teacher", "admin"]
    return {"code": 0, "data": [_assignment_to_dict(a, include_answer=include_answer) for a in assignments]}


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
        "data": _assignment_to_dict(assignment, include_answer=current_user.role in ["teacher", "admin"]),
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

    auto_grade_dt = None
    if req.auto_grade_at:
        try:
            auto_grade_dt = datetime.fromisoformat(req.auto_grade_at.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="自动批改时间格式错误")

    if req.grading_mode not in ["auto", "manual", "hybrid"]:
        raise HTTPException(status_code=400, detail="批改模式无效")

    assignment = Assignment(
        section_id=section_id,
        course_id=section.course_id,  # 冗余字段，从 section 自动填入
        title=req.title,
        description=req.description,
        question_files=json.dumps(req.question_files),
        grading_prompt=req.grading_prompt,
        reference_answer=_normalize_answer_json(req.reference_answer),
        deadline=deadline_dt,
        auto_grade_at=auto_grade_dt,
        status="draft",
        grading_mode=req.grading_mode,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return {"code": 0, "data": _assignment_to_dict(assignment, include_answer=True)}


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
        assignment.reference_answer = _normalize_answer_json(req.reference_answer)
    if req.deadline is not None:
        try:
            assignment.deadline = datetime.fromisoformat(req.deadline.replace("Z", "+00:00"))
        except:
            raise HTTPException(status_code=400, detail="截止时间格式错误")
    if req.auto_grade_at is not None:
        if req.auto_grade_at == "":
            assignment.auto_grade_at = None
        else:
            try:
                assignment.auto_grade_at = datetime.fromisoformat(req.auto_grade_at.replace("Z", "+00:00"))
            except:
                raise HTTPException(status_code=400, detail="自动批改时间格式错误")
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


@router.get("/assignments/{section_id}/answer")
async def get_assignment_answer(
    section_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    return {
        "code": 0,
        "data": {
            "assignment_id": assignment.id,
            "section_id": section_id,
            "answer": _answer_to_object(assignment.reference_answer),
        },
    }


@router.put("/assignments/{section_id}/answer")
async def save_assignment_answer(
    section_id: int,
    req: SaveAnswerRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    assignment.reference_answer = _normalize_answer_json(req.answer)
    await db.commit()
    return {"code": 0, "data": {"answer": _answer_to_object(assignment.reference_answer)}}


@router.post("/answer/parse")
async def parse_answer_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".doc", ".docx"]:
        raise HTTPException(status_code=400, detail="仅支持 PDF/DOC/DOCX 格式")

    os.makedirs(ANSWER_UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(ANSWER_UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        parsed = await parse_answer_file_with_agent(filepath)
        normalized = _normalize_answer_json(parsed)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"答案解析失败：{str(e)}")

    return {"code": 0, "data": {"answer": _answer_to_object(normalized)}}


@router.post("/assignments/{section_id}/answer/parse")
async def parse_assignment_answer_file(
    section_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".doc", ".docx"]:
        raise HTTPException(status_code=400, detail="仅支持 PDF/DOC/DOCX 格式")

    os.makedirs(ANSWER_UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(ANSWER_UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        parsed = await parse_answer_file_with_agent(filepath)
        assignment.reference_answer = _normalize_answer_json(parsed)
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"答案解析失败：{str(e)}")

    return {"code": 0, "data": {"answer": _answer_to_object(assignment.reference_answer)}}


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
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
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


@router.get("/assignments/{course_id}/submissions-summary")
async def list_submissions_summary(
    course_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程作业提交汇总（含已交/未交）

    数据口径说明：
    - 全部学生：按角色筛选 users.role == 'student'
    - 已交：提交该课程作业的学生（基于 assignment_id 的最新提交 is_latest=True）
    - 未交：全体学生减已交学生集合
    """
    assignment_result = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    assignment = assignment_result.scalar_one_or_none()

    if not assignment:
        return {
            "code": 0,
            "data": {
                "assignment": None,
                "submissions": [],
                "unsubmitted_students": [],
                "summary": {
                    "total_students": 0,
                    "submitted_count": 0,
                    "unsubmitted_count": 0,
                    "pending_count": 0,
                    "graded_count": 0,
                },
            },
        }

    submission_result = await db.execute(
        select(Submission)
        .where(Submission.assignment_id == assignment.id)
        .where(Submission.is_latest == True)
        .order_by(Submission.submitted_at.desc())
    )
    submissions = submission_result.scalars().all()

    submission_ids = [s.id for s in submissions]
    student_ids = [s.user_id for s in submissions]

    user_rows = await db.execute(select(User).where(User.id.in_(student_ids))) if student_ids else []
    users = {u.id: u for u in user_rows.scalars().all()} if student_ids else {}

    report_rows = await db.execute(
        select(GradingReport).where(GradingReport.submission_id.in_(submission_ids))
    ) if submission_ids else []
    reports = {r.submission_id: r for r in report_rows.scalars().all()} if submission_ids else {}

    task_rows = await db.execute(
        select(GradingTask).where(GradingTask.submission_id.in_(submission_ids))
    ) if submission_ids else []
    tasks = {t.submission_id: t for t in task_rows.scalars().all()} if submission_ids else {}

    data = []
    for s in submissions:
        user = users.get(s.user_id)
        report = reports.get(s.id)
        task = tasks.get(s.id)
        data.append({
            "id": s.id,
            "user": {"id": user.id, "name": user.name} if user else None,
            "images": json.loads(s.images),
            "status": s.status,
            "submitted_at": s.submitted_at.isoformat(),
            "report": {
                "score": report.score,
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat(),
            } if report else None,
            "task": {
                "status": task.status,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "sent_at": task.sent_at.isoformat() if task and task.sent_at else None,
                "graded_at": task.graded_at.isoformat() if task and task.graded_at else None,
            } if task else None,
        })

    all_students_result = await db.execute(select(User).where(User.role == "student"))
    all_students = all_students_result.scalars().all()
    all_student_ids = {u.id for u in all_students}

    submitted_student_ids = set(student_ids)
    unsubmitted_students = [
        {"id": u.id, "name": u.name, "class_name": u.class_name}
        for u in all_students
        if u.id not in submitted_student_ids
    ]

    pending_count = sum(1 for s in submissions if s.status == "pending")
    graded_count = sum(1 for s in submissions if s.status == "graded")

    return {
        "code": 0,
        "data": {
            "assignment": {
                "id": assignment.id,
                "status": assignment.status,
                "grading_status": assignment.grading_status,
                "grading_mode": assignment.grading_mode,
            },
            "submissions": data,
            "unsubmitted_students": sorted(
                unsubmitted_students,
                key=lambda s: ((s["class_name"] or ""), (s["name"] or "")),
            ),
            "summary": {
                "total_students": len(all_students),
                "submitted_count": len(submitted_student_ids & all_student_ids),
                "unsubmitted_count": max(len(all_student_ids) - len(submitted_student_ids), 0),
                "pending_count": pending_count,
                "graded_count": graded_count,
            },
        },
    }


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
            "full_score": report.full_score,
            "status": report.status,
            "accuracy": report.accuracy,
            "correct_count": report.correct_count,
            "wrong_count": report.wrong_count,
            "feedback": report.feedback,
            "detail": json.loads(report.detail),
            "review_questions": json.loads(report.review_questions) if report.review_questions else [],
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
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
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
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
            } if report else None,
        },
    }


@router.post("/trigger-grading/{assignment_id}")
async def trigger_grading(
    assignment_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发智能体批改 — 异步执行
    对作业下所有 pending 且 is_latest=True 的提交进行 AI 批改。

    权限要求：teacher / admin
    """
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if assignment.status != "published":
        raise HTTPException(status_code=400, detail="作业未发布")

    sub_result = await db.execute(
        select(Submission).where(
            and_(
                Submission.assignment_id == assignment_id,
                Submission.status == "pending",
                Submission.is_latest == True,
            )
        )
    )
    submissions = sub_result.scalars().all()

    if not submissions:
        return {"code": 0, "data": {"message": "无待批改的提交", "submission_count": 0}}

    assignment.grading_triggered = True
    await db.commit()

    async def _run_grading():
        for submission in submissions:
            try:
                async with async_session() as session:
                    existing = await session.execute(
                        select(GradingTask).where(GradingTask.submission_id == submission.id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    images = json.loads(submission.images)
                    if not images:
                        continue

                    local_paths = [image_url_to_local_path(url) for url in images]
                    output_filename = f"stitched_{submission.id}.jpg"
                    stitched_url = stitch_images(local_paths, output_filename)

                    task = GradingTask(
                        submission_id=submission.id,
                        stitched_image_url=stitched_url,
                        status="pending",
                    )
                    session.add(task)
                    await session.commit()
                    await session.refresh(task)

                await call_grading_agent(
                    task_id=task.id,
                    submission_id=submission.id,
                    stitched_image_url=stitched_url,
                    prompt=assignment.grading_prompt,
                    answer_json=assignment.reference_answer or "",
                )
            except Exception as e:
                logger.error(f"手动触发批改失败: submission_id={submission.id}, error={e}")

    background_tasks.add_task(_run_grading)

    return {
        "code": 0,
        "data": {
            "message": "批改任务已启动",
            "submission_count": len(submissions),
        },
    }


@router.get("/trigger-status/{assignment_id}")
async def trigger_grading_status(
    assignment_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    查询作业下所有提交的批改进度（轮询用）

    权限要求：teacher / admin
    """
    result = await db.execute(
        select(Submission).where(
            and_(
                Submission.assignment_id == assignment_id,
                Submission.is_latest == True,
            )
        )
    )
    submissions = result.scalars().all()

    total = len(submissions)
    pending = 0
    processing = 0
    graded = 0
    failed = 0

    for s in submissions:
        task = (await db.execute(
            select(GradingTask).where(GradingTask.submission_id == s.id)
        )).scalar_one_or_none()

        if not task or task.status == "pending":
            pending += 1
        elif task.status == "sent":
            processing += 1
        elif task.status == "graded":
            graded += 1
        elif task.status == "failed":
            failed += 1

    return {
        "code": 0,
        "data": {
            "total": total,
            "pending": pending,
            "processing": processing,
            "graded": graded,
            "failed": failed,
            "done": graded + failed,
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
            reference_answer=_normalize_answer_json(item.reference_answer),
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
    return {"code": 0, "data": [_assignment_to_dict(a, include_answer=True) for a in assignments]}
