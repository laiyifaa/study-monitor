import hashlib
import hmac
import base64
import time
import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import Course, StudySession, User
from app.utils.jwt_helper import require_role

router = APIRouter(prefix="/api/notify", tags=["通知"])
settings = get_settings()


def _sign_webhook() -> tuple[str, str]:
    """生成钉钉机器人签名"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{settings.DT_ROBOT_SECRET}"
    hmac_code = hmac.new(
        settings.DT_ROBOT_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


async def _send_markdown(webhook_url: str, title: str, text: str):
    """发送 Markdown 格式的钉钉消息"""
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }
    if settings.DT_ROBOT_SECRET:
        ts, sign = _sign_webhook()
        separator = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{separator}timestamp={ts}&sign={sign}"

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook_url, json=payload)


class SendReminderRequest(BaseModel):
    course_id: int
    webhook_url: str = ""


@router.post("/study-reminder")
async def send_study_reminder(
    req: SendReminderRequest,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """向班级群发送学习提醒"""
    # 获取课程信息
    result = await db.execute(select(Course).where(Course.id == req.course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 获取未完成学生
    require_minutes = course.require_minutes or 60
    query = (
        select(
            User.name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
        )
        .join(StudySession, StudySession.user_id == User.id)
        .where(StudySession.course_id == req.course_id)
        .group_by(User.id, User.name)
        .having(func.sum(StudySession.effective_seconds) < require_minutes * 60)
    )
    result = await db.execute(query)
    incomplete = result.all()

    if not incomplete:
        return {"code": 0, "data": {"msg": "所有学生已完成学习"}}

    names = "、".join([r.name for r in incomplete[:10]])
    suffix = "等" if len(incomplete) > 10 else ""
    deadline = str(course.end_date) if course.end_date else "本周末"

    webhook = req.webhook_url or settings.DT_ROBOT_WEBHOOK
    await _send_markdown(
        webhook_url=webhook,
        title=f"学习提醒：{course.title}",
        text=(
            f"### 学习进度提醒\n\n"
            f"**课程**：{course.title}\n\n"
            f"**要求时长**：{require_minutes} 分钟\n\n"
            f"**截止日期**：{deadline}\n\n"
            f"**未完成同学**：{names}{suffix}\n\n"
            f"> 请尽快完成学习任务！"
        ),
    )

    return {"code": 0, "data": {"incomplete_count": len(incomplete)}}


@router.post("/daily-report")
async def send_daily_report(
    req: SendReminderRequest,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """向班级群发送每日学习报告"""
    from datetime import datetime, timedelta

    result = await db.execute(select(Course).where(Course.id == req.course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 今日数据
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    require_minutes = course.require_minutes or 60

    # 学习人数和时长
    active_count = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow)
        )
    )
    total_effective = await db.scalar(
        select(func.sum(StudySession.effective_seconds)).where(
            and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow)
        )
    )
    avg_min = round((total_effective or 0) / 60 / max(active_count or 1, 1), 1)

    # 学习标兵
    top_query = (
        select(User.name, func.sum(StudySession.effective_seconds).label("total"))
        .join(StudySession, StudySession.user_id == User.id)
        .where(and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow))
        .group_by(User.id, User.name)
        .order_by(func.sum(StudySession.effective_seconds).desc())
        .limit(5)
    )
    top_result = await db.execute(top_query)
    top_names = "、".join([r.name for r in top_result.all()])

    webhook = req.webhook_url or settings.DT_ROBOT_WEBHOOK
    await _send_markdown(
        webhook_url=webhook,
        title=f"每日学习报告：{course.title}",
        text=(
            f"### 今日学习报告\n\n"
            f"**课程**：{course.title}\n\n"
            f"- 今日学习人数：{active_count or 0}\n"
            f"- 全班平均时长：{avg_min} 分钟\n"
            f"- 全班总时长：{round((total_effective or 0) / 60, 1)} 分钟\n\n"
            f"**学习标兵**：{top_names}\n"
        ),
    )

    return {"code": 0, "data": {"sent": True}}


@router.get("/export")
async def export_study_data(
    course_id: int = Query(...),
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """导出学习数据为 Excel"""
    from openpyxl import Workbook
    from fastapi.responses import StreamingResponse
    import io

    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 聚合数据
    query = (
        select(
            User.name,
            User.class_name,
            func.sum(StudySession.effective_seconds).label("total_effective"),
            func.max(StudySession.video_progress).label("max_progress"),
            func.max(StudySession.last_heartbeat).label("last_time"),
        )
        .join(StudySession, StudySession.user_id == User.id)
        .where(StudySession.course_id == course_id)
        .group_by(User.id, User.name, User.class_name)
        .order_by(func.sum(StudySession.effective_seconds).desc())
    )
    result = await db.execute(query)
    rows = result.all()

    wb = Workbook()
    ws = wb.active
    ws.title = course.title[:31]
    ws.append(["姓名", "班级", "有效学习(分钟)", "要求时长(分钟)", "完成率", "视频进度(%)", "最后学习时间"])
    for r in rows:
        eff_min = round((r.total_effective or 0) / 60, 1)
        ws.append([
            r.name, r.class_name, eff_min,
            course.require_minutes,
            f"{round(min(eff_min / (course.require_minutes or 60), 1) * 100, 1)}%",
            round(float(r.max_progress or 0), 1),
            str(r.last_time) if r.last_time else "-",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=study_report_{course_id}.xlsx"},
    )
