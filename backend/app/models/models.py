"""
数据模型模块
============
功能：定义 SQLAlchemy ORM 模型，映射到 MySQL 数据库表，构成系统的核心数据结构。

在系统中的角色：
- User：用户表，存储钉钉用户信息，区分学生/教师/管理员角色
- Course：课程表，存储课程元数据和视频源信息，由教师创建管理
- StudySession：学习会话表，记录每次学习行为的完整生命周期，
  是"有效学习时长"计算的核心数据源
- HeartbeatLog：心跳日志表，记录学习过程中的实时状态快照，
  是防刷课判定和有效时长计算的依据

数据流概览：
  学生打开课程 → 创建 StudySession → 前端每30秒上报心跳 → 写入 HeartbeatLog
  → 心跳处理器校验播放状态/页面可见性 → 累加 StudySession.effective_seconds
  → 学生关闭页面 → 标记 StudySession.is_active=False

防刷课关键设计：
  HeartbeatLog 中 is_playing + is_page_visible 两字段联合判定：
  - 播放中且页面可见 → 有效学习，累加时长
  - 暂停/页面隐藏 → 无效，不累加
  这确保了学生不能通过最小化窗口或暂停视频来刷时长
"""

from sqlalchemy import Column, BigInteger, String, Enum, DateTime, ForeignKey, Boolean, Integer, DECIMAL
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
    # API Key：供智能体/外部程序调用系统接口的长期密钥
    # 格式为 "sk_" + 32字节随机十六进制字符串，共67字符
    # 教师和管理员可通过管理后台生成，智能体携带此Key即可代替JWT访问API
    api_key = Column(String(100), default="", unique=True, comment="API Key(空=未生成)")
    created_at = Column(DateTime, server_default=func.now())
    # onupdate=func.now() — 当任意字段被 UPDATE 时自动刷新时间戳
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Course(Base):
    """
    课程模型

    用途：存储课程信息，包括视频源和学习要求，由教师创建和管理。

    字段说明：
        id               — 自增主键
        title            — 课程标题
        description      — 课程描述
        video_type       — 视频来源类型：
                           url=外部链接（B站/腾讯视频等，学生跳转观看）
                           local=本地上传（视频文件存储在服务器本地）
        video_url        — 视频地址，含义随 video_type 变化
        wukong_url       — 钉钉悟空智能体接口（预留字段，暂未使用）
        duration_seconds — 课程视频总时长（秒），用于计算学习进度百分比
        teacher_id       — 创建该课程的教师 ID，外键关联 users 表
        require_minutes  — 该课程要求的有效学习时长（分钟），达标即视为完成
        start_date       — 课程开始日期，控制学生何时可以开始学习
        end_date         — 课程截止日期，逾期后不再计入统计
        status           — 课程状态：draft=草稿/active=进行中/ended=已结束
        created_at       — 创建时间
        updated_at       — 最后修改时间
    """
    __tablename__ = "courses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), default="")
    # 视频源：url=外部链接(如B站/腾讯视频)，local=本地上传
    video_type = Column(Enum("url", "local"), default="url", nullable=False)
    video_url = Column(String(500), default="", comment="视频地址：外部链接或本地路径")
    wukong_url = Column(String(500), default="", comment="钉钉悟空智能体接口预留(暂未使用)")
    duration_seconds = Column(Integer, default=0, comment="课程总时长(秒)")
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    # 默认60分钟，教师可按课程难度调整要求学习时长
    require_minutes = Column(Integer, default=60, comment="要求学习时长(分钟)")
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(Enum("active", "ended", "draft"), default="draft", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StudySession(Base):
    """
    学习会话模型

    用途：记录学生一次完整的学习行为（从打开课程到关闭页面），
         是有效学习时长计算和进度跟踪的核心数据实体。

    字段说明：
        id                — 自增主键
        user_id           — 学习的学生 ID，外键关联 users 表，加索引加速用户维度查询
        course_id         — 学习的课程 ID，外键关联 courses 表，加索引加速课程维度查询
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
