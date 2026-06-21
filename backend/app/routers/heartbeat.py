"""
心跳模块 (heartbeat)

功能说明：
    实现学习会话的完整生命周期管理：开始学习 → 心跳上报 → 结束学习。
    这是整个"防刷课"系统的核心入口——通过心跳机制持续采集学生的学习行为数据，
    由 StudyEngine 计算有效学习时长（非简单地累计时间，而是综合判断视频播放状态、
    页面可见性、鼠标活动等多维信号）。

在系统中的角色：
    学习数据采集层——前端视频播放器每30秒上报一次心跳，本模块接收后委托
    StudyEngine 进行有效时长判定和累积，是统计模块的数据源头。

API 列表：
    POST /api/heartbeat/start  — 开始学习（创建会话）
    POST /api/heartbeat/beat   — 心跳上报（每30秒调用一次）
    POST /api/heartbeat/end    — 结束学习（关闭会话）

安全说明：
    - Redis 限流：每用户每课程每分钟最多5次心跳，防止脚本高频刷时长
    - 会话绑定：心跳必须关联到活跃会话，无会话则拒绝
    - 防多开：开始新会话时自动结束同一课程的旧会话
"""

import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database_redis import get_redis
from app.models.models import StudySession, User, Section
from app.services.study_engine import StudyEngine
from app.utils.jwt_helper import get_current_user

router = APIRouter(prefix="/api/heartbeat", tags=["心跳"])


class StartRequest(BaseModel):
    """开始学习请求体"""
    course_id: int          # 要学习的课程ID
    section_id: int | None = None  # 要学习的小节ID（v3.0新增，可选兼容旧数据）


class BeatRequest(BaseModel):
    """
    心跳上报请求体（beat 和 end 共用）

    字段说明：
        is_playing:       视频是否正在播放（暂停状态不计有效时长）
        is_page_visible:  学习页面是否在前台可见（切后台不计有效时长）
        video_current_time: 当前视频播放进度（秒），用于检测是否在快进刷进度
        action:           动作类型，默认 "heartbeat"，结束时传 "end"
    """
    course_id: int
    section_id: int | None = None  # 小节ID（v3.0新增）
    is_playing: bool = True
    is_page_visible: bool = True
    video_current_time: float = 0
    action: str = "heartbeat"


@router.post("/start")
async def start_session(req: StartRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    开始学习 — 创建一个新的学习会话

    请求参数：
        body.course_id (int):    要学习的课程ID
        body.section_id (int):   要学习的小节ID（可选）

    返回格式：
        code=0, data.session_id: 新创建的会话唯一标识

    核心业务逻辑：
        1. 先结束该用户该课程的旧活跃会话（防止同一课程同时开多个会话刷时长）
        2. 生成唯一的 session_id（格式：用户ID_课程ID_时间戳）
        3. 创建 StudySession 记录写入数据库（含 section_id）

    权限要求：已登录用户
    """
    # 开播时间检查：如果小节设置了 open_time 且当前时间未到，拒绝开始学习
    if req.section_id:
        section_result = await db.execute(select(Section).where(Section.id == req.section_id))
        section = section_result.scalar_one_or_none()
        if section and section.open_time and datetime.now() < section.open_time:
            return {
                "code": 1,
                "msg": f"该课程尚未开播，开播时间：{section.open_time.strftime('%Y-%m-%d %H:%M')}",
                "data": {"open_time": section.open_time.isoformat()},
            }

    # 先结束已有的活跃会话（防多开）
    await StudyEngine.end_active_sessions(db, user.id, req.course_id)

    session_id = f"{user.id}_{req.course_id}_{int(time.time())}"
    session = StudySession(
        user_id=user.id,
        course_id=req.course_id,
        section_id=req.section_id,  # v3.0: 关联到小节
        session_id=session_id,
        start_time=datetime.now(),
        last_heartbeat=datetime.now(),
        effective_seconds=0,
        video_progress=0,
        is_active=True,
    )
    db.add(session)
    await db.commit()

    return {"code": 0, "data": {"session_id": session_id}}


@router.post("/beat")
async def heartbeat(req: BeatRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    心跳上报 — 前端视频播放器每30秒调用一次

    请求参数：
        body.course_id (int):            课程ID
        body.is_playing (bool):          视频是否在播放，默认 True
        body.is_page_visible (bool):     页面是否可见，默认 True
        body.video_current_time (float): 当前视频播放位置（秒），默认 0
        body.action (str):               动作类型，默认 "heartbeat"

    返回格式：
        code=0, data: StudyEngine 处理后的结果（含本次有效秒数、累计有效时长等）
        429: 心跳过于频繁（触发Redis限流）
        404: 无活跃会话

    核心业务逻辑：
        1. Redis 限流检查（每用户每课程每分钟最多5次）
        2. 查找当前活跃会话
        3. 委托 StudyEngine.process_heartbeat 计算本次有效时长
           （综合判断播放状态、页面可见性、快进检测等多维信号）

    权限要求：已登录用户

    安全说明：
        【限流防护】使用 Redis INCR + EXPIRE 实现滑动窗口限流，
        每用户每课程每分钟上限5次心跳（正常30秒一次=2次/分钟，
        留有余量应对网络抖动导致的重试，但足以拦截恶意脚本刷时长）
        【会话校验】必须存在活跃会话才能上报心跳，防止绕过 start 直接 beat
    """
    # 【安全校验】Redis 限流：每人每课程每分钟最多5次心跳
    # ——正常心跳30秒一次约2次/分钟，5次上限留有余量但可拦截脚本刷时长
    redis = await get_redis()
    rate_key = f"heartbeat:rate:{user.id}:{req.course_id}"
    count = await redis.incr(rate_key)
    if count == 1:
        # 首次请求时设置60秒过期，形成固定窗口限流
        await redis.expire(rate_key, 60)
    if count > 5:
        # 超过频率限制，直接拒绝并返回429
        raise HTTPException(status_code=429, detail="心跳上报过于频繁，请稍后再试")

    # 查找该用户该课程的活跃会话
    session = await StudyEngine.get_active_session(db, user.id, req.course_id)
    if not session:
        # 没有活跃会话说明可能 session 过期或未调用 start
        raise HTTPException(status_code=404, detail="没有活跃的学习会话，请先开始学习")

    # 委托 StudyEngine 核心引擎处理心跳，计算有效学习时长
    # Engine 会综合判断：视频是否播放、页面是否可见、是否有快进跳转等
    result = await StudyEngine.process_heartbeat(
        db=db,
        session=session,
        is_playing=req.is_playing,
        is_page_visible=req.is_page_visible,
        video_current_time=req.video_current_time,
        action=req.action,
    )
    await db.commit()
    return {"code": 0, "data": result}


@router.post("/end")
async def end_session(req: BeatRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    结束学习 — 关闭活跃学习会话

    请求参数：
        body.course_id (int):            课程ID
        body.is_playing (bool):          结束时的播放状态
        body.is_page_visible (bool):     结束时的页面可见状态
        body.video_current_time (float): 结束时的视频进度
        body.action (str):               固定传 "end"

    返回格式：
        code=0, data.status: "ok"

    核心业务逻辑：
        1. 查找活跃会话（无会话也返回成功，幂等设计）
        2. 做最后一次心跳计算（确保最后一段有效时长被记录）
        3. 标记会话为非活跃、记录结束时间

    权限要求：已登录用户

    安全说明：
        - 幂等设计：重复调用 end 不会报错，避免前端网络抖动导致重复请求时出问题
    """
    session = await StudyEngine.get_active_session(db, user.id, req.course_id)
    if session:
        # 结束前做最后一次心跳计算，确保最后一段学习时长被记录
        await StudyEngine.process_heartbeat(
            db=db,
            session=session,
            is_playing=req.is_playing,
            is_page_visible=req.is_page_visible,
            video_current_time=req.video_current_time,
            action="end",  # 显式标记为结束动作，Engine可做特殊处理
        )
        session.is_active = False  # 标记会话已结束
        session.end_time = datetime.now()  # 记录实际结束时间
        await db.commit()

    return {"code": 0, "data": {"status": "ok"}}
