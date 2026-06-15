"""
智能体调用模块 (agent_caller)
=============================
功能：调用外部智能体 API 进行作业批改。

调用流程：
    1. 下载拼接后的长图到本地临时文件
    2. POST /files/upload 上传图片 → 获取 file_id
    3. POST /chat-messages (streaming) → 接收 SSE 事件
    4. 解析第一个 SSE 事件获取 task_id
    5. 立即关闭连接
    6. 更新 GradingTask: agent_task_id, status=sent

智能体平台：TeleAI Agent
"""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.models import GradingTask

logger = logging.getLogger(__name__)
settings = get_settings()


async def call_grading_agent(
    task_id: int,
    submission_id: int,
    stitched_image_url: str,
    prompt: str,
    retry_count: int = 0,
) -> bool:
    """
    调用智能体批改作业

    参数：
        task_id            — GradingTask ID
        submission_id      — 提交 ID
        stitched_image_url — 拼接后的作业图片 URL
        prompt             — 评分标准/批改提示词
        retry_count        — 当前重试次数

    返回值：
        True  — 调用成功（已发送给智能体）
        False — 调用失败
    """
    agent_url = settings.GRADING_AGENT_URL
    api_key = settings.GRADING_AGENT_API_KEY

    if not agent_url or not api_key:
        logger.warning(
            f"智能体批改未配置 (GRADING_AGENT_URL 或 GRADING_AGENT_API_KEY 为空), "
            f"跳过调用: task_id={task_id}, submission_id={submission_id}"
        )
        return False

    try:
        image_path = await _download_image(stitched_image_url)
        if not image_path:
            raise Exception("图片下载失败")

        file_id = await _upload_file(agent_url, api_key, image_path)
        if not file_id:
            raise Exception("图片上传失败")

        agent_task_id = await _send_chat_message(agent_url, api_key, file_id, prompt, submission_id)
        if not agent_task_id:
            raise Exception("获取任务ID失败")

        async with async_session() as db:
            result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.agent_task_id = agent_task_id
                task.status = "sent"
                task.sent_at = datetime.utcnow()
                task.retry_count = retry_count
                await db.commit()

        logger.info(
            f"智能体调用成功: task_id={task_id}, submission_id={submission_id}, "
            f"agent_task_id={agent_task_id}"
        )
        return True

    except Exception as e:
        logger.error(
            f"智能体调用失败: task_id={task_id}, submission_id={submission_id}, "
            f"retry_count={retry_count}, error={str(e)}"
        )

        if retry_count < settings.GRADING_MAX_RETRIES:
            delay = settings.GRADING_RETRY_DELAY * (retry_count + 1)
            logger.info(f"将在 {delay} 秒后重试: task_id={task_id}")
            await asyncio.sleep(delay)
            return await call_grading_agent(
                task_id=task_id,
                submission_id=submission_id,
                stitched_image_url=stitched_image_url,
                prompt=prompt,
                retry_count=retry_count + 1,
            )
        else:
            async with async_session() as db:
                result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.retry_count = retry_count
                    await db.commit()

            logger.error(
                f"智能体调用最终失败（超过最大重试次数）: "
                f"task_id={task_id}, submission_id={submission_id}"
            )
            return False


async def _download_image(image_url: str) -> str:
    """
    下载图片到本地临时文件

    参数：
        image_url — 图片 URL（如 /uploads/homework/stitched/xxx.jpg）

    返回值：
        本地文件路径
    """
    if image_url.startswith("/"):
        local_path = image_url[1:]
        if os.path.exists(local_path):
            return local_path

    base_url = settings.API_BASE_URL
    full_url = f"{base_url}{image_url}" if image_url.startswith("/") else image_url

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(full_url)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(response.content)
            return f.name


async def _upload_file(agent_url: str, api_key: str, file_path: str) -> str:
    """
    上传文件到智能体平台

    参数：
        agent_url — 智能体基础 URL
        api_key   — API Key
        file_path — 本地文件路径

    返回值：
        file_id
    """
    upload_url = f"{agent_url}/files/upload"

    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "image/jpeg")}
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.post(upload_url, files=files, headers=headers)
            response.raise_for_status()

        data = response.json()
        file_id = data.get("id")
        logger.info(f"文件上传成功: file_id={file_id}")
        return file_id


async def _send_chat_message(agent_url: str, api_key: str, file_id: str, prompt: str, submission_id: int = 0) -> str:
    """
    发送批改请求到智能体

    参数：
        agent_url      — 智能体基础 URL
        api_key        — API Key
        file_id        — 上传的文件 ID
        prompt         — 评分标准
        submission_id  — 提交 ID，传给智能体用于回调

    返回值：
        task_id
    """
    chat_url = f"{agent_url}/chat-messages"

    body = {
        "inputs": {
            "submission_id": submission_id,
            "sys_zy": {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": file_id,
            }
        },
        "query": prompt or "请批改这份作业",
        "response_mode": "streaming",
        "conversation_id": "",
        "user": "study-monitor",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream("POST", chat_url, json=body, headers=headers) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                        task_id = data.get("task_id")
                        if task_id:
                            logger.info(f"获取到任务ID: task_id={task_id}")
                            return task_id
                    except json.JSONDecodeError:
                        continue

    return ""
