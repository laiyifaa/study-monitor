"""
课程管理模块 (course)

功能说明：
    提供课程的完整 CRUD 操作和视频文件上传服务。
    课程支持两种视频来源模式：URL外链（如悟空播放器链接）和本地文件上传。
    教师可以创建、编辑课程，管理员可以删除课程。

在系统中的角色：
    内容管理层——管理学习资源，是心跳模块（学生学课程）和统计模块（查看学习数据）的基础。

API 列表：
    POST   /api/courses                    — 创建课程
    GET    /api/courses                    — 课程列表（支持状态过滤）
    GET    /api/courses/{course_id}        — 课程详情
    PUT    /api/courses/{course_id}        — 更新课程
    DELETE /api/courses/{course_id}        — 删除课程（仅管理员）
    POST   /api/courses/{course_id}/upload-video — 上传视频文件
    GET    /api/courses/video-file/{filename}   — 获取本地视频文件

权限矩阵：
    创建课程：teacher / admin
    编辑课程：teacher / admin
    删除课程：admin（仅管理员可删除，防止误删影响学生数据）
    查看课程：所有人（无需登录）
    上传视频：teacher / admin
"""

import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse

from app.database import get_db
from app.models.models import Course, User
from app.utils.jwt_helper import get_current_user, require_role

router = APIRouter(prefix="/api/courses", tags=["课程管理"])

# 视频文件存储目录（项目根目录/uploads/videos）
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 【安全配置】允许上传的视频格式白名单——防止上传恶意文件伪装成视频
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}
# 【安全配置】文件大小上限500MB——防止磁盘被大文件撑爆
MAX_FILE_SIZE = 500 * 1024 * 1024


class CourseCreate(BaseModel):
    """创建课程请求体"""
    title: str                       # 课程标题（必填）
    description: str = ""             # 课程描述
    video_type: str = "url"           # 视频类型："url" 外链 或 "local" 本地文件
    video_url: str = ""               # 视频URL（video_type=url时填写）
    duration_seconds: int = 0         # 视频总时长（秒）
    require_minutes: int = 60         # 要求学习时长（分钟），默认60分钟
    start_date: datetime | None = None  # 学习开始日期
    end_date: datetime | None = None    # 学习截止日期


class CourseUpdate(BaseModel):
    """
    更新课程请求体（所有字段可选，只更新传入的字段）
    使用 exclude_unset=True 仅处理客户端实际传了的字段
    """
    title: str | None = None
    description: str | None = None
    video_type: str | None = None
    video_url: str | None = None
    duration_seconds: int | None = None
    require_minutes: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None


def _course_to_dict(c):
    """
    统一的课程序列化函数
    ——将 Course ORM 对象转换为前端可用的字典格式，兼容新旧数据结构

    兼容性说明：
        旧版数据使用 wukong_url 字段存储视频链接，新版统一使用 video_url。
        这里优先取 video_url，fallback 到 wukong_url，确保旧数据不会丢失。
    """
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "video_type": c.video_type or "url",
        # 兼容旧数据：优先取 video_url，回退到 wukong_url
        "video_url": c.video_url or c.wukong_url or "",
        "duration_seconds": c.duration_seconds,
        "require_minutes": c.require_minutes,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "status": c.status,
        "teacher_id": c.teacher_id,
    }


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
        body.video_type (str):          视频类型，"url" 或 "local"，默认 "url"
        body.video_url (str):          视频链接
        body.duration_seconds (int):    视频总时长（秒）
        body.require_minutes (int):     要求学习时长（分钟），默认60
        body.start_date (datetime):     学习开始日期
        body.end_date (datetime):       学习截止日期

    返回格式：code=0, data.id/title

    权限要求：【teacher / admin】只有教师和管理员可以创建课程

    安全说明：
        - require_role 依赖注入会在请求到达处理器前校验用户角色
        - 新课程默认状态为 "active"，创建后立即可见
    """
    course = Course(
        title=req.title,
        description=req.description,
        video_type=req.video_type,
        video_url=req.video_url,
        # 向后兼容：如果是 URL 类型，同时写入 wukong_url 字段
        wukong_url=req.video_url if req.video_type == "url" else "",
        duration_seconds=req.duration_seconds,
        teacher_id=user.id,  # 记录创建者（教师ID），用于权限追溯
        require_minutes=req.require_minutes,
        start_date=req.start_date,
        end_date=req.end_date,
        status="active",
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)  # 刷新以获取数据库生成的自增ID
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

    返回格式：code=0, data: 课程对象数组

    权限要求：无需登录（所有人可查看课程列表）

    业务逻辑：
        默认只返回 active 状态的课程，传 "all" 则返回所有状态（含已下架课程）
    """
    query = select(Course).order_by(Course.created_at.desc())
    if status != "all":
        # 非全部时按状态过滤，默认只展示活跃课程
        query = query.where(Course.status == status)
    result = await db.execute(query)
    courses = result.scalars().all()
    return {"code": 0, "data": [_course_to_dict(c) for c in courses]}


@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    """
    课程详情

    请求参数：
        path.course_id (int): 课程ID

    返回格式：code=0, data: 课程对象
    错误：404 课程不存在

    权限要求：无需登录
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return {"code": 0, "data": _course_to_dict(course)}


@router.put("/{course_id}")
async def update_course(
    course_id: int,
    req: CourseUpdate,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    更新课程（部分更新，只修改传入的字段）

    请求参数：
        path.course_id (int): 课程ID
        body: 要更新的字段（均为可选）

    返回格式：code=0, data.id
    错误：404 课程不存在

    权限要求：【teacher / admin】

    业务逻辑：
        使用 model_dump(exclude_unset=True) 只更新客户端实际传了的字段，
        未传的字段保持原值不变。更新视频URL时同步 wukong_url 保证兼容性。
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 只更新客户端实际传了的字段（exclude_unset=True 排除未设置的字段）
    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(course, key, value)
    # 【兼容性处理】同步更新 wukong_url 字段，确保旧版代码也能读到新视频链接
    if req.video_url is not None and (req.video_type or course.video_type) == "url":
        course.wukong_url = req.video_url
    await db.commit()
    return {"code": 0, "data": {"id": course.id}}


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    删除课程

    请求参数：
        path.course_id (int): 课程ID

    返回格式：code=0, data.id
    错误：404 课程不存在

    权限要求：【仅 admin】删除操作不可逆，限制为最高权限角色

    业务逻辑：
        删除课程时同步删除关联的本地视频文件，避免磁盘空间浪费。
        注意：不级联删除学生的 StudySession 记录（保留历史学习数据）。
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    # 删除本地视频文件（仅当视频类型为 local 时）
    if course.video_type == "local" and course.video_url:
        local_path = os.path.join(UPLOAD_DIR, course.video_url)
        if os.path.exists(local_path):
            os.remove(local_path)
    await db.delete(course)
    await db.commit()
    return {"code": 0, "data": {"id": course_id}}


@router.post("/{course_id}/upload-video")
async def upload_video(
    course_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    上传课程视频文件

    请求参数：
        path.course_id (int): 课程ID
        form.file (UploadFile): 视频文件

    返回格式：code=0, data: video_type 和 video_url
    错误：404 课程不存在 / 400 格式不支持或文件过大

    权限要求：【teacher / admin】

    安全说明：
        【格式白名单】只允许 mp4/webm/ogg/mov 格式，防止上传恶意脚本文件
        【大小限制】500MB上限，防止磁盘被大文件占满
        【文件名随机化】使用 UUID 生成文件名，防止路径遍历攻击和文件名冲突

    业务逻辑：
        1. 校验课程存在性
        2. 校验文件格式和大小
        3. 删除旧视频（如果有的话）
        4. 保存新文件并更新课程记录
    """
    # 校验课程是否存在
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 【安全校验】检查文件扩展名是否在白名单中
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式，允许: {', '.join(ALLOWED_EXTENSIONS)}")

    # 【安全校验】检查文件大小是否超过限制
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="视频文件不能超过500MB")

    # 如果课程已有本地视频，先删除旧文件避免磁盘空间浪费
    if course.video_type == "local" and course.video_url:
        old_path = os.path.join(UPLOAD_DIR, course.video_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    # 【安全】使用 课程ID_UUID随机数.扩展名 作为文件名，防止路径遍历和文件名冲突
    filename = f"{course_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # 更新课程为本地视频类型
    course.video_type = "local"
    course.video_url = filename
    course.wukong_url = ""  # 切换到本地模式，清空外链
    await db.commit()

    return {"code": 0, "data": {"video_type": "local", "video_url": filename}}


@router.get("/video-file/{filename}")
async def serve_video(filename: str):
    """
    提供本地视频文件流式传输

    请求参数：
        path.filename (str): 视频文件名

    返回格式：video/mp4 文件流
    错误：404 文件不存在

    权限要求：无（视频本身无敏感信息，且前端HTML5 video标签需要直接访问）

    安全说明：
        路由设计上放在 /video-file/ 而非 /{course_id}/video，
        避免 FastAPI 路由解析时与课程详情路由 /{course_id} 冲突
    """
    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="视频文件不存在")
    # 使用 FileResponse 流式返回，支持浏览器范围请求（seek/拖动进度条）
    return FileResponse(filepath, media_type="video/mp4")
