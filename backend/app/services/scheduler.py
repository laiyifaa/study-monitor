"""
定时任务模块 (scheduler)
=======================
功能：管理后台定时任务，目前包含心跳日志自动清理和作业自动批改。

在系统中的角色：
    运维保障层——自动执行数据维护任务，防止 heartbeat_logs 表无限增长导致磁盘爆满。
    批改触发层——到达作业截止时间后，自动触发智能体批改流程。

定时任务列表：
    - cleanup_heartbeat_logs：每天凌晨3点清理超过30天的心跳日志
    - trigger_auto_grading：每分钟检查是否有到期作业需要自动批改

扩展说明：
    如需新增定时任务，在此模块中定义 async 函数并调用 scheduler.add_job() 注册即可。
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, text, and_

from app.config import get_settings
from app.database import async_session
from app.models.models import HeartbeatLog, Assignment, Submission, GradingTask
from app.services.image_stitcher import stitch_images, image_url_to_local_path
from app.services.agent_caller import call_grading_agent

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()

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


async def trigger_auto_grading():
    """
    自动批改到期作业（并发处理 + GradingTask 状态追踪）

    执行频率：每分钟
    逻辑：
        1. 查找所有 deadline <= now 且 status=published 且 grading_triggered=False 的作业
        2. 对每个作业，查找所有 pending 的提交
        3. 并发处理每个提交：
           a. 检查是否已有 GradingTask，跳过已处理的
           b. 创建 GradingTask (status=pending)
           c. 取出图片 URL 列表，转换为本地路径
           d. 调用 image_stitcher 拼接为长图，保存 URL 到 GradingTask
           e. 调用 agent_caller 发给智能体（带重试）
        4. 标记作业 grading_triggered=True，防止重复触发
    """
    try:
        async with async_session() as db:
            now = datetime.utcnow()
            result = await db.execute(
                select(Assignment).where(
                    and_(
                        Assignment.status == "published",
                        Assignment.deadline <= now,
                        Assignment.grading_triggered == False,
                    )
                )
            )
            assignments = result.scalars().all()

            if not assignments:
                return

            for assignment in assignments:
                if assignment.grading_mode == "manual":
                    assignment.grading_triggered = True
                    await db.commit()
                    logger.info(f"作业 {assignment.id} 批改模式为人工，跳过智能体")
                    continue

                sub_result = await db.execute(
                    select(Submission).where(
                        and_(
                            Submission.assignment_id == assignment.id,
                            Submission.status == "pending",
                            Submission.is_latest == True,
                        )
                    )
                )
                submissions = sub_result.scalars().all()

                if not submissions:
                    assignment.grading_triggered = True
                    await db.commit()
                    logger.info(f"作业 {assignment.id} 无待批改提交，标记已触发")
                    continue

                tasks = [
                    _process_submission(submission, assignment)
                    for submission in submissions
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                success_count = sum(1 for r in results if r is True)
                fail_count = sum(1 for r in results if r is False or isinstance(r, Exception))

                assignment.grading_triggered = True
                await db.commit()
                logger.info(
                    f"作业 {assignment.id} 批改任务已触发: "
                    f"共 {len(submissions)} 个提交, 成功 {success_count}, 失败 {fail_count}"
                )

    except Exception as e:
        logger.error(f"自动批改任务执行失败: {e}")


async def _process_submission(submission: Submission, assignment: Assignment) -> bool:
    """
    处理单个提交的批改任务

    参数：
        submission  — 提交对象
        assignment  — 作业对象

    返回值：
        True  — 成功发送给智能体
        False — 处理失败
    """
    try:
        async with async_session() as db:
            existing_task = await db.execute(
                select(GradingTask).where(GradingTask.submission_id == submission.id)
            )
            if existing_task.scalar_one_or_none():
                logger.info(f"提交 {submission.id} 已有 GradingTask，跳过")
                return True

            images = json.loads(submission.images)
            if not images:
                logger.warning(f"提交 {submission.id} 无图片，跳过")
                return False

            local_paths = [image_url_to_local_path(url) for url in images]
            output_filename = f"stitched_{submission.id}.jpg"
            stitched_url = stitch_images(local_paths, output_filename)

            task = GradingTask(
                submission_id=submission.id,
                stitched_image_url=stitched_url,
                status="pending",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

        success = await call_grading_agent(
            task_id=task.id,
            submission_id=submission.id,
            stitched_image_url=stitched_url,
            prompt=assignment.grading_prompt,
        )
        return success

    except Exception as e:
        logger.error(f"提交 {submission.id} 批改处理失败: {e}")
        return False


def start_scheduler():
    """
    启动定时任务调度器

    在 FastAPI lifespan 的启动阶段调用，注册所有定时任务并启动调度器。
    调用位置：app/main.py 的 lifespan() 函数中。
    """
    scheduler.add_job(
        cleanup_heartbeat_logs,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_heartbeat_logs",
        replace_existing=True,
    )

    scheduler.add_job(
        trigger_auto_grading,
        "cron",
        minute="*",
        id="trigger_auto_grading",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "定时任务调度器已启动: 心跳日志清理(每天03:00, 保留%d天), 自动批改(每分钟检查)",
        HEARTBEAT_RETENTION_DAYS,
    )


def stop_scheduler():
    """
    停止定时任务调度器

    在 FastAPI lifespan 的关闭阶段调用，优雅终止所有定时任务。
    调用位置：app/main.py 的 lifespan() 函数中。
    """
    scheduler.shutdown(wait=False)
    logger.info("定时任务调度器已停止")
