"""
====================================================================
  JWT 认证与权限校验工具 (JWT Helper)
====================================================================

【功能概述】
  本模块是整个系统的身份认证和权限控制基础设施。基于 JSON Web Token (JWT)
  实现无状态的身份验证，为所有需要鉴权的 API 接口提供统一的安全保障。

【设计思路】
  采用标准的 JWT 认证流程：
    1. 用户通过钉钉免登或浏览器登录 → 后端签发 JWT Token
    2. 前端将 Token 存储在 localStorage，每次请求携带在 Authorization 头中
    3. 后端中间件解析 Token → 还原用户身份 → 注入到请求上下文
    4. 路由处理函数通过依赖注入获取当前用户对象，直接使用

  权限控制采用 FastAPI 依赖注入 + 装饰器模式：
    - get_current_user: 基础依赖，从 Token 中解析用户
    - require_role: 高阶依赖，在获取用户的基础上校验角色权限

【核心流程图】
  登录 → create_token(user_id, role)
         → 返回 JWT 字符串给前端

  API 请求 → Authorization: Bearer <token>
           → get_current_user 依赖注入
             → 解析 Token → 查询数据库 → 返回 User 对象
             → 可选: require_role("teacher") → 校验角色

【JWT Payload 结构】
  {
    "sub": "用户ID",       — subject，JWT 标准字段，存放用户唯一标识
    "role": "用户角色",     — 自定义字段: student(学生) / teacher(教师) / admin(管理员)
    "exp": "过期时间戳"    — JWT 标准字段，自动由库校验
  }

【角色权限模型】
  系统定义 3 种角色：
    - student: 学生，只能访问学习相关接口（心跳、进度查询等）
    - teacher: 教师，可访问统计看板、课程管理等接口
    - admin:   管理员，拥有所有权限（超级用户，开发调试用）

  权限校验规则：
    - require_role("teacher") → 允许 teacher 和 admin
    - require_role("student") → 允许 student 和 admin
    - admin 角色始终通过所有权限检查（硬编码在 checker 中）

【与前端/其他模块的交互接口】
  - 登录接口: POST /api/auth/ding-login  → 调用 create_token() 签发 Token
  - 所有鉴权 API: 通过 Depends(get_current_user) 注入当前用户
  - 教师专用 API: 通过 Depends(require_role("teacher")) 校验权限
  - 前端请求头: Authorization: Bearer <jwt_token>
  - 配置来源: app.config.settings 中的 JWT_SECRET / JWT_ALGORITHM / JWT_EXPIRE_HOURS
"""

from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import User

# 加载全局配置，获取 JWT 相关参数（密钥、算法、过期时间等）
settings = get_settings()


def create_token(user_id: int, role: str) -> str:
    """创建 JWT Token

    【调用方】
      - 钉钉免登接口 (POST /api/auth/ding-login)
        用户通过钉钉 OAuth 登录成功后，调用此方法签发 Token
      - 浏览器登录接口 (POST /api/auth/login)
        用户通过用户名密码登录成功后，调用此方法签发 Token

    【参数】
      user_id: 用户唯一标识（数据库 User.id）
      role:    用户角色（"student" / "teacher" / "admin"）

    【返回值】
      编码后的 JWT 字符串，例如：
      "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIx..."

    【Token 生命周期】
      - 签发时写入 exp（过期时间），由 JWT_EXPIRE_HOURS 配置控制（默认24小时）
      - 过期后 get_current_user 会抛出 401 异常，前端需引导重新登录
      - Token 无撤销机制（无状态），过期前始终有效
    """
    # 构造 JWT Payload
    payload = {
        "sub": str(user_id),     # subject: JWT 标准字段，存放用户ID（字符串形式）
        "role": role,             # 自定义字段：用户角色，用于后续权限校验
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS),  # 过期时间
    }

    # 使用 HS256 算法和密钥对 Payload 进行编码，生成 Token 字符串
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT Token

    【调用方】
      - get_current_user() — 从请求头提取 Token 后调用此方法解码

    【参数】
      token: JWT 字符串（不含 "Bearer " 前缀）

    【返回值】
      解码后的 Payload 字典，包含 sub(用户ID)、role(角色)、exp(过期时间) 等字段

    【异常处理】
      - Token 过期 → JWTError → 401 "无效的认证令牌"
      - Token 被篡改 → JWTError → 401 "无效的认证令牌"
      - Token 格式错误 → JWTError → 401 "无效的认证令牌"

    【安全说明】
      - 此方法同时完成签名验证和过期检查
      - 使用 jose 库的 jwt.decode()，内部会自动校验 exp 字段
      - 配置中 JWT_ALGORITHM 指定算法（HS256），防止算法混淆攻击
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        # 统一将所有 JWT 异常（过期、篡改、格式错误等）返回 401
        # 不向客户端暴露具体错误类型，防止信息泄露
        raise HTTPException(status_code=401, detail="无效的认证令牌")


async def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从请求头中提取 Token 或 API Key 并获取当前用户 —— FastAPI 依赖注入

    【调用方】
      所有需要鉴权的 API 路由，通过 FastAPI 的 Depends() 机制自动调用。

    【工作机制】
      支持两种认证方式（优先级从高到低）：
      1. X-API-Key 请求头：智能体/外部程序使用，长期有效，无需续期
      2. Authorization: Bearer <token>：浏览器/钉钉客户端使用，有过期时间

    【参数】
      authorization: FastAPI 自动从请求头 "Authorization" 注入
      x_api_key:     FastAPI 自动从请求头 "X-API-Key" 注入
      db:            FastAPI 自动注入数据库会话

    【异常】
      - 两种认证方式都未提供 → 401 "缺少认证令牌"
      - Token 无效/过期 → 401 "无效的认证令牌"
      - API Key 无效 → 401 "无效的API Key"
      - 用户不存在 → 404 "用户不存在"
    """
    # 优先检查 API Key 认证（智能体调用场景）
    if x_api_key:
        result = await db.execute(select(User).where(User.api_key == x_api_key))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="无效的API Key")
        return user

    # 其次检查 JWT Token 认证（浏览器/钉钉客户端场景）
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少认证令牌")

    # 去掉 "Bearer " 前缀（7个字符），得到纯 Token
    token = authorization[7:]

    # 解码 Token，获取 Payload（包含 sub/user_id 和 role）
    payload = decode_token(token)

    # 从 Payload 中提取用户ID
    user_id = int(payload.get("sub", 0))

    # 查询数据库获取完整用户对象
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return user


def require_role(*roles: str):
    """角色权限校验 —— 工厂函数，返回 FastAPI 依赖

    【调用方】
      需要限制访问权限的 API 路由，通过 Depends() 使用。
      例如：
        # 仅教师和管理员可访问
        @router.get("/dashboard")
        async def dashboard(user: User = Depends(require_role("teacher"))):
            ...

        # 学生和教师都可访问（管理员始终可访问）
        @router.get("/courses")
        async def courses(user: User = Depends(require_role("student", "teacher"))):
            ...

    【参数】
      *roles: 允许访问的角色列表，可传入一个或多个角色名
              支持的角色: "student", "teacher", "admin"

    【返回值】
      返回一个异步函数 checker，作为 FastAPI 依赖使用。
      checker 内部会：
        1. 先调用 get_current_user 获取当前用户（若未登录则 401）
        2. 检查用户角色是否在允许列表中
        3. admin 角色硬编码为始终通过（超级用户权限）
        4. 通过则返回 User 对象，不通过则 403

    【权限矩阵】
      require_role() 调用         | student | teacher | admin
      ─────────────────────────────────────────────────────
      require_role("student")     |   ✓     |   ✗     |  ✓
      require_role("teacher")     |   ✗     |   ✓     |  ✓
      require_role("student",     |         |         |
        "teacher")                |   ✓     |   ✓     |  ✓

    【设计说明】
      使用工厂函数（而非直接定义多个 require_teacher / require_student）
      的好处是：一个函数支持任意角色组合，扩展新角色时无需新增函数。
      admin 始终通过是硬编码的安全策略，确保管理员不会被权限配置遗漏。
    """
    async def checker(user: User = Depends(get_current_user)) -> User:
        # 先通过 get_current_user 完成身份认证（未登录则已抛出 401）
        # 然后检查用户角色是否在允许列表中，或是否为 admin
        if user.role not in roles and user.role != "admin":
            # 角色不在允许列表中，也不是 admin → 拒绝访问
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return checker
