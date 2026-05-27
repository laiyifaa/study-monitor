import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import StudySession, User
from app.services.study_engine import StudyEngine
from app.utils.jwt_helper import get_current_user

router = APIRouter(prefix="/api/heartbeat", tags=["心跳"])


class StartRequest(BaseModel):
    course_id: int


class BeatRequest(BaseModel):
    course_id: int
    is_playing: bool = True
    is_page_visible: bool = True
    video_current_time: float = 0
    action: str = "heartbeat"


@router.post("/start")
async def start_session(req: StartRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """学生开始学习：创建学习会话"""
    # 先结束已有的活跃会话（防多开）
    await StudyEngine.end_active_sessions(db, user.id, req.course_id)

    session_id = f"{user.id}_{req.course_id}_{int(time.time())}"
    session = StudySession(
        user_id=user.id,
        course_id=req.course_id,
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
    """心跳上报：每30秒调用"""
    session = await StudyEngine.get_active_session(db, user.id, req.course_id)
    if not session:
        raise HTTPException(status_code=404, detail="没有活跃的学习会话，请先开始学习")

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
    """学生退出学习：结束会话"""
    session = await StudyEngine.get_active_session(db, user.id, req.course_id)
    if session:
        await StudyEngine.process_heartbeat(
            db=db,
            session=session,
            is_playing=req.is_playing,
            is_page_visible=req.is_page_visible,
            video_current_time=req.video_current_time,
            action="end",
        )
        session.is_active = False
        session.end_time = datetime.now()
        await db.commit()

    return {"code": 0, "data": {"status": "ok"}}
