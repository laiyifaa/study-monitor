from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import StudySession, HeartbeatLog


class StudyEngine:
    """有效学习时长引擎 - 系统核心"""

    HEARTBEAT_INTERVAL = 30      # 心跳间隔(秒)
    HEARTBEAT_TIMEOUT = 90       # 心跳超时(秒)
    PAUSE_TOLERANCE = 300        # 暂停容忍时长(秒)

    @staticmethod
    async def process_heartbeat(
        db: AsyncSession,
        session: StudySession,
        is_playing: bool,
        is_page_visible: bool,
        video_current_time: float,
        action: str = "heartbeat",
    ) -> dict:
        now = datetime.now()
        last = session.last_heartbeat or session.start_time
        gap_seconds = (now - last).total_seconds()

        # 判断本次心跳是否计为有效学习
        is_effective = (
            is_playing
            and is_page_visible
            and gap_seconds <= StudyEngine.HEARTBEAT_TIMEOUT
        )

        # 计算有效增量
        if is_effective:
            increment = min(gap_seconds, StudyEngine.HEARTBEAT_INTERVAL + 5)
            session.effective_seconds = int(session.effective_seconds + increment)

        # 更新视频进度（去重：只升不降）
        if video_current_time > float(session.video_progress):
            session.video_progress = video_current_time

        # 更新最后心跳时间
        session.last_heartbeat = now

        # 记录心跳日志
        log = HeartbeatLog(
            session_id=session.session_id,
            user_id=session.user_id,
            timestamp=now,
            is_playing=is_playing,
            is_page_visible=is_page_visible,
            video_current_time=video_current_time,
            action=action,
        )
        db.add(log)
        await db.flush()

        return {
            "is_effective": is_effective,
            "effective_seconds": session.effective_seconds,
            "effective_minutes": round(session.effective_seconds / 60, 1),
            "video_progress": round(float(session.video_progress), 1),
            "session_id": session.session_id,
        }

    @staticmethod
    async def get_active_session(
        db: AsyncSession, user_id: int, course_id: int
    ) -> StudySession | None:
        result = await db.execute(
            select(StudySession).where(
                and_(
                    StudySession.user_id == user_id,
                    StudySession.course_id == course_id,
                    StudySession.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def end_active_sessions(db: AsyncSession, user_id: int, course_id: int):
        """结束该用户该课程的所有活跃会话（防多开）"""
        result = await db.execute(
            select(StudySession).where(
                and_(
                    StudySession.user_id == user_id,
                    StudySession.course_id == course_id,
                    StudySession.is_active == True,
                )
            )
        )
        sessions = result.scalars().all()
        now = datetime.now()
        for s in sessions:
            s.is_active = False
            s.end_time = now
        await db.flush()
