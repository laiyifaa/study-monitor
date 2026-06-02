"""
定时任务模块 (scheduler)
========================
功能：管理后台定时任务，目前包含心跳日志自动清理。

在系统中的角色：
    运维保障层——自动执行数据维护任务，防止 heartbeat_logs 表无限增长导致磁盘爆满。
    通过 APScheduler 的 AsyncIOScheduler 在 FastAPI lifespan 中启动/关闭。

定时任务列表：
    - cleanup_heartbeat_logs：每天凌晨3点清理超过30天的心跳日志

扩展说明：
    如需新增定时任务，在此模块中定义 async 函数并调用 scheduler.add_job() 注册即可。
    常见扩展场景：每日学习报告推送、过期课程自动归档等。
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, text

from app.database import async_session
from app.models.models import HeartbeatLog

logger = logging.getLogger(__name__)

# APScheduler 异步调度器实例
scheduler = AsyncIOScheduler()

# 心跳日志保留天数，超过此天数的记录将被自动清理
# 30天足够支撑争议申诉和审计回溯，同时控制表体积
HEARTBEAT_RETENTION_DAYS = 30


async def cleanup_heartbeat_logs():
    """
    清理过期心跳日志 —— 删除超过 HEARTBEAT_RETENTION_DAYS 天的 heartbeat_logs 记录

    执行频率：每天凌晨 3:00
    清理策略：按 timestamp 字段判断，删除早于保留天数的全部记录
    日志输出：清理前记录总数 → 清理行数 → 清理后总数

    为什么用分批删除：
        单条 DELETE 可能源于表数据量巨大（百万级）导致锁表时间过长，
        影响正常的心跳写入。分批每次删 10000 条，降低锁竞争。

    为什么用原生 SQL 而非 ORM：
        MySQL 不支持 DELETE ... WHERE id IN (SELECT ... LIMIT) 子查询，
        使用原生 SQL 的 DELETE ... WHERE ... LIMIT 更简洁高效。
    """
    cutoff = datetime.utcnow() - timedelta(days=HEARTBEAT_RETENTION_DAYS)
    total_deleted = 0
    batch_size = 10000

    try:
        async with async_session() as db:
            # 清理前统计
            count_before = await db.scalar(
                select(func.count()).select_from(HeartbeatLog)
            )

            # 分批删除，使用原生 SQL 避免 MySQL 不支持 IN+LIMIT 的问题
            while True:
                result = await db.execute(
                    text(
                        "DELETE FROM heartbeat_logs "
                        "WHERE timestamp < :cutoff "
                        "LIMIT :batch_size"
                    ),
                    {"cutoff": cutoff, "batch_size": batch_size}
                )
                deleted = result.rowcount
                total_deleted += deleted
                await db.commit()

                if deleted < batch_size:
                    break  # 本批次不足 batch_size，说明已删完

            # 清理后统计
            count_after = await db.scalar(
                select(func.count()).select_from(HeartbeatLog)
            )

            logger.info(
                f"心跳日志清理完成: 删除 {total_deleted} 条 "
                f"(保留 {HEARTBEAT_RETENTION_DAYS} 天), "
                f"清理前 {count_before} → 清理后 {count_after}"
            )

    except Exception as e:
        logger.error(f"心跳日志清理失败: {e}")


def start_scheduler():
    """
    启动定时任务调度器

    在 FastAPI lifespan 的启动阶段调用，注册所有定时任务并启动调度器。
    调用位置：app/main.py 的 lifespan() 函数中。
    """
    # 注册心跳日志清理任务：每天凌晨3点执行
    scheduler.add_job(
        cleanup_heartbeat_logs,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_heartbeat_logs",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务调度器已启动: 心跳日志清理(每天03:00, 保留%d天)", HEARTBEAT_RETENTION_DAYS)


def stop_scheduler():
    """
    停止定时任务调度器

    在 FastAPI lifespan 的关闭阶段调用，优雅终止所有定时任务。
    调用位置：app/main.py 的 lifespan() 函数中。
    """
    scheduler.shutdown(wait=False)
    logger.info("定时任务调度器已停止")
