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
        POST   /api/homework/regrade/{submission_id}   — 重新触发单条提交智能批改
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
import logging
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Request, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional, List

from app.config import get_settings
from app.database import get_db, async_session
from app.models.models import Assignment, Submission, GradingReport, GradingTask, Course, Section, User
from app.services.agent_caller import parse_answer_file_with_agent, call_grading_agent
from app.services.image_stitcher import stitch_images, image_url_to_local_path
from app.utils.datetime_helper import now_cn_naive, parse_cn_datetime_input

from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/homework", tags=["作业管理"])
settings = get_settings()
logger = logging.getLogger(__name__)

HOMEWORK_UPLOAD_DIR = "uploads/homework"
ANSWER_UPLOAD_DIR = os.path.join(HOMEWORK_UPLOAD_DIR, "answers")
QUESTION_UPLOAD_DIR = os.path.join(HOMEWORK_UPLOAD_DIR, "questions")
ANSWER_FILE_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".doc", ".docx"]
ANSWER_FILE_ALLOWED_PREFIXES = ("uploads/homework/answers/", "homework/answers/")
UPLOAD_BASE_DIRS = [Path(__file__).resolve().parents[2] / "uploads", Path(__file__).resolve().parents[3] / "uploads"]
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


async def _prepare_grading_task(
    session: AsyncSession,
    submission_id: int,
    force: bool = False,
    batch_started_at: datetime | None = None,
) -> GradingTask | None:
    existing_result = await session.execute(
        select(GradingTask).where(GradingTask.submission_id == submission_id).order_by(GradingTask.id.desc())
    )
    task = existing_result.scalars().first()

    if task and task.status in {"graded", "sent"} and not force:
        return None

    if not task:
        task = GradingTask(
            submission_id=submission_id,
            stitched_image_url="",
            status="pending",
            sent_at=batch_started_at,
        )
        session.add(task)
    else:
        previous_status = task.status
        previous_sent_at = task.sent_at
        task.stitched_image_url = ""
        task.agent_task_id = ""
        task.status = "pending"
        task.retry_count = 0
        task.error_message = ""
        if batch_started_at is not None:
            task.sent_at = batch_started_at
        elif previous_status == "pending" and previous_sent_at:
            task.sent_at = previous_sent_at
        else:
            task.sent_at = None
        task.graded_at = None

    await session.commit()
    await session.refresh(task)
    return task


async def _execute_grading_for_submission(
    submission_id: int,
    prompt: str,
    answer_json: str = "",
    force: bool = False,
) -> bool:
    task_id = None

    try:
        async with async_session() as session:
            submission_result = await session.execute(select(Submission).where(Submission.id == submission_id))
            submission = submission_result.scalar_one_or_none()
            if not submission:
                raise Exception(f"提交 {submission_id} 不存在")

            images = _load_url_list(submission.images)
            if not images:
                raise ValueError("提交未包含可批改图片")

            local_paths = [image_url_to_local_path(url) for url in images]
            missing_paths = [path for path in local_paths if not os.path.exists(path)]
            if missing_paths:
                raise FileNotFoundError("原始作业图片缺失，无法重新批改")

            task = await _prepare_grading_task(session, submission_id, force=force)
            if not task:
                return False

            task_id = task.id
            output_filename = f"stitched_{submission.id}.jpg"
            stitched_url = stitch_images(local_paths, output_filename)

            task.stitched_image_url = stitched_url
            await session.commit()

        return await call_grading_agent(
            task_id=task_id,
            submission_id=submission_id,
            stitched_image_url=stitched_url,
            prompt=prompt,
            answer_json=answer_json,
        )
    except Exception as e:
        if task_id is not None:
            await _mark_task_failed(task_id, str(e))
        raise


async def _mark_task_failed(task_id: int, error_message: str):
    async with async_session() as session:
        task_result = await session.execute(
            select(GradingTask).where(GradingTask.id == task_id)
        )
        task = task_result.scalar_one_or_none()
        if not task:
            return

        task.status = "failed"
        task.error_message = error_message
        await session.commit()


class CreateAssignmentRequest(BaseModel):
    title: str
    description: str = ""
    question_files: List[str] = []
    answer_files: List[str] = []
    grading_prompt: str = ""
    reference_answer: str = ""  # v5.0: 参考答案
    deadline: Optional[str] = None
    auto_grade_at: Optional[str] = None
    grading_mode: str = "auto"


class UpdateAssignmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    question_files: Optional[List[str]] = None
    answer_files: Optional[List[str]] = None
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


class ReturnSubmissionRequest(BaseModel):
    reason: str = ""
    field_validator = field_validator("reason")(lambda cls, v: (v or "").strip()[:500])


class SaveAnswerRequest(BaseModel):
    answer: Any  # 支持新旧答案 JSON 结构
    answer_files: Optional[List[str]] = None


class AnswerFileAccessRequest(BaseModel):
    section_id: Optional[int] = None
    file_index: Optional[int] = None
    file_url: Optional[str] = None


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


def _load_url_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _load_report_detail(report: GradingReport | None) -> dict:
    if not report or not report.detail:
        return {}
    try:
        value = json.loads(report.detail)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_review_questions(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _student_questions_from_detail(detail: dict) -> list[dict]:
    questions: list[dict] = []

    raw_questions = detail.get("questions")
    if isinstance(raw_questions, list):
        for item in raw_questions:
            if not isinstance(item, dict):
                continue
            index = item.get("index") or item.get("qid") or item.get("question_id") or item.get("no") or item.get("key")
            correct = item.get("correct")
            if correct is None:
                correct = item.get("ok")
            if correct is None:
                correct = item.get("is_correct")
            if index in {None, ""} or correct is None:
                continue
            questions.append({
                "index": str(index),
                "correct": bool(correct),
            })
        if questions:
            return questions

    raw_details = detail.get("details")
    if not isinstance(raw_details, list) or not raw_details:
        nested = detail.get("result")
        if isinstance(nested, dict):
            raw_details = nested.get("details")
    if not isinstance(raw_details, list):
        return questions

    for item in raw_details:
        if not isinstance(item, dict):
            continue
        index = item.get("index") or item.get("qid") or item.get("question_id") or item.get("no") or item.get("key")
        correct = item.get("correct")
        if correct is None:
            correct = item.get("ok")
        if correct is None:
            correct = item.get("is_correct")
        if index in {None, ""} or correct is None:
            continue
        questions.append({
            "index": str(index),
            "correct": bool(correct),
        })
    return questions


def _report_to_staff_summary(report: GradingReport) -> dict:
    return {
        "score": report.score,
        "full_score": report.full_score,
        "status": report.status,
        "accuracy": report.accuracy,
        "correct_count": report.correct_count,
        "wrong_count": report.wrong_count,
        "feedback": report.feedback,
        "generated_by": report.generated_by,
        "created_at": report.created_at.isoformat(),
    }


def _report_to_student_summary(report: GradingReport) -> dict:
    detail = _load_report_detail(report)
    return {
        "status": report.status,
        "correct_count": report.correct_count,
        "wrong_count": report.wrong_count,
        "feedback": report.feedback,
        "questions": _student_questions_from_detail(detail),
    }


def _normalize_homework_file_url(file_url: str) -> str:
    normalized = image_url_to_local_path(str(file_url or "").strip())
    normalized = os.path.normpath(normalized).replace("\\", "/")
    return normalized.lstrip("/")


def _is_safe_answer_file_url(file_url: str) -> bool:
    normalized = _normalize_homework_file_url(file_url)
    if not normalized or normalized in {".", ".."} or normalized.startswith("../"):
        return False
    return normalized.startswith(ANSWER_FILE_ALLOWED_PREFIXES)


def _resolve_answer_file_path(file_url: str) -> Path | None:
    if not _is_safe_answer_file_url(file_url):
        return None

    normalized = _normalize_homework_file_url(file_url)
    candidates = [normalized]
    if normalized.startswith("uploads/"):
        candidates.append(normalized[len("uploads/"):])

    for base_dir in UPLOAD_BASE_DIRS:
        for relative in candidates:
            candidate = (base_dir / relative).resolve()
            try:
                upload_root = base_dir.resolve()
            except OSError:
                continue
            if str(candidate).startswith(f"{str(upload_root)}{os.sep}") and candidate.is_file():
                return candidate
    return None


def _answer_files_to_student_entries(files: list[str]) -> list[dict]:
    entries = []
    for index, file_url in enumerate(files):
        normalized = str(file_url or "").strip().split("?", 1)[0].split("#", 1)[0]
        entries.append({
            "index": index,
            "name": os.path.basename(normalized) or f"answer-{index + 1}",
        })
    return entries


async def _student_can_view_answer_files(assignment_id: int, student_id: int, db: AsyncSession) -> bool:
    latest_submission = (await db.execute(
        select(Submission).where(
            and_(
                Submission.assignment_id == assignment_id,
                Submission.user_id == student_id,
                Submission.is_latest == True,
            )
        ).order_by(Submission.id.desc())
    )).scalars().first()
    if not latest_submission:
        return False

    report_id = await db.scalar(
        select(GradingReport.id).where(GradingReport.submission_id == latest_submission.id)
    )
    return report_id is not None


async def _resolve_assignment_answer_file(
    section_id: int,
    file_index: int,
    db: AsyncSession,
) -> tuple[Assignment, list[str], str]:
    assignment = (await db.execute(select(Assignment).where(Assignment.section_id == section_id))).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    answer_files = _load_url_list(getattr(assignment, "answer_files", None))
    if file_index < 0 or file_index >= len(answer_files):
        raise HTTPException(status_code=404, detail="答案附件不存在")
    return assignment, answer_files, answer_files[file_index]


async def _ensure_assignment_contains_answer_file(section_id: int, file_url: str, db: AsyncSession) -> Assignment:
    assignment = (await db.execute(select(Assignment).where(Assignment.section_id == section_id))).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")
    if file_url not in _load_url_list(getattr(assignment, "answer_files", None)):
        raise HTTPException(status_code=404, detail="答案附件不存在")
    return assignment


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

    os.makedirs(QUESTION_UPLOAD_DIR, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(QUESTION_UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/homework/questions/{filename}"}}


@router.post("/upload-answer")
async def upload_answer_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ANSWER_FILE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持图片/PDF/DOC/DOCX 格式")

    os.makedirs(ANSWER_UPLOAD_DIR, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(ANSWER_UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    return {"code": 0, "data": {"url": f"/uploads/homework/answers/{filename}"}}


def _assignment_to_dict(a: Assignment, include_answer: bool = False):
    """统一作业序列化函数（v4.0 section 级）"""
    data = {
        "id": a.id,
        "section_id": a.section_id,
        "course_id": a.course_id,
        "title": a.title,
        "description": a.description,
        "question_files": _load_url_list(a.question_files),
        "grading_prompt": a.grading_prompt,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "auto_grade_at": a.auto_grade_at.isoformat() if a.auto_grade_at else None,
        "status": a.status,
        "grading_mode": a.grading_mode,
        "grading_status": a.grading_status,
        "grading_triggered": a.grading_triggered,
        "created_at": a.created_at.isoformat(),
    }
    if include_answer:
        data["reference_answer"] = a.reference_answer or ""
        data["answer_files"] = _load_url_list(getattr(a, "answer_files", None))
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
            deadline_dt = parse_cn_datetime_input(req.deadline)
        except ValueError:
            raise HTTPException(status_code=400, detail="截止时间格式错误")

    auto_grade_dt = None
    if req.auto_grade_at:
        try:
            auto_grade_dt = parse_cn_datetime_input(req.auto_grade_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="自动批改时间格式错误")

    if req.grading_mode not in ["auto", "manual", "hybrid"]:
        raise HTTPException(status_code=400, detail="批改模式无效")

    assignment = Assignment(
        section_id=section_id,
        course_id=section.course_id,  # 冗余字段，从 section 自动填入
        title=req.title,
        description=req.description,
        question_files=json.dumps(req.question_files),
        answer_files=json.dumps(req.answer_files),
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
    if req.answer_files is not None:
        assignment.answer_files = json.dumps(req.answer_files)
    if req.grading_prompt is not None:
        assignment.grading_prompt = req.grading_prompt
    if req.reference_answer is not None:
        assignment.reference_answer = _normalize_answer_json(req.reference_answer)
    if req.deadline is not None:
        if req.deadline == "":
            assignment.deadline = None
        else:
            try:
                assignment.deadline = parse_cn_datetime_input(req.deadline)
            except ValueError:
                raise HTTPException(status_code=400, detail="截止时间格式错误")
    if req.auto_grade_at is not None:
        if req.auto_grade_at == "":
            assignment.auto_grade_at = None
        else:
            try:
                assignment.auto_grade_at = parse_cn_datetime_input(req.auto_grade_at)
            except ValueError:
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
            "answer_files": _load_url_list(getattr(assignment, "answer_files", None)),
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
    if req.answer_files is not None:
        assignment.answer_files = json.dumps(req.answer_files)
    await db.commit()
    return {
        "code": 0,
        "data": {
            "answer": _answer_to_object(assignment.reference_answer),
            "answer_files": _load_url_list(getattr(assignment, "answer_files", None)),
        },
    }


@router.post("/answer-files/access")
async def create_answer_file_access_url(
    req: AnswerFileAccessRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_url = ""
    section_id = req.section_id

    if current_user.role in ["teacher", "admin"] and req.file_url:
        file_url = req.file_url
    else:
        if section_id is None or req.file_index is None:
            raise HTTPException(status_code=400, detail="缺少答案附件定位信息")

        assignment, answer_files, file_url = await _resolve_assignment_answer_file(section_id, req.file_index, db)
        if current_user.role == "student":
            if not await _student_can_view_answer_files(assignment.id, current_user.id, db):
                raise HTTPException(status_code=403, detail="当前不可查看答案附件")

    if current_user.role not in ["teacher", "admin", "student"]:
        raise HTTPException(status_code=403, detail="无权访问答案附件")

    if not _is_safe_answer_file_url(file_url):
        raise HTTPException(status_code=400, detail="答案附件路径非法")
    if not _resolve_answer_file_path(file_url):
        raise HTTPException(status_code=404, detail="答案附件不存在")

    # 转为直接文件 URL，与题目 PDF 格式一致
    if file_url.startswith('/uploads/'):
        public_url = f"/api/uploads/{file_url[len('/uploads/'):]}"
    elif file_url.startswith('uploads/'):
        public_url = f"/api/uploads/{file_url[len('uploads/'):]}"
    else:
        public_url = f"/api/uploads/{file_url.lstrip('/')}"
    return {"code": 0, "data": {"url": public_url}}


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
        select(Submission)
        .where(Submission.assignment_id == assignment.id)
        .where(Submission.is_latest == True)
        .order_by(Submission.submitted_at.desc())
    )
    submissions = result.scalars().all()

    submission_ids = [s.id for s in submissions]
    student_ids = [s.user_id for s in submissions]

    # 批量查询用户、报告、任务，避免 N+1
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
            "user": {"id": user.id, "name": user.name, "class_name": user.class_name} if user else None,
            "images": _load_url_list(s.images),
            "status": s.status,
            "is_late": s.is_late,  # v4.0: 迟交标记
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "report": {
                "score": report.score,
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            } if report else None,
            "task": {
                "status": task.status,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "sent_at": task.sent_at.isoformat() if task and task.sent_at else None,
                "graded_at": task.graded_at.isoformat() if task and task.graded_at else None,
            } if task else None,
        })

    return {"code": 0, "data": data}


@router.get("/assignments/{section_id}/student-submissions")
async def list_student_submissions(
    section_id: int,
    user_id: int = Query(..., description="学生用户ID"),
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    assignment_result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
    assignment = assignment_result.scalar_one_or_none()
    if not assignment:
        return {"code": 0, "data": []}

    result = await db.execute(
        select(Submission)
        .where(
            and_(
                Submission.assignment_id == assignment.id,
                Submission.user_id == user_id,
            )
        )
        .order_by(Submission.version.desc())
    )
    submissions = result.scalars().all()
    if not submissions:
        return {"code": 0, "data": []}

    submission_ids = [s.id for s in submissions]

    user_rows = await db.execute(select(User).where(User.id == user_id))
    user = user_rows.scalar_one_or_none()

    report_rows = await db.execute(
        select(GradingReport).where(GradingReport.submission_id.in_(submission_ids))
    )
    reports = {r.submission_id: r for r in report_rows.scalars().all()}

    task_rows = await db.execute(
        select(GradingTask).where(GradingTask.submission_id.in_(submission_ids))
    )
    tasks = {t.submission_id: t for t in task_rows.scalars().all()}

    data = []
    for s in submissions:
        report = reports.get(s.id)
        task = tasks.get(s.id)
        data.append({
            "id": s.id,
            "version": s.version,
            "user": {"id": user.id, "name": user.name, "class_name": user.class_name} if user else None,
            "images": _load_url_list(s.images),
            "status": s.status,
            "is_late": s.is_late,
            "is_latest": s.is_latest,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "report": {
                "score": report.score,
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            } if report else None,
            "task": {
                "status": task.status,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "sent_at": task.sent_at.isoformat() if task and task.sent_at else None,
                "graded_at": task.graded_at.isoformat() if task and task.graded_at else None,
            } if task else None,
            "return_reason": s.return_reason,
            "returned_at": s.returned_at.isoformat() if s.returned_at else None,
        })

    return {"code": 0, "data": data}


@router.get("/assignments/{section_id}/submissions-summary")
async def list_submissions_summary(
    section_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取小节作业提交汇总（含已交/未交）

    v4.0: 从 course_id 切换到 section_id，1 section = 1 assignment

    数据口径说明：
    - 全部学生：按角色筛选 users.role == 'student'
    - 已交：提交该小节作业的学生（基于 assignment_id 的最新提交 is_latest=True）
    - 未交：全体学生减已交学生集合
    """
    assignment_result = await db.execute(select(Assignment).where(Assignment.section_id == section_id))
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
            "user": {"id": user.id, "name": user.name, "class_name": user.class_name} if user else None,
            "images": _load_url_list(s.images),
            "status": s.status,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "report": {
                "score": report.score,
                "full_score": report.full_score,
                "status": report.status,
                "accuracy": report.accuracy,
                "correct_count": report.correct_count,
                "wrong_count": report.wrong_count,
                "feedback": report.feedback,
                "generated_by": report.generated_by,
                "created_at": report.created_at.isoformat() if report.created_at else None,
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

    if current_user.role == "student":
        return {
            "code": 0,
            "data": {
                "submission_id": submission_id,
                **_report_to_student_summary(report),
                "created_at": report.created_at.isoformat(),
            },
        }

    return {
        "code": 0,
        "data": {
            "submission_id": submission_id,
            **_report_to_staff_summary(report),
            "detail": _load_report_detail(report),
            "review_questions": _load_review_questions(report.review_questions),
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
    if assignment.deadline and now_cn_naive() > assignment.deadline:
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
    existing = existing_result.scalars().first()

    next_version = 1
    if existing:
        existing_report_id = await db.scalar(
            select(GradingReport.id).where(GradingReport.submission_id == existing.id)
        )
        if existing.status == "returned":
            pass
        elif existing.status == "graded" or existing_report_id is not None:
            raise HTTPException(status_code=400, detail="当前提交已批改，不能再次提交")
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
    if assignment.grading_mode != "manual":
        assignment.grading_triggered = False

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

    # 批量查询 assignment 和 report，避免 N+1
    assignment_ids = list({s.assignment_id for s in submissions})
    submission_ids = [s.id for s in submissions]

    assignment_rows = await db.execute(select(Assignment).where(Assignment.id.in_(assignment_ids))) if assignment_ids else []
    assignments = {a.id: a for a in assignment_rows.scalars().all()} if assignment_ids else {}

    report_rows = await db.execute(
        select(GradingReport).where(GradingReport.submission_id.in_(submission_ids))
    ) if submission_ids else []
    reports = {r.submission_id: r for r in report_rows.scalars().all()} if submission_ids else {}

    data = []
    for s in submissions:
        assignment = assignments.get(s.assignment_id)
        report = reports.get(s.id)
        can_view_answer_files = bool(assignment and s.is_latest and report and s.status != "returned")

        data.append({
            "id": s.id,
            "assignment": {
                "id": assignment.id,
                "title": assignment.title,
                "section_id": assignment.section_id,  # v4.0
                "course_id": assignment.course_id,
            } if assignment else None,
            "images": _load_url_list(s.images),
            "status": s.status,
            "is_late": s.is_late,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "can_view_answer_files": can_view_answer_files,
            "answer_files": _answer_files_to_student_entries(_load_url_list(getattr(assignment, "answer_files", None))) if can_view_answer_files else [],
            "report": _report_to_student_summary(report) if report else None,
            "return_reason": s.return_reason,
            "returned_at": s.returned_at.isoformat() if s.returned_at else None,
        })

    return {"code": 0, "data": data}


@router.post("/return/{submission_id}")
async def return_submission(
    submission_id: int,
    req: ReturnSubmissionRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    submission.status = "returned"
    submission.return_reason = req.reason or None
    submission.returned_at = datetime.utcnow()
    await db.commit()

    return {"code": 0, "data": {"message": "已打回", "submission_id": submission.id}}


@router.patch("/submissions/{submission_id}/unlate")
async def unlate_submission(
    submission_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")
    if not submission.is_late:
        raise HTTPException(status_code=400, detail="该提交未被标记为迟交")

    submission.is_late = False
    await db.commit()
    return {"code": 0, "data": {"message": "已取消迟交标签"}}


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
        full_score=100,
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
        if "+teacher" not in (report.generated_by or ""):
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


@router.post("/regrade/{submission_id}")
async def regrade_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
    _current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    assignment_result = await db.execute(
        select(Assignment).where(Assignment.id == submission.assignment_id)
    )
    assignment = assignment_result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="作业不存在")

    if assignment.status != "published":
        raise HTTPException(status_code=400, detail="作业未发布")

    report_result = await db.execute(
        select(GradingReport).where(GradingReport.submission_id == submission_id)
    )
    report = report_result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=400, detail="该提交尚未批改，不能重新智能批改")

    generated_by = str(report.generated_by or "").lower()
    if report.review_status == "modified" or "teacher" in generated_by:
        raise HTTPException(status_code=400, detail="该提交已被人工修改，不可重新智能批改")

    task_result = await db.execute(
        select(GradingTask).where(GradingTask.submission_id == submission_id).order_by(GradingTask.id.desc())
    )
    task = task_result.scalars().first()
    if task and task.status in {"pending", "sent"}:
        raise HTTPException(status_code=400, detail="当前已有批改任务在进行")

    images = _load_url_list(submission.images)
    if not images:
        raise HTTPException(status_code=400, detail="提交未包含可批改图片")
    local_paths = [image_url_to_local_path(url) for url in images]
    missing_paths = [path for path in local_paths if not os.path.exists(path)]
    if missing_paths:
        raise HTTPException(status_code=404, detail="原始作业图片缺失，无法重新批改")

    async def _run_regrading():
        try:
            await _execute_grading_for_submission(
                submission_id=submission_id,
                prompt=assignment.grading_prompt,
                answer_json=assignment.reference_answer or "",
                force=True,
            )
        except Exception as e:
            logger.error(f"重新触发批改失败: submission_id={submission_id}, error={e}")

    background_tasks.add_task(_run_regrading)

    return {
        "code": 0,
        "data": {
            "message": "重新批改任务已启动",
            "submission_id": submission_id,
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
        select(GradingTask).where(GradingTask.submission_id == submission_id).order_by(GradingTask.id.desc())
    )
    task = task_result.scalars().first()

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
            "report": (
                _report_to_student_summary(report)
                if report and current_user.role == "student"
                else _report_to_staff_summary(report)
                if report
                else None
            ),
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
        ).order_by(Submission.submitted_at.asc(), Submission.id.asc())
    )
    submissions = sub_result.scalars().all()

    if not submissions:
        return {"code": 0, "data": {"message": "无待批改的提交", "submission_count": 0}}

    batch_started_at = now_cn_naive()
    queued_submission_ids: list[int] = []
    for submission in submissions:
        task = await _prepare_grading_task(
            db,
            submission.id,
            force=True,
            batch_started_at=batch_started_at,
        )
        if task:
            queued_submission_ids.append(submission.id)

    if not queued_submission_ids:
        return {"code": 0, "data": {"message": "无可执行的批改任务", "submission_count": 0}}

    assignment.grading_triggered = True
    assignment.grading_status = "pending"
    grading_prompt = assignment.grading_prompt
    answer_json = assignment.reference_answer or ""
    await db.commit()

    async def _run_grading():
        for submission_id in queued_submission_ids:
            try:
                await _execute_grading_for_submission(
                    submission_id=submission_id,
                    prompt=grading_prompt,
                    answer_json=answer_json,
                )
            except Exception as e:
                logger.error(f"手动触发批改失败: submission_id={submission_id}, error={e}")

    background_tasks.add_task(_run_grading)

    return {
        "code": 0,
        "data": {
            "message": "批改任务已启动",
            "submission_count": len(queued_submission_ids),
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

    latest_batch_started_at = None
    tasks_by_submission_id: dict[int, GradingTask] = {}
    # 批量查询所有 GradingTask，避免 N+1
    sub_ids = [s.id for s in submissions]
    all_task_rows = await db.execute(
        select(GradingTask).where(GradingTask.submission_id.in_(sub_ids)).order_by(GradingTask.id.desc())
    ) if sub_ids else []
    # 每个 submission 取最新的一条 task
    task_map: dict[int, GradingTask] = {}
    for t in all_task_rows.scalars().all() if sub_ids else []:
        if t.submission_id not in task_map:
            task_map[t.submission_id] = t

    for s in submissions:
        task = task_map.get(s.id)
        if not task or not task.sent_at:
            continue

        tasks_by_submission_id[s.id] = task
        if latest_batch_started_at is None or task.sent_at > latest_batch_started_at:
            latest_batch_started_at = task.sent_at

    if latest_batch_started_at is None:
        return {
            "code": 0,
            "data": {
                "total": 0,
                "task_count": 0,
                "pending": 0,
                "processing": 0,
                "graded": 0,
                "failed": 0,
                "done": 0,
            },
        }

    current_batch_tasks = [
        task for task in tasks_by_submission_id.values()
        if task.sent_at == latest_batch_started_at
    ]

    total = len(current_batch_tasks)
    task_count = len(current_batch_tasks)
    pending = 0
    processing = 0
    graded = 0
    failed = 0

    for task in current_batch_tasks:
        if task.status == "pending":
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
            "task_count": task_count,
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
    answer_files: List[str] = []
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
                deadline_dt = parse_cn_datetime_input(item.deadline)
            except ValueError:
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
            answer_files=json.dumps(item.answer_files),
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


@router.get("/grading-overview")
async def grading_overview(
    course_id: Optional[int] = Query(None, description="课程ID，不传则返回所有课程"),
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    course_query = select(Course).order_by(Course.id)
    if course_id:
        course_query = course_query.where(Course.id == course_id)
    courses = (await db.execute(course_query)).scalars().all()
    if not courses:
        return {"code": 0, "data": {"summary": {}, "courses": []}}

    course_ids = [c.id for c in courses]
    sections = (await db.execute(
        select(Section).where(Section.course_id.in_(course_ids)).order_by(Section.id)
    )).scalars().all()
    section_ids = [s.id for s in sections]

    assignments = (await db.execute(
        select(Assignment).where(Assignment.section_id.in_(section_ids)) if section_ids else select(Assignment).where(False)
    )).scalars().all() if section_ids else []
    assignment_map = {a.section_id: a for a in assignments}
    assignment_ids = [a.id for a in assignments]

    course_sections = {}
    for s in sections:
        course_sections.setdefault(s.course_id, []).append(s)

    sub_counts = {aid: {"pending": 0, "graded": 0} for aid in assignment_ids}
    if assignment_ids:
        rows = await db.execute(
            select(Submission.assignment_id, Submission.status, func.count(Submission.id))
            .where(and_(Submission.assignment_id.in_(assignment_ids), Submission.is_latest == True))
            .group_by(Submission.assignment_id, Submission.status)
        )
        for assignment_id, status, cnt in rows:
            sub_counts.setdefault(assignment_id, {"pending": 0, "graded": 0})[status] = cnt

    task_counts = {}
    failed_detail = {}
    if assignment_ids:
        aid_of_sub = {}
        for aid in assignment_ids:
            for (sid,) in await db.execute(
                select(Submission.id).where(and_(Submission.assignment_id == aid, Submission.is_latest == True))
            ):
                aid_of_sub[sid] = aid

        sub_id_list = list(aid_of_sub.keys())
        if sub_id_list:
            tasks = (await db.execute(
                select(GradingTask).where(GradingTask.submission_id.in_(sub_id_list))
            )).scalars().all()

            failed_sids = []
            for t in tasks:
                aid = aid_of_sub.get(t.submission_id)
                if not aid:
                    continue
                task_counts.setdefault(aid, {"pending": 0, "sent": 0, "graded": 0, "failed": 0})
                if t.status in task_counts[aid]:
                    task_counts[aid][t.status] += 1
                if t.status == "failed":
                    failed_sids.append(t.submission_id)
                    failed_detail.setdefault(aid, []).append({
                        "submission_id": t.submission_id,
                        "error": t.error_message or "未知错误",
                        "retry_count": t.retry_count,
                    })

            if failed_sids:
                sub_user_rows = await db.execute(
                    select(Submission.id, Submission.user_id).where(Submission.id.in_(failed_sids))
                )
                sub_to_user = {row[0]: row[1] for row in sub_user_rows}
                uids = list(set(sub_to_user.values()))
                user_rows = await db.execute(select(User.id, User.name).where(User.id.in_(uids)))
                user_map = {row[0]: row[1] for row in user_rows}
                for aid, flist in failed_detail.items():
                    for ft in flist:
                        ft["student_name"] = user_map.get(sub_to_user.get(ft["submission_id"]), "未知")

    course_list = []
    totals = {"total_assignments": 0, "total_submissions": 0, "graded": 0, "pending": 0, "failed": 0, "in_progress": 0}

    for course in courses:
        secs = course_sections.get(course.id, [])
        sections_out = []
        c_as = 0
        c_subs = 0
        c_graded = 0
        c_pending = 0
        c_failed = 0
        c_in_progress = 0

        for sec in secs:
            assignment = assignment_map.get(sec.id)
            if not assignment:
                continue
            c_as += 1
            sc = sub_counts.get(assignment.id, {"pending": 0, "graded": 0})
            tc = task_counts.get(assignment.id, {"pending": 0, "sent": 0, "graded": 0, "failed": 0})
            total = sc["pending"] + sc["graded"]
            graded = sc["graded"]
            pending_subs = sc["pending"]
            failed = tc.get("failed", 0)
            in_progress = tc.get("sent", 0) + tc.get("pending", 0)

            c_subs += total
            c_graded += graded
            c_pending += pending_subs
            c_failed += failed
            c_in_progress += in_progress

            sections_out.append({
                "section_id": sec.id,
                "section_title": sec.title,
                "assignment_id": assignment.id,
                "title": assignment.title,
                "status": assignment.status,
                "grading_mode": assignment.grading_mode,
                "grading_triggered": assignment.grading_triggered,
                "grading_status": assignment.grading_status,
                "total_submissions": total,
                "graded": graded,
                "pending": pending_subs,
                "failed": failed,
                "in_progress": in_progress,
                "failed_tasks": failed_detail.get(assignment.id, []),
            })

        totals["total_assignments"] += c_as
        totals["total_submissions"] += c_subs
        totals["graded"] += c_graded
        totals["pending"] += c_pending
        totals["failed"] += c_failed
        totals["in_progress"] += c_in_progress

        course_list.append({
            "id": course.id,
            "title": course.title,
            "summary": {
                "total_assignments": c_as,
                "total_submissions": c_subs,
                "graded": c_graded,
                "pending": c_pending,
                "failed": c_failed,
                "in_progress": c_in_progress,
            },
            "sections": sections_out if c_as > 0 else [],
        })

    totals["total_courses"] = len(course_list)
    return {"code": 0, "data": {"summary": totals, "courses": course_list}}
