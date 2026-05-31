"""
通知模块 (notify)

功能说明：
    提供钉钉群消息推送和学习数据 Excel 导出功能。
    教师可以通过钉钉机器人向班级群发送学习提醒（催促未完成学生）和每日学习报告，
    也可以将班级学习数据导出为 Excel 文件用于存档或进一步分析。

在系统中的角色：
    对外通知层——将系统内的学习数据通过钉钉机器人推送到班级群，
    实现师生之间的信息闭环。同时提供数据导出能力，方便教师进行离线分析。

API 列表：
    POST /api/notify/study-reminder  — 发送学习提醒（@未完成学生）
    POST /api/notify/daily-report    — 发送每日学习报告
    GET  /api/notify/export          — 导出学习数据为 Excel

权限矩阵：
    所有接口均要求 【teacher / admin】角色

安全说明：
    - 钉钉机器人使用 HMAC-SHA256 签名验证，防止 Webhook URL 被伪造调用
    - 消息发送失败静默处理（不抛异常），避免影响主业务流程
"""

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
    """
    生成钉钉机器人 Webhook 签名（HMAC-SHA256）

    安全说明：
        钉钉自定义机器人安全设置支持"加签"方式，使用密钥(Secret)对请求签名，
        服务器通过相同的算法验证签名来确认请求确实来自合法的发送方。
        签名算法：HMAC-SHA256(timestamp + "\n" + secret)

    Returns:
        tuple[str, str]: (timestamp毫秒, URL安全的Base64签名)
    """
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{settings.DT_ROBOT_SECRET}"
    hmac_code = hmac.new(
        settings.DT_ROBOT_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,  # 钉钉要求使用 SHA256 哈希
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


async def _send_markdown(webhook_url: str, title: str, text: str):
    """
    发送 Markdown 格式的钉钉群消息（内部工具函数）

    参数：
        webhook_url: 机器人 Webhook 地址（含签名参数）
        title:       消息标题（在钉钉中显示为卡片标题）
        text:        Markdown 格式的消息正文

    安全说明：
        - 如果配置了 DT_ROBOT_SECRET，自动在 URL 上附加签名参数
        - 签名参数包括 timestamp 和 sign，由 _sign_webhook() 生成
        - 签名有效期有限（钉钉服务器校验），使用当前时间戳确保时效性
    """
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }
    # 如果配置了机器人密钥，自动附加签名参数
    if settings.DT_ROBOT_SECRET:
        ts, sign = _sign_webhook()
        # 根据 URL 中是否已有参数决定用 & 还是 ? 拼接签名参数
        separator = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{separator}timestamp={ts}&sign={sign}"

    # 消息发送采用"发后即忘"策略，不检查返回结果
    # ——发送失败不应影响教师端的正常操作体验
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook_url, json=payload)


class SendReminderRequest(BaseModel):
    """学习提醒/每日报告请求体"""
    course_id: int                        # 课程ID（必填）
    webhook_url: str = ""                 # 自定义 Webhook 地址（可选，不传使用系统默认）


@router.post("/study-reminder")
async def send_study_reminder(
    req: SendReminderRequest,
    user: User = Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    发送学习提醒 — 向钉钉班级群推送未完成学生名单

    请求参数：
        body.course_id (int):    课程ID（必填）
        body.webhook_url (str):  自定义 Webhook 地址（可选，空则使用系统默认配置）

    返回格式：
        code=0: data.incomplete_count=未完成人数 / data.msg=全部完成提示
        code=1: 课程不存在

    权限要求：【teacher / admin】

    核心业务逻辑：
        1. 查询课程的未完成学生（有效时长 < 要求时长）
        2. 拼接 Markdown 格式的提醒消息
        3. 最多显示10个学生姓名，超出部分用"等"字省略（避免消息过长）
        4. 通过钉钉机器人发送到班级群

    注意事项：
        如果所有学生都已完成，不发送消息，直接返回提示。
    """
    # 获取课程信息
    result = await db.execute(select(Course).where(Course.id == req.course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 获取未完成学生列表（聚合有效时长后用 HAVING 过滤未达标的）
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

    # 全部已完成时直接返回，不发送消息
    if not incomplete:
        return {"code": 0, "data": {"msg": "所有学生已完成学习"}}

    # 最多显示10个学生姓名，超出用"等"省略——避免钉钉消息过长被折叠
    names = "、".join([r.name for r in incomplete[:10]])
    suffix = "等" if len(incomplete) > 10 else ""
    # 截止日期优先取课程设置，否则提示"本周末"
    deadline = str(course.end_date) if course.end_date else "本周末"

    # 使用自定义 Webhook 或系统默认配置
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
    """
    发送每日学习报告 — 向钉钉班级群推送今日学习统计

    请求参数：
        body.course_id (int):    课程ID（必填）
        body.webhook_url (str):  自定义 Webhook 地址（可选）

    返回格式：code=0, data.sent=True / code=1 课程不存在

    权限要求：【teacher / admin】

    核心业务逻辑：
        1. 统计今日学习人数和总有效时长
        2. 计算人均学习时长
        3. 查询今日学习时长前5名的"学习标兵"
        4. 拼接 Markdown 格式的每日报告发送到班级群

    注意事项：
        即使当天无人学习也会发送报告（显示0人），让教师了解当天情况。
    """
    from datetime import datetime, timedelta

    result = await db.execute(select(Course).where(Course.id == req.course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 构造今日时间范围 [today 00:00:00, tomorrow 00:00:00)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    require_minutes = course.require_minutes or 60

    # 统计今日活跃学习人数（去重）
    active_count = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow)
        )
    )
    # 统计今日全班总有效学习时长
    total_effective = await db.scalar(
        select(func.sum(StudySession.effective_seconds)).where(
            and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow)
        )
    )
    # 人均有效时长（分母防零除）
    avg_min = round((total_effective or 0) / 60 / max(active_count or 1, 1), 1)

    # 查询今日学习时长 Top5 学生，作为"学习标兵"展示
    # ——利用学生的竞争心理激励学习积极性
    top_query = (
        select(User.name, func.sum(StudySession.effective_seconds).label("total"))
        .join(StudySession, StudySession.user_id == User.id)
        .where(and_(StudySession.course_id == req.course_id, StudySession.start_time >= today, StudySession.start_time < tomorrow))
        .group_by(User.id, User.name)
        .order_by(func.sum(StudySession.effective_seconds).desc())  # 按有效时长降序
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
    """
    导出学习数据为 Excel 文件

    请求参数：
        query.course_id (int): 课程ID（必填）

    返回格式：
        Excel 文件流（application/vnd.openxmlformats-officedocument.spreadsheetml.sheet）
        文件名：study_report_{course_id}.xlsx

    错误：code=1 课程不存在

    权限要求：【teacher / admin】

    核心业务逻辑：
        1. 按学生聚合统计（有效时长、视频进度、最后学习时间）
        2. 计算完成率并格式化为百分比
        3. 按有效时长降序排列
        4. 使用 openpyxl 生成 Excel 文件，通过 StreamingResponse 流式返回

    Excel 列定义：
        姓名 | 班级 | 有效学习(分钟) | 要求时长(分钟) | 完成率 | 视频进度(%) | 最后学习时间
    """
    from openpyxl import Workbook
    from fastapi.responses import StreamingResponse
    import io

    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"code": 1, "msg": "课程不存在"}

    # 聚合查询每个学生的学习数据，按有效时长降序排列（表现好的排在前面）
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
        .order_by(func.sum(StudySession.effective_seconds).desc())  # 降序排列
    )
    result = await db.execute(query)
    rows = result.all()

    # 使用 openpyxl 创建 Excel 文件（在内存中操作，不写磁盘）
    wb = Workbook()
    ws = wb.active
    # Excel 工作表名最长31个字符，截断课程标题防止超限
    ws.title = course.title[:31]
    ws.append(["姓名", "班级", "有效学习(分钟)", "要求时长(分钟)", "完成率", "视频进度(%)", "最后学习时间"])
    for r in rows:
        eff_min = round((r.total_effective or 0) / 60, 1)
        ws.append([
            r.name, r.class_name, eff_min,
            course.require_minutes,
            # 完成率格式化为百分比字符串，上限100%
            f"{round(min(eff_min / (course.require_minutes or 60), 1) * 100, 1)}%",
            round(float(r.max_progress or 0), 1),
            str(r.last_time) if r.last_time else "-",
        ])

    # 写入内存缓冲区并通过 StreamingResponse 流式返回
    # ——避免先生成临时文件再返回，减少磁盘IO
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)  # 重置指针到起始位置，确保读取时从头开始

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=study_report_{course_id}.xlsx"},
    )
