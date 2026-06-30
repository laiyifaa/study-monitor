"""
智能体接口模块 (agent)

功能说明：
    为 AI 智能体提供统一入口的业务 API，所有接口支持 API Key 认证。
    本模块不重复实现业务逻辑，而是将智能体常用操作汇总到 /api/agent/ 前缀下，
    方便智能体发现和调用，也便于权限审计。

    所有接口要求 teacher 或 admin 角色，智能体通过 X-API-Key 请求头认证。

在系统中的角色：
    智能体网关 — 汇总智能体最常用的操作，提供清晰的 API 文档。

API 列表：
    学生管理：
        GET    /api/agent/students              — 获取学生列表（含班级信息）
        POST   /api/agent/students              — 创建学生
        PUT    /api/agent/students/{user_id}     — 更新学生信息
        DELETE /api/agent/students/{user_id}     — 删除学生（仅 admin API Key）

    课程与作业：
        GET    /api/agent/courses               — 获取课程列表
        GET    /api/agent/courses/{course_id}/assignments — 获取课程作业（含参考答案）

    学习数据：
        GET    /api/agent/progress/{course_id}   — 获取课程下学生的学习进度
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models.models import User, Course, Assignment, Section, StudySession
from app.routers.auth import hash_password
from app.utils.jwt_helper import require_role

router = APIRouter(prefix="/api/agent", tags=["智能体接口"])


# ============================================================
# 学生管理
# ============================================================

@router.get("/students")
async def agent_list_students(
    class_name: Optional[str] = Query(None, description="按班级筛选"),
    search: Optional[str] = Query(None, description="按姓名搜索"),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取学生列表（智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    query = select(User).where(User.role == "student").order_by(User.id)

    if class_name:
        query = query.where(User.class_name == class_name)
    if search:
        query = query.where(User.name.like(f"%{search}%"))

    result = await db.execute(query)
    students = result.scalars().all()

    return {
        "code": 0,
        "data": [
            {
                "id": s.id,
                "name": s.name,
                "real_name": s.real_name or "",
                "class_name": s.class_name,
                "phone": s.phone or "",
            }
            for s in students
        ],
    }


class AgentCreateStudentRequest(BaseModel):
    name: str
    class_name: str = ""
    password: str = "123456"


@router.post("/students")
async def agent_create_student(
    req: AgentCreateStudentRequest,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    创建学生（智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    from datetime import datetime

    if not req.name.strip():
        return {"code": 1, "msg": "学生姓名不能为空"}

    # 检查同名
    result = await db.execute(select(User).where(User.name == req.name.strip()))
    if result.scalar_one_or_none():
        return {"code": 1, "msg": f"学生 '{req.name}' 已存在"}

    student = User(
        name=req.name.strip(),
        role="student",
        class_name=req.class_name.strip(),
        dingtalk_user_id=f"local_{req.name.strip()}_{int(datetime.now().timestamp())}",
        password_hash=hash_password(req.password),
    )
    db.add(student)
    await db.flush()
    await db.refresh(student)
    await db.commit()

    return {
        "code": 0,
        "msg": "学生创建成功",
        "data": {
            "id": student.id,
            "name": student.name,
            "class_name": student.class_name,
        },
    }


class AgentUpdateStudentRequest(BaseModel):
    name: Optional[str] = None
    class_name: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None


@router.put("/students/{user_id}")
async def agent_update_student(
    user_id: int,
    req: AgentUpdateStudentRequest,
    current_user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新学生信息（智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    result = await db.execute(select(User).where(User.id == user_id, User.role == "student"))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(student, key, value)

    await db.commit()
    await db.refresh(student)

    return {
        "code": 0,
        "msg": "学生信息更新成功",
        "data": {
            "id": student.id,
            "name": student.name,
            "class_name": student.class_name,
        },
    }


@router.delete("/students/{user_id}")
async def agent_delete_student(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除学生（智能体专用，仅 admin）

    权限要求：【仅 admin】，支持 X-API-Key 认证
    """
    result = await db.execute(select(User).where(User.id == user_id, User.role == "student"))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    await db.delete(student)
    await db.commit()
    return {"code": 0, "msg": f"学生 '{student.name}' 已删除"}


# ============================================================
# 课程与作业
# ============================================================

@router.get("/courses")
async def agent_list_courses(
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程列表（智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    result = await db.execute(
        select(Course).where(Course.status == "active").order_by(Course.id)
    )
    courses = result.scalars().all()

    data = []
    for c in courses:
        # 获取小节数
        section_count = await db.scalar(
            select(func.count()).select_from(Section).where(Section.course_id == c.id)
        )
        data.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "require_minutes": c.require_minutes,
            "section_count": section_count or 0,
            "status": c.status,
        })

    return {"code": 0, "data": data}


@router.get("/courses/{course_id}/assignments")
async def agent_get_course_assignments(
    course_id: int,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程作业（含参考答案，智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    import json

    result = await db.execute(
        select(Assignment).where(Assignment.course_id == course_id)
    )
    assignments = result.scalars().all()

    data = []
    for a in assignments:
        data.append({
            "id": a.id,
            "section_id": a.section_id,
            "title": a.title,
            "description": a.description,
            "question_files": json.loads(a.question_files),
            "grading_prompt": a.grading_prompt,
            "reference_answer": a.reference_answer or "",
            "deadline": a.deadline.isoformat() if a.deadline else None,
            "status": a.status,
            "grading_mode": a.grading_mode,
        })

    return {"code": 0, "data": data}


# ============================================================
# 学习进度
# ============================================================

@router.get("/progress/{course_id}")
async def agent_get_course_progress(
    course_id: int,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课程下所有学生的学习进度（智能体专用）

    权限要求：【teacher / admin】，支持 X-API-Key 认证
    """
    # 获取课程信息
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 获取所有学生
    students_result = await db.execute(
        select(User).where(User.role == "student").order_by(User.class_name, User.name)
    )
    students = students_result.scalars().all()

    data = []
    for s in students:
        # 该学生在这门课的总有效学习时长
        total_seconds = await db.scalar(
            select(func.coalesce(func.sum(StudySession.effective_seconds), 0)).where(
                and_(
                    StudySession.user_id == s.id,
                    StudySession.course_id == course_id,
                )
            )
        )
        effective_minutes = round((total_seconds or 0) / 60, 1)
        require_minutes = course.require_minutes or 0
        completion_rate = min(effective_minutes / require_minutes, 1.0) if require_minutes > 0 else 0

        data.append({
            "user_id": s.id,
            "name": s.name,
            "class_name": s.class_name,
            "effective_minutes": effective_minutes,
            "require_minutes": require_minutes,
            "completion_rate": round(completion_rate, 4),
            "is_completed": completion_rate >= 1.0,
        })

    return {
        "code": 0,
        "data": {
            "course_id": course_id,
            "course_title": course.title,
            "require_minutes": course.require_minutes,
            "total_students": len(data),
            "completed_students": sum(1 for d in data if d["is_completed"]),
            "students": data,
        },
    }
