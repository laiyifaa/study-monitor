"""
配置管理模块
============
功能：集中管理所有环境变量和配置项，提供类型安全的配置访问接口。

在系统中的角色：
- 作为整个后端的"配置中心"，所有模块通过 get_settings() 获取配置
- 利用 pydantic-settings 自动从 .env 文件和环境变量中读取配置
- 通过 @lru_cache 保证 Settings 单例，避免重复解析环境变量
- 提供 mysql_url / redis_url 属性，将分散的连接参数组装为标准连接字符串

设计决策：
- 使用 pydantic BaseSettings 而非手动 os.environ，获得类型校验和默认值支持
- 敏感信息（密钥、密码）不硬编码，强制从 .env 或环境变量注入
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    全局配置类

    用途：将所有配置项定义为带类型的属性，pydantic 会按以下优先级读取值：
          环境变量 > .env 文件 > 代码中的默认值

    参数说明：每个属性即为一个配置项，名称与 .env 中的 key 一一对应
    """

    # ── 钉钉开放平台凭证 ──
    # 用于调用钉钉 API（免登、发送消息等），空值表示未配置钉钉集成
    DT_APP_KEY: str = ""
    DT_APP_SECRET: str = ""
    DT_CORP_ID: str = ""
    DT_ROBOT_WEBHOOK: str = ""   # 群机器人 Webhook，用于推送学习提醒
    DT_ROBOT_SECRET: str = ""    # 机器人加签密钥，防止 Webhook 被伪造调用

    # ── MySQL 数据库连接 ──
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "study_monitor"
    MYSQL_PASSWORD: str = "change_me"    # 必须通过 .env 注入，默认值仅用于开发
    MYSQL_DATABASE: str = "study_monitor"

    # ── Redis 连接 ──
    # 用途：缓存钉钉 access_token（有效期2h，避免频繁请求）、心跳限流（防刷课）
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""     # 生产环境务必设置密码
    REDIS_DB: int = 0

    # ── JWT 令牌配置 ──
    # 前端通过钉钉免登获取 JWT，后续请求携带令牌鉴权
    JWT_SECRET: str = "change_me"        # 签名密钥，必须通过 .env 注入
    JWT_ALGORITHM: str = "HS256"         # 对称加密算法，适用于单服务场景
    JWT_EXPIRE_HOURS: int = 72           # 令牌有效期72小时，覆盖一个长周末不断登录

    # ── CDN 配置 ──
    # 天翼云 CDN 加速域名，启用后视频文件通过 CDN 分发，降低源站带宽压力
    # 格式示例：https://cdn.example.com（带协议前缀）
    # 为空时表示不使用 CDN，视频直接从 Nginx 服务器分发（向后兼容）
    CDN_DOMAIN: str = ""

    # ── 智能体批改配置 ──
    # 智能体 API 地址，用于自动批改作业
    # 为空时表示未配置，定时任务会跳过智能体调用
    GRADING_AGENT_URL: str = ""
    GRADING_AGENT_API_KEY: str = ""
    GRADING_AGENT_TIMEOUT: int = 30
    GRADING_MAX_RETRIES: int = 3
    GRADING_RETRY_DELAY: int = 5
    GRADING_CONCURRENCY_LIMIT: int = 10
    API_BASE_URL: str = "http://localhost:8000"

    # ── 服务运行参数 ──
    API_HOST: str = "0.0.0.0"            # 监听所有网卡，Docker 部署时必须
    API_PORT: int = 8000
    DEBUG: bool = True                   # 开启时 SQLAlchemy 会打印 SQL 语句

    @property
    def mysql_url(self) -> str:
        """
        组装 MySQL 异步连接字符串

        返回值：aiomysql 驱动格式的连接 URL
                例：mysql+aiomysql://user:pwd@host:3306/db?charset=utf8mb4

        核心逻辑：charset=utf8mb4 确保支持中文和 emoji，
                  因为钉钉用户昵称可能包含 emoji
        """
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """
        组装 Redis 连接字符串

        返回值：标准 redis:// URL
                有密码时：redis://:password@host:port/db
                无密码时：redis://host:port/db

        核心逻辑：密码为空时省略认证段，否则 aioredis 会用空密码鉴权导致连接失败
        """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    class Config:
        env_file = ".env"   # 指定环境变量文件路径，项目根目录下


@lru_cache()
def get_settings() -> Settings:
    """
    获取全局配置单例

    用途：各模块通过 from app.config import get_settings 获取配置，
          无需自行解析环境变量。

    返回值：Settings 实例（全局唯一）

    核心逻辑：@lru_cache 无参装饰器使函数只执行一次并缓存结果，
              后续调用直接返回缓存，既保证单例又避免重复 I/O
    """
    return Settings()
