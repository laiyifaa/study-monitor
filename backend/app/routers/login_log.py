"""
登录日志查询模块 (login_log)
============================
功能：为管理员/教师提供登录日志查询接口，支持按时间、用户、设备维度筛选，
     用于设备兼容性问题排查（如某些设备视频无法播放时定位具体设备分布）。

API 列表：
    GET /api/login-logs/recent        — 最近 N 条登录日志（默认100，最多500）
    GET /api/login-logs/by-user/{uid} — 指定用户的登录历史（最近100条）
    GET /api/login-logs/stats         — 按设备/浏览器/OS 聚合统计
    GET /api/login-logs/failed        — 最近的失败登录记录（排查异常尝试）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import LoginLog
from app.utils.jwt_helper import require_role

router = APIRouter(prefix="/api/login-logs", tags=["登录日志"])


def _log_to_dict(log: LoginLog) -> dict:
    """将 LoginLog ORM 对象转为前端友好的字典"""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "account": log.account,
        "login_type": log.login_type,
        "ip": log.ip,
        "user_agent_raw": log.user_agent_raw,
        "device_platform": log.device_platform,
        "device_os": log.device_os,
        "browser": log.browser,
        "screen_size": log.screen_size,
        "in_dingtalk": bool(log.in_dingtalk),
        "in_wechat": bool(log.in_wechat),
        "is_mobile": bool(log.is_mobile),
        "network_type": log.network_type,
        "success": bool(log.success),
        "message": log.message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=500, description="返回记录数，默认100，最多500"),
    success: bool = Query(None, description="可选过滤：true=仅成功，false=仅失败"),
    current_user=Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取最近 N 条登录日志（按时间倒序）

    用途：快速浏览近期登录情况，发现异常登录或排查具体用户的设备信息。
    """
    stmt = select(LoginLog).order_by(desc(LoginLog.created_at)).limit(limit)
    if success is not None:
        stmt = stmt.where(LoginLog.success == success)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {"code": 0, "data": {"logs": [_log_to_dict(l) for l in logs], "count": len(logs)}}


@router.get("/by-user/{user_id}")
async def get_logs_by_user(
    user_id: int,
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定用户的登录历史（按时间倒序）

    用途：当某个学生反馈视频无法播放时，可通过 user_id 查询他最近用何设备登录，
         据此判断是否是特定设备/操作系统的兼容性问题。
    """
    stmt = (
        select(LoginLog)
        .where(LoginLog.user_id == user_id)
        .order_by(desc(LoginLog.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {"code": 0, "data": {"logs": [_log_to_dict(l) for l in logs], "count": len(logs)}}


@router.get("/stats")
async def get_login_stats(
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天，默认7天"),
    current_user=Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    按设备/浏览器/OS 聚合统计登录情况

    用途：从宏观层面看用户设备分布（钉钉占比/移动端占比/各浏览器占比），
         以及各类设备的登录成功率，为兼容性问题排查提供数据方向。
    """
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(days=days)

    # 按浏览器聚合
    browser_stmt = (
        select(
            LoginLog.browser,
            func.count().label("total"),
            func.sum(LoginLog.success).label("success_count"),
        )
        .where(LoginLog.created_at >= since)
        .group_by(LoginLog.browser)
        .order_by(desc("total"))
    )
    browser_result = await db.execute(browser_stmt)
    browser_stats = [
        {
            "browser": row.browser or "(未知)",
            "total": row.total,
            "success": int(row.success_count or 0),
            "fail": row.total - int(row.success_count or 0),
            "success_rate": round(int(row.success_count or 0) / row.total * 100, 1) if row.total else 0,
        }
        for row in browser_result
    ]

    # 按操作系统聚合
    os_stmt = (
        select(
            LoginLog.device_os,
            func.count().label("total"),
            func.sum(LoginLog.success).label("success_count"),
        )
        .where(LoginLog.created_at >= since)
        .group_by(LoginLog.device_os)
        .order_by(desc("total"))
    )
    os_result = await db.execute(os_stmt)
    os_stats = [
        {
            "os": row.device_os or "(未知)",
            "total": row.total,
            "success": int(row.success_count or 0),
            "success_rate": round(int(row.success_count or 0) / row.total * 100, 1) if row.total else 0,
        }
        for row in os_result
    ]

    # 按是否钉钉环境聚合
    dt_stmt = (
        select(
            LoginLog.in_dingtalk,
            func.count().label("total"),
            func.sum(LoginLog.success).label("success_count"),
        )
        .where(LoginLog.created_at >= since)
        .group_by(LoginLog.in_dingtalk)
    )
    dt_result = await db.execute(dt_stmt)
    dt_stats = [
        {
            "in_dingtalk": bool(row.in_dingtalk),
            "total": row.total,
            "success": int(row.success_count or 0),
        }
        for row in dt_result
    ]

    return {
        "code": 0,
        "data": {
            "days": days,
            "browser_stats": browser_stats,
            "os_stats": os_stats,
            "dingtalk_stats": dt_stats,
        },
    }


@router.get("/failed")
async def get_failed_logs(
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_role("teacher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取最近的失败登录记录（按时间倒序）

    用途：发现异常登录尝试（密码爆破猜测）、排查为何某些用户反复登录失败。
    """
    stmt = (
        select(LoginLog)
        .where(LoginLog.success == False)  # noqa: E712
        .order_by(desc(LoginLog.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {"code": 0, "data": {"logs": [_log_to_dict(l) for l in logs], "count": len(logs)}}
