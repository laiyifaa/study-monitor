from sqlalchemy import Column, BigInteger, String, Enum, DateTime, ForeignKey, Boolean, Integer, DECIMAL
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dingtalk_user_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    role = Column(Enum("student", "teacher", "admin"), default="student", nullable=False)
    class_name = Column(String(50), default="", comment="班级名称")
    class_id = Column(BigInteger, default=0, comment="班级ID")
    avatar = Column(String(500), default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Course(Base):
    __tablename__ = "courses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), default="")
    # 视频源：url=外部链接(如B站/腾讯视频)，local=本地上传
    video_type = Column(Enum("url", "local"), default="url", nullable=False)
    video_url = Column(String(500), default="", comment="视频地址：外部链接或本地路径")
    wukong_url = Column(String(500), default="", comment="悟空播放器URL(已废弃，兼容保留)")
    duration_seconds = Column(Integer, default=0, comment="课程总时长(秒)")
    teacher_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    require_minutes = Column(Integer, default=60, comment="要求学习时长(分钟)")
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(Enum("active", "ended", "draft"), default="draft", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(BigInteger, ForeignKey("courses.id"), nullable=False, index=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    effective_seconds = Column(Integer, default=0, comment="有效学习秒数")
    video_progress = Column(DECIMAL(10, 2), default=0, comment="视频播放进度0-100%")
    is_active = Column(Boolean, default=True, index=True)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class HeartbeatLog(Base):
    __tablename__ = "heartbeat_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("study_sessions.session_id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    is_playing = Column(Boolean, default=True)
    is_page_visible = Column(Boolean, default=True)
    video_current_time = Column(DECIMAL(12, 2), default=0, comment="当前播放秒数")
    action = Column(String(20), default="heartbeat", comment="heartbeat/play/pause/seek/verify/end")
