"""
数据模型模块
============
功能：定义 SQLAlchemy ORM 模型，映射到 MySQL 数据库表，构成系统的核心数据结构。

在系统中的角色：
- User：用户表，存储钉钉用户信息，区分学生/教师/管理员角色
- Course：课程表，存储课程元数据和学习要求，由教师创建管理
- Section：小节表，存储课程下的视频小节，每个课程包含多个小节
- StudySession：学习会话表，记录每次学习行为的完整生命周期，
  是"有效学习时长"计算的核心数据源
- HeartbeatLog：心跳日志表，记录学习过程中的实时状态快照，
  是防刷课判定和有效时长计算的依据

数据流概览：
  学生打开课程小节 → 创建 StudySession → 前端每30秒上报心跳 → 写入 HeartbeatLog
  → 心跳处理器校验播放状态/页面可见性 → 累加 StudySession.effective_seconds
  → 学生关闭页面 → 标记 StudySession.is_active=False

防刷课关键设计：
  HeartbeatLog 中 is_playing + is_page_visible 两字段联合判定：
  - 播放中且页面可见 → 有效学习，累加时长
  - 暂停/页面隐藏 → 无效，不累加
  这确保了学生不能通过最小化窗口或暂停视频来刷时长

课程-小节两级结构（v3.0）：
  Course（课程）→ 包含多个 Section（小节）→ 每个小节有独立视频
  学生学习时针对具体小节计时，课程总进度由各小节进度汇总
"""

from sqlalchemy import Column, BigInteger, String, Enum, DateTime, ForeignKey, Boolean, Integer, DECIMAL, Text, Float
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """
    用户模型

    用途：存储通过钉钉免登获取的用户信息，支撑权限控制和数据关联。

    字段说明：
        id               — 自增主键
        dingtalk_user_id — 钉钉用户唯一标识，作为钉钉 API 交互的 key，
                           设为 unique + index 防止重复注册并加速查询
        name             — 用户姓名（来自钉钉通讯录）
        real_name        — 真实姓名（钉钉通讯录详解接口获取，用于实名展示）
        phone            — 手机号（钉钉通讯录获取，用于实名信息核验）
        role             — 角色：student 教师/管理员/学生，控制前端页面和 API 权限
        class_name       — 班级名称（如"高三1班"），用于按班级筛选统计
        class_id         — 班级 ID，关联钉钉部门体系（预留）
        avatar           — 头像 URL，前端展示用
        created_at       — 首次登录时间
        updated_at       — 信息更新时间（如角色变更）
    """
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dingtalk_user_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    role = Column(Enum("student", "teacher", "admin"), default="student", nullable=False)
    class_name = Column(String(50), default="", comment="班级名称")
    class_id = Column(BigInteger, default=0, comment="班级ID")
    avatar = Column(String(500), default="")
    # 浏览器登录密码哈希：钉钉免登用户没有密码，浏览器登录用户必须有
    # 使用 PBKDF2-SHA256 算法，格式为 "盐:哈希值"
    password_hash = Column(String(200), default="", comment="浏览器登录密码哈希(空=仅钉钉登录)")
    # 实名信息：钉钉免登时从通讯录API自动获取
    real_name = Column(String(50), default="", comment="真实姓名（钉钉通讯录获取）")
    phone = Column(String(20), default="", comment="手机号（钉钉通讯录获取）")
    # API Key：供智能体/外部程序调用系统接口的长期密钥
    # 格式为 "sk_" + 32字节随机十六进制字符串，共67字符
    # 教师和管理员可通过管理后台生成，智能体携带此Key即可代替JWT访问API
    api_key = Column(String(100), default=None, nullable=True, unique=True, comment="API Key(null=未生成)")
    created_at = Column(DateTime, server_default=func.now())
    # onupdate=func.now() — 当任意字段被 UPDATE 时自动刷新时间戳
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Course(Base):
    """
    课程模型

    用途：存储课程元数据和学习要求，由教师创建和管理。
         视频内容通过 Section（小节）模型关联，一门课包含多个小节。

    字段说明：
        id               — 自增主键
        title            — 课程标题
        description      — 课程描述
        teacher_id       — 创建该课程的教师 ID，外键关联 users 表
        require_minutes  — 该课程要求的有效学习时长（分钟），达标即视为完成
        start_date       — 课程开始日期，控制学生何时可以开始学习
        end_date         — 课程截止日期，逾期后不再计入统计
        status           — 课程状态：draft=草稿/active=进行中/ended=已结束
        created_at       — 创建时间
        updated_at       — 最后修改时间

    视频字段迁移说明（v3.0）：
        video_type, video_url, wukong_url, duration_seconds 已迁移到 Section 表。
        旧字段保留在数据库中但不再使用（MySQL 无法 DROP COLUMN 安全在线操作），
        新代码通过 Section 访问视频数据。
    """
    __tablename__ = "courses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), default="")
    # === 以下视频字段已废弃，保留在DB但不再使用 ===
    # 视频数据已迁移到 sections 表，每个小节有独立的 video_type/video_url/duration_seconds
    # 旧字段在数据库中仍存在，但新代码不再读写这些字段
    video_type = Column(Enum("url", "local"), default="url", nullable=True)
    video_url = Column(String(500), default="", comment="[已废弃] 迁移至 sections 表")
    wukong_url = Column(String(500), default="", comment="[已废弃]")
    duration_seconds = Column(Integer, default=0, comment="[已废弃] 迁移至 sections 表")
    # === 废弃字段结束 ===
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    # 默认60分钟，教师可按课程难度调整要求学习时长；null=不设时长要求
    require_minutes = Column(Integer, default=None, nullable=True, comment="要求学习时长(分钟)，null=不设要求")
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(Enum("active", "ended", "draft"), default="draft", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Section(Base):
    """
    小节模型

    用途：课程下的视频小节，每个课程包含多个小节。
         小节是学生实际学习的最小单元，每个小节有独立的视频源。

    字段说明：
        id               — 自增主键
        course_id        — 所属课程 ID，外键关联 courses 表，加索引加速课程维度查询
        title            — 小节标题（如"第1讲 集合的概念"）
        sort_order       — 排序序号，控制小节在课程内的显示顺序，从小到大排列
        video_type       — 视频来源类型：
                           url=外部链接（B站/腾讯视频等）
                           local=本地上传（视频文件存储在服务器本地）
        video_url        — 视频地址：外部链接或服务器本地文件名
        duration_seconds — 小节视频总时长（秒）
        open_time        — 开播时间：未到该时间学生无法进入学习，null表示不限制
        created_at       — 创建时间

    与课程的关系：
        Course 1:N Section — 一门课包含多个小节，删除课程时级联删除其下所有小节
    """
    __tablename__ = "sections"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, comment="小节标题")
    sort_order = Column(Integer, default=0, comment="排序序号（从小到大）")
    video_type = Column(Enum("url", "local"), default="url", nullable=False)
    video_url = Column(String(500), default="", comment="视频地址：外部链接或本地路径")
    duration_seconds = Column(Integer, default=0, comment="小节视频时长(秒)")
    # 开播时间：未到该时间学生无法进入学习，null表示不限制
    # 开播时间过后学生始终可进入（包括复习），不再锁定
    open_time = Column(DateTime, nullable=True, comment="开播时间（未到不可进入学习，null=不限制）")
    created_at = Column(DateTime, server_default=func.now())


class StudySession(Base):
    """
    学习会话模型

    用途：记录学生一次完整的学习行为（从打开课程到关闭页面），
         是有效学习时长计算和进度跟踪的核心数据实体。

    字段说明：
        id                — 自增主键
        user_id           — 学习的学生 ID，外键关联 users 表，加索引加速用户维度查询
        course_id         — 学习的课程 ID，外键关联 courses 表，加索引加速课程维度查询
        section_id        — 学习的小节 ID，外键关联 sections 表，nullable 兼容旧数据
        session_id        — 会话唯一标识（UUID），前端生成，用于关联心跳日志，
                            设为 unique + index 防止重复提交
        start_time        — 学习开始时间，学生打开课程页面时记录
        last_heartbeat    — 最近一次收到心跳的时间，用于判断会话是否超时断开
        effective_seconds — 累计有效学习秒数（仅播放中+页面可见时累加），
                            这是系统最核心的指标，决定了学生是否达标
        video_progress    — 视频播放进度百分比（0-100），对应视频播放器的进度条
        is_active         — 会话是否仍在进行中，加索引加速"活跃会话"查询
        end_time          — 学习结束时间，学生主动关闭或会话超时时记录
        created_at        — 记录创建时间

    业务逻辑关键点：
        effective_seconds 的累加由心跳处理器控制：
        - 只在 is_playing=True 且 is_page_visible=True 时累加
        - 每次 heartbeat 间隔按 30 秒计算（与前端心跳上报频率一致）
        - 学生关闭页面时 is_active→False，不再接受新心跳
    """
    __tablename__ = "study_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=False, index=True)
    # section_id 可为空，兼容 v2.x 旧数据（旧数据没有小节维度）
    section_id = Column(BigInteger, ForeignKey("sections.id"), nullable=True, index=True, comment="学习的小节ID")
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    effective_seconds = Column(Integer, default=0, comment="有效学习秒数")
    # DECIMAL(10,2) 精确存储百分比，避免浮点误差导致进度判断不准
    video_progress = Column(DECIMAL(10, 2), default=0, comment="视频播放进度0-100%")
    # 非活跃会话不再接受心跳，防止过期会话被恶意续期
    is_active = Column(Boolean, default=True, index=True)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class HeartbeatLog(Base):
    """
    心跳日志模型

    用途：记录学习过程中每 30 秒一次的状态快照，是防刷课判定和
         有效时长计算的最细粒度数据。即使后续需要审计或申诉，
         也可通过心跳日志回溯完整的学习过程。

    字段说明：
        id                — 自增主键
        session_id        — 所属学习会话 ID，外键关联 study_sessions.session_id，
                            加索引加速按会话查询心跳序列
        user_id           — 学习的学生 ID，加索引加速用户维度排查
        timestamp         — 心跳上报时间，由服务端记录（防客户端伪造）
        is_playing        — 视频是否正在播放，False 表示暂停/缓冲中
        is_page_visible   — 学习页面是否可见，False 表示切换了标签页/最小化窗口
        video_current_time — 视频当前播放位置（秒），用于检测快进/跳跃行为
        action            — 心跳类型标识：
                            heartbeat=常规定时上报（每30秒）
                            play=用户点击播放
                            pause=用户点击暂停
                            seek=用户拖动进度条
                            verify=页面焦点验证（切回时触发）
                            end=会话结束

    防刷课判定逻辑：
        有效心跳条件：is_playing=True 且 is_page_visible=True
        - 两者缺一均不累加 effective_seconds
        - video_current_time 用于二次验证：播放位置应匀速增长，
          若出现跳跃（如1秒跳了5分钟的视频进度），标记为可疑
    """
    __tablename__ = "heartbeat_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("study_sessions.session_id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    is_playing = Column(Boolean, default=True)
    is_page_visible = Column(Boolean, default=True)
    # DECIMAL(12,2) 最大支持约 115 天的视频时长，远超实际需求，但保留足够余量
    video_current_time = Column(DECIMAL(12, 2), default=0, comment="当前播放秒数")
    # action 字段区分心跳类型，便于后续统计分析和异常检测
    action = Column(String(20), default="heartbeat", comment="heartbeat/play/pause/seek/verify/end")


class Assignment(Base):
    """
    作业模型

    用途：教师发布的作业，绑定到小节（section），每个小节最多一份作业。
         v4.0 起从课程级（1 course = 1 assignment）迁移到小节级（1 section = 1 assignment）。

    字段说明：
        id                — 自增主键
        section_id        — 所属小节 ID，外键关联 sections 表（unique 约束保证 1:1）
        course_id         — 所属课程 ID（冗余字段，方便按课程批量查询作业）
        title             — 作业标题
        description       — 题目描述/要求（Markdown 或纯文本）
        question_files    — 题目文件 URL 列表（图片/PDF，JSON 数组）
        grading_prompt    — 评分标准/批改提示词（传递给智能体）
        deadline          — 截止时间（迟交仍可提交，但标记 is_late=True）
        status            — 作业状态：draft=草稿/published=已发布/closed=已关闭
        grading_mode      — 批改模式：auto=自动/manual=人工/hybrid=混合
        grading_status    — 批改状态：pending=待批改/graded=已批改
        grading_triggered — 是否已触发智能体批改（防重复触发）
        created_at        — 创建时间
        updated_at        — 最后修改时间
    """
    __tablename__ = "assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # v4.0: 从 course_id 迁移到 section_id，1 section = 1 assignment
    section_id = Column(BigInteger, ForeignKey("sections.id"), unique=True, nullable=False, index=True, comment="所属小节ID")
    # course_id 冗余字段，方便按课程维度查询所有作业，迁移后从 section.course_id 自动填入
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=True, index=True, comment="所属课程ID(冗余)")
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    question_files = Column(Text, default="[]", comment="题目文件URL数组(JSON)")
    grading_prompt = Column(Text, default="", comment="评分标准/批改提示词")
    reference_answer = Column(Text, default="", comment="参考答案（供智能体批改参考）")
    deadline = Column(DateTime, nullable=True)
    status = Column(Enum("draft", "published", "closed"), default="draft", nullable=False)
    grading_mode = Column(Enum("auto", "manual", "hybrid"), default="auto", nullable=False, comment="批改模式")
    grading_status = Column(Enum("pending", "graded"), default="pending", nullable=False, comment="批改状态")
    grading_triggered = Column(Boolean, default=False, comment="是否已触发智能体批改")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Submission(Base):
    """
    作业提交模型

    用途：学生提交的作业，包含上传的图片列表。支持多次提交（截止前可修改）。

    字段说明：
        id              — 自增主键
        assignment_id   — 所属作业 ID，外键关联 assignments 表
        user_id         — 提交的学生 ID，外键关联 users 表
        images          — 图片 URL 数组（JSON 格式）
        status          — 提交状态：pending=待批改/graded=已批改
        is_late         — 是否迟交：截止时间后提交标记为 True，仍可提交但记录迟交
        version         — 提交版本号（1, 2, 3...）
        is_latest       — 是否为最新版本
        submitted_at    — 提交时间
    """
    __tablename__ = "submissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    assignment_id = Column(BigInteger, ForeignKey("assignments.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    images = Column(Text, default="[]", comment="图片URL数组(JSON)")
    status = Column(Enum("pending", "graded"), default="pending", nullable=False)
    # 是否迟交：截止时间后仍可提交，但标记为迟交，方便教师统计
    is_late = Column(Boolean, default=False, comment="是否迟交（截止时间后提交）")
    version = Column(Integer, default=1, comment="提交版本号")
    is_latest = Column(Boolean, default=True, index=True, comment="是否最新版本")
    submitted_at = Column(DateTime, server_default=func.now())


class GradingReport(Base):
    """
    批改报告模型

    用途：智能体生成的批改报告，一对一关联到提交。

    字段说明：
        id              — 自增主键
        submission_id   — 关联的提交 ID，外键唯一约束
        score           — 分数（0-100）
        feedback        — 总评（Markdown 或纯文本）
        detail          — 各题详细批改（JSON 格式）
        generated_by    — 智能体标识（如 "wukong", "gpt-4o", "custom"）
        review_status   — 复核状态：pending_review=待复核/confirmed=已确认/modified=已修改
        created_at      — 生成时间
    """
    __tablename__ = "grading_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    submission_id = Column(BigInteger, ForeignKey("submissions.id"), unique=True, nullable=False, index=True)
    score = Column(Integer, default=0, comment="分数0-100")
    feedback = Column(Text, default="")
    detail = Column(Text, default="{}", comment="各题详细批改(JSON)")
    generated_by = Column(String(50), default="", comment="智能体标识")
    review_status = Column(Enum("pending_review", "confirmed", "modified"), default="confirmed", nullable=False, comment="复核状态")
    created_at = Column(DateTime, server_default=func.now())


class Announcement(Base):
    """
    公告模型

    用途：教师/管理员发布的公告通知，学生端首页展示。
         可绑定到具体课程（课程公告），也可为全平台公告（course_id=null）。

    字段说明：
        id           — 自增主键
        course_id    — 关联课程 ID，null 表示全平台公告
        title        — 公告标题
        content      — 公告正文（纯文本）
        priority     — 优先级：normal=普通/important=重要/urgent=紧急
        created_by   — 发布者用户 ID，外键关联 users 表
        created_at   — 发布时间
        updated_at   — 更新时间
    """
    __tablename__ = "announcements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # course_id 为 null 时表示全平台公告，所有人都可见
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=True, index=True, comment="关联课程ID(null=全平台公告)")
    title = Column(String(200), nullable=False, comment="公告标题")
    content = Column(Text, default="", comment="公告正文")
    priority = Column(Enum("normal", "important", "urgent"), default="normal", nullable=False, comment="优先级")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AnnouncementRead(Base):
    """
    公告已读记录模型

    用途：记录每个用户对每条公告的已读状态，支撑"未读公告红点"功能。
         用户查看公告后标记已读，前端根据未读数显示红点。

    字段说明：
        id               — 自增主键
        announcement_id  — 公告 ID，外键关联 announcements 表
        user_id          — 用户 ID，外键关联 users 表
        read_at          — 标记已读时间

    唯一约束：(announcement_id, user_id) — 同一用户对同一公告只有一条已读记录
    """
    __tablename__ = "announcement_reads"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    announcement_id = Column(BigInteger, ForeignKey("announcements.id"), nullable=False, index=True, comment="公告ID")
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")
    read_at = Column(DateTime, server_default=func.now(), comment="已读时间")

    __table_args__ = (
        # 同一用户对同一公告只能有一条已读记录
        {"mysql_charset": "utf8mb4"},
    )


class SectionFeedback(Base):
    """
    小节评价/反馈模型

    用途：学生对课程小节的评价反馈，包括评分和文字留言。
         教师可据此了解课程质量和学生满意度。

    字段说明：
        id           — 自增主键
        section_id   — 关联小节 ID，外键关联 sections 表
        user_id      — 评价学生 ID，外键关联 users 表
        rating       — 评分（1-5 星）
        comment      — 文字评价（最多500字）
        created_at   — 评价时间
    """
    __tablename__ = "section_feedbacks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    section_id = Column(BigInteger, ForeignKey("sections.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, default=5, comment="评分1-5星")
    comment = Column(String(500), default="", comment="文字评价")
    created_at = Column(DateTime, server_default=func.now())


class GradingTask(Base):
    """
    批改任务模型

    用途：追踪每个提交的智能体批改状态，支持重试和错误记录。

    字段说明：
        id                 — 自增主键
        submission_id      — 关联的提交 ID，外键关联 submissions 表
        stitched_image_url — 拼接后的长图 URL
        agent_task_id      — 智能体返回的任务 ID（用于状态查询）
        status             — 任务状态：pending=待发送/sent=已发送/graded=已批改/failed=失败
        retry_count        — 已重试次数
        error_message      — 错误信息（失败时记录）
        sent_at            — 发送给智能体的时间
        graded_at          — 智能体回调时间
        created_at         — 创建时间
    """
    __tablename__ = "grading_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    submission_id = Column(BigInteger, ForeignKey("submissions.id"), nullable=False, index=True)
    stitched_image_url = Column(String(500), default="", comment="拼接后的长图URL")
    agent_task_id = Column(String(100), default="", comment="智能体任务ID")
    status = Column(Enum("pending", "sent", "graded", "failed"), default="pending", nullable=False, comment="任务状态")
    retry_count = Column(Integer, default=0, comment="已重试次数")
    error_message = Column(Text, default="", comment="错误信息")
    sent_at = Column(DateTime, nullable=True, comment="发送时间")
    graded_at = Column(DateTime, nullable=True, comment="批改完成时间")
    created_at = Column(DateTime, server_default=func.now())
