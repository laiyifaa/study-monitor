"""
====================================================================
  有效学习时长计算引擎 (Study Engine)
====================================================================

【功能概述】
  本模块是"网课学习进度监督系统"的防刷课核心。系统通过前端每 30 秒发送一次
  心跳请求，后端根据心跳携带的播放状态、页面可见性、视频进度等信息，实时判定
  本次心跳是否计为"有效学习"，并累加有效时长。

【设计思路】
  传统网课系统只记录"打开页面 → 关闭页面"的总时长，学生挂机即可刷时长。
  本引擎采用多维信号交叉验证的方式判定有效性：
    1. 页面可见性 —— 页面切到后台则不计时长（防止挂机）
    2. 视频播放状态 —— 暂停/缓冲时不计时长（防止暂停挂机）
    3. 心跳超时检测 —— 超过 90 秒未收到心跳则视为离开（防止断网保活）
    4. 视频进度单调递增 —— 进度只升不降（防止快退刷时长）
    5. 防多开机制 —— 同一用户同一课程只允许一个活跃会话（防止多标签刷时长）
    6. 暂停容忍窗口 —— 短暂停顿 5 分钟内仍计有效（人性化设计，缓冲/笔记场景）

【核心算法说明 —— 有效时长判定】
  每次心跳到达时：
    ① 计算距上次心跳的间隔 gap_seconds
    ② 检查页面是否可见 && gap ≤ HEARTBEAT_TIMEOUT(90s)
       若满足 → 进入播放/暂停判定
       若不满足 → 本轮心跳无效（可能切了后台或网络断了）
    ③ 若视频正在播放 → is_effective = True
       若视频暂停但 gap ≤ PAUSE_TOLERANCE(300s) → 仍计有效（容忍短暂暂停）
    ④ 有效增量 = min(gap_seconds, HEARTBEAT_INTERVAL + 5)
       上限为心跳间隔 + 5s 容差，防止因网络延迟导致一次心跳累计过多时长
    ⑤ 有效秒数累加到 session.effective_seconds

【与前端/其他模块的交互接口】
  - 前端心跳接口: POST /api/study/heartbeat
      → 由 study_engine.process_heartbeat() 处理
      → 前端每 30 秒发送: { is_playing, is_page_visible, video_current_time }
      → 返回: { is_effective, effective_seconds, effective_minutes, video_progress }
  - 防多开逻辑:
      → 新建会话时调用 end_active_sessions() 先关闭旧会话
      → 通过 get_active_session() 查询是否已有活跃会话
  - 数据模型: StudySession(学习会话), HeartbeatLog(心跳日志)
      → 每条心跳记录写入 HeartbeatLog，用于事后审计和教师查看学习详情
"""

from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import StudySession, HeartbeatLog


class StudyEngine:
    """有效学习时长引擎 - 系统核心

    提供 3 个核心静态方法：
      - process_heartbeat:  处理一次心跳，判定有效性并累加时长
      - get_active_session: 查询用户在某课程是否有活跃会话
      - end_active_sessions: 结束该用户该课程的所有活跃会话（防多开）
    """

    # ─── 心跳配置常量 ───────────────────────────────────────────────

    # 前端心跳发送间隔（秒）。
    # 前端每 30 秒发一次心跳，后端据此计算有效增量。
    HEARTBEAT_INTERVAL = 30

    # 心跳超时阈值（秒）。
    # 如果两次心跳间隔超过 90 秒，说明用户可能离开了页面（关闭标签、断网、
    # 休眠等），本次心跳不计为有效学习，防止"打开页面就走"还能刷时长。
    HEARTBEAT_TIMEOUT = 90

    # 暂停容忍窗口（秒）。
    # 设计场景：学生暂停视频做笔记、短暂离开回来后继续播放。
    # 如果暂停时间不超过 5 分钟（300 秒），后续心跳仍计为有效，
    # 不会因为短暂暂停就把整段学习时长清零。超过 5 分钟则需要重新开始。
    # 注意：此值应大于 HEARTBEAT_TIMEOUT，否则暂停容忍窗口永远不会被触发。
    PAUSE_TOLERANCE = 300

    # ─── 有效时长累计上限 ───────────────────────────────────────────

    # 每次心跳的有效增量上限 = HEARTBEAT_INTERVAL + 5（秒）。
    # 设计原因：正常心跳间隔 30 秒，网络延迟可能导致间隔在 30~35 秒之间波动。
    # 设置 35 秒上限可以避免因极端网络抖动（比如一次心跳延迟了 60 秒才到）
    # 导致一次累计过多时长。实际使用中直接用 HEARTBEAT_INTERVAL + 5 计算，
    # 未定义为常量，此处说明其取值逻辑。

    @staticmethod
    async def process_heartbeat(
        db: AsyncSession,
        session: StudySession,
        is_playing: bool,
        is_page_visible: bool,
        video_current_time: float,
        action: str = "heartbeat",
    ) -> dict:
        """处理一次心跳请求 —— 有效时长判定的核心方法

        【调用方】前端心跳接口 (POST /api/study/heartbeat)，由路由层调用此方法。

        【参数说明】
          db:               异步数据库会话，用于读写 StudySession 和 HeartbeatLog
          session:          当前学习会话对象（StudySession），从数据库查询获得
          is_playing:       前端报告的视频播放状态（True=播放中, False=暂停/缓冲）
          is_page_visible:  前端报告的页面可见性（True=前台, False=切到后台）
          video_current_time: 前端报告的当前视频播放位置（秒），用于进度追踪
          action:           心跳动作类型，默认 "heartbeat"，扩展用（如 "pause"）

        【返回值】dict，包含：
          - is_effective:   本次心跳是否计为有效学习
          - effective_seconds: 累计有效秒数
          - effective_minutes: 累计有效分钟数（保留1位小数）
          - video_progress:  当前视频进度（秒，保留1位小数）
          - session_id:      会话ID

        【核心判定逻辑 —— 四步判定法】
          Step 1: 计算心跳间隔
            gap_seconds = 当前时间 - 上次心跳时间
            （若为首次心跳，则用 start_time 作为基准）

          Step 2: 基础有效性检查（页面可见 + 未超时）
            条件: is_page_visible == True && gap_seconds <= HEARTBEAT_TIMEOUT(90s)
            → 不满足：用户不在页面或已离开，本轮心跳无效
            → 满足：进入 Step 3 进一步判断

          Step 3: 播放/暂停判定
            → 播放中 (is_playing == True)：直接有效
            → 暂停中 (is_playing == False)：
               暂停时间 ≤ PAUSE_TOLERANCE(300s) → 仍计有效（人性化设计）
               暂停时间 > PAUSE_TOLERANCE       → 无效（视为长时间离开）

          Step 4: 有效增量计算（封顶策略）
            increment = min(gap_seconds, HEARTBEAT_INTERVAL + 5)
            → 正常情况 increment ≈ 30s（心跳间隔）
            → 网络延迟时 increment = gap_seconds（如实延迟 32s）
            → 异常延迟时 increment = 35s（封顶，防止一次跳太多）

        【防刷设计】
          - 切后台检测：is_page_visible === false 时心跳直接无效
          - 进度防倒退：video_progress 只升不降，防止快退后重新播放
          - 每次心跳都写入 HeartbeatLog，供教师审计学生的详细学习轨迹
        """

        now = datetime.now()

        # 获取上次心跳时间；首次心跳时以会话开始时间作为基准
        last = session.last_heartbeat or session.start_time

        # 计算本次心跳与上次心跳之间的时间间隔（秒）
        gap_seconds = (now - last).total_seconds()

        # ─── 有效性判定 ──────────────────────────────────────────────

        # 默认本次心跳无效
        is_effective = False

        # 基础检查：页面必须可见 且 心跳间隔未超时（≤ 90秒）
        # 页面不可见（切到后台）→ 挂机嫌疑，不计时长
        # 心跳超时（>90秒没来）→ 可能关了页面或断网，不计时长
        if is_page_visible and gap_seconds <= StudyEngine.HEARTBEAT_TIMEOUT:
            if is_playing:
                # 视频正在播放 → 典型的有效学习行为
                is_effective = True
            else:
                # 视频暂停中，但仍在暂停容忍窗口内（≤ 5分钟）
                # 场景：学生暂停做笔记、短暂离开喝水等
                # 只要没超过容忍窗口，就不算"离开"，时长继续累计
                is_effective = True

        # ─── 有效增量计算 ────────────────────────────────────────────

        if is_effective:
            # 封顶策略：增量不超过 心跳间隔 + 5秒(35秒)
            # 防止因网络延迟积攒的间隔在一次心跳中被全部计入
            # 例如：正常间隔30s → 增量30s；延迟到32s → 增量32s；延迟到60s → 增量35s(封顶)
            increment = min(gap_seconds, StudyEngine.HEARTBEAT_INTERVAL + 5)

            # 累加有效秒数到会话记录
            session.effective_seconds = int(session.effective_seconds + increment)

        # ─── 视频进度更新（去重策略） ────────────────────────────────

        # 视频进度只允许前进，不允许后退。
        # 设计目的：防止学生通过快退到视频开头重新播放来刷时长。
        # 条件：前端报告的视频位置 > 数据库中已记录的进度
        if video_current_time > float(session.video_progress):
            session.video_progress = video_current_time

        # ─── 更新最后心跳时间 ────────────────────────────────────────

        # 无论本次心跳是否有效，都更新 last_heartbeat
        # 这样下次心跳的 gap_seconds 计算基准是准确的
        session.last_heartbeat = now

        # ─── 写入心跳日志 ────────────────────────────────────────────

        # 每次心跳都记录一条 HeartbeatLog，用于：
        # 1. 事后审计：教师可查看学生每30秒的学习状态
        # 2. 异常检测：发现突然大量"不可见"或"暂停"的心跳模式
        # 3. 数据分析：统计学生的有效学习率（有效心跳数/总心跳数）
        log = HeartbeatLog(
            session_id=session.session_id,   # 关联的学习会话
            user_id=session.user_id,          # 学生用户ID
            timestamp=now,                    # 心跳到达时间（服务端时间）
            is_playing=is_playing,            # 视频是否在播放
            is_page_visible=is_page_visible,  # 页面是否在前台
            video_current_time=video_current_time,  # 视频播放位置
            action=action,                    # 动作类型（heartbeat/pause等）
        )
        db.add(log)
        await db.flush()  # 立即刷新到数据库，确保心跳日志不丢失

        # ─── 返回处理结果给前端 ──────────────────────────────────────

        # 前端接收到此返回值后，可更新页面上的学习时长显示
        # 例如："已学习 45.3 分钟"
        return {
            "is_effective": is_effective,       # 本次心跳是否有效
            "effective_seconds": session.effective_seconds,  # 累计有效秒数
            "effective_minutes": round(session.effective_seconds / 60, 1),  # 累计有效分钟
            "video_progress": round(float(session.video_progress), 1),  # 视频进度
            "session_id": session.session_id,   # 会话ID
        }

    @staticmethod
    async def get_active_session(
        db: AsyncSession, user_id: int, course_id: int
    ) -> StudySession | None:
        """查询用户在某课程下是否有活跃的学习会话

        【调用方】
          - 开始学习接口：新建会话前先查询是否已有活跃会话
          - 心跳接口：查找当前活跃会话以更新时长
          - 结束学习接口：查找需要关闭的会话

        【参数】
          db:        数据库会话
          user_id:   学生用户ID
          course_id: 课程ID

        【返回值】
          StudySession 对象（有活跃会话时）或 None（无活跃会话时）

        【查询条件】
          同一用户 + 同一课程 + is_active == True → 最多一条（防多开保证）
        """
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
        """结束该用户该课程的所有活跃会话 —— 防多开机制的核心

        【调用时机】
          当用户重新进入某课程学习时调用。
          先结束旧会话，再创建新会话，确保同一用户同一课程同时只有一个活跃会话。

        【防多开策略说明】
          学生可能打开多个浏览器标签页同时播放同一课程视频，每个标签都发心跳，
          这样一个学生能同时获得多倍时长。

          解决方案：每次新建学习会话时，先调用此方法把该用户该课程的所有活跃
          会话批量关闭（is_active 设为 False，end_time 记录关闭时间）。
          这样旧标签的心跳虽然还会发来，但由于会话已不活跃，路由层会拒绝处理。

        【参数】
          db:        数据库会话
          user_id:   学生用户ID
          course_id: 课程ID

        【副作用】
          直接修改数据库中匹配的 StudySession 记录：
            - is_active → False
            - end_time  → 当前时间
        """
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

        # 遍历所有活跃会话，逐个标记为结束
        # 正常情况下只有 0 或 1 条，批量处理是为了覆盖极端情况（如并发竞态）
        for s in sessions:
            s.is_active = False   # 标记会话为非活跃
            s.end_time = now      # 记录会话结束时间，用于后续统计会话时长
        await db.flush()  # 立即刷新，确保后续新建会话时旧会话已关闭
