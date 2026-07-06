"""
智能体调用模块 (agent_caller)
=============================
功能：调用外部智能体 API 进行作业批改。

流程：
    1. 下载拼接后的长图到本地临时文件
    2. POST /files/upload 上传图片 → 获取 file_id
    3. POST /chat-messages (streaming) → 接收完整 SSE 流
    4. 解析最终批改结果 JSON（新格式）
    5. 写入 GradingReport + 更新 Submission / GradingTask 状态

智能体平台：TeleAI Agent
"""

import asyncio
import json
import logging
import mimetypes
import os
import tempfile
from datetime import datetime

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.models import GradingTask, Submission, GradingReport, Assignment

logger = logging.getLogger(__name__)
settings = get_settings()


async def _mark_task_sent(task_id: int):
    async with async_session() as db:
        task_result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            return

        task.status = "sent"
        task.sent_at = task.sent_at or datetime.utcnow()
        task.error_message = ""
        await db.commit()


async def _mark_task_failed(task_id: int, error_message: str, retry_count: int):
    async with async_session() as db:
        result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return

        task.status = "failed"
        task.error_message = error_message
        task.retry_count = retry_count
        await db.commit()


async def call_grading_agent(
    task_id: int,
    submission_id: int,
    stitched_image_url: str,
    prompt: str,
    answer_json: str = "",
    retry_count: int = 0,
) -> bool:
    """
    调用智能体批改作业（同步等待完整流式响应，直接落库）

    参数：
        task_id            — GradingTask ID
        submission_id      — 提交 ID（内部使用，不传给智能体）
        stitched_image_url — 拼接后的作业图片 URL
        prompt             — 评分标准/批改提示词
        answer_json        — 参考答案 JSON 字符串
        retry_count        — 当前重试次数

    返回值：
        True  — 批改成功（结果已写入数据库）
        False — 批改失败
    """
    agent_url = settings.GRADING_AGENT_URL
    api_key = settings.GRADING_AGENT_API_KEY

    if not agent_url or not api_key:
        error_message = "智能体批改未配置 (GRADING_AGENT_URL 或 GRADING_AGENT_API_KEY 为空)"
        logger.warning(
            f"{error_message}, 跳过调用: task_id={task_id}, submission_id={submission_id}"
        )
        await _mark_task_failed(task_id, error_message, retry_count)
        return False

    try:
        await _mark_task_sent(task_id)

        image_path = await _download_image(stitched_image_url)
        if not image_path:
            raise Exception("图片下载失败")

        file_id = await _upload_file(agent_url, api_key, image_path, content_type="image/jpeg")
        if not file_id:
            raise Exception("图片上传失败")

        response_text = await _send_chat_message(agent_url, api_key, file_id, prompt, answer_json)
        if not response_text:
            raise Exception("智能体未返回有效响应")

        result = _parse_grading_result(response_text)

        async with async_session() as db:
            submission_result = await db.execute(select(Submission).where(Submission.id == submission_id))
            submission = submission_result.scalar_one_or_none()
            if not submission:
                raise Exception(f"提交 {submission_id} 不存在")

            assignment_result = await db.execute(
                select(Assignment).where(Assignment.id == submission.assignment_id)
            )
            assignment = assignment_result.scalar_one_or_none()

            review_status = "confirmed"
            if assignment and assignment.grading_mode == "hybrid":
                review_status = "pending_review"

            detail_json = json.dumps(result, ensure_ascii=False)
            review_qs = json.dumps(result.get("review", []), ensure_ascii=False)
            summary = result.get("summary", {})
            details = result.get("details", [])
            status = result.get("status", "failed")

            correct_count = sum(1 for d in details if d.get("ok"))
            wrong_count = sum(1 for d in details if not d.get("ok"))

            report = GradingReport(
                submission_id=submission_id,
                score=summary.get("score", 0),
                full_score=summary.get("full_score", 0),
                accuracy=summary.get("accuracy", 0.0),
                correct_count=correct_count,
                wrong_count=wrong_count,
                feedback="",
                detail=detail_json,
                status=status,
                review_questions=review_qs,
                generated_by="wukong",
                review_status=review_status,
            )
            db.add(report)

            if review_status == "confirmed":
                submission.status = "graded"

            task_result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
            task = task_result.scalar_one_or_none()
            if task:
                task.status = "graded"
                task.sent_at = task.sent_at or datetime.utcnow()
                task.graded_at = datetime.utcnow()

            await _refresh_grading_status(submission.assignment_id, db)
            await db.commit()

        logger.info(
            f"智能体批改成功: task_id={task_id}, submission_id={submission_id}, "
            f"score={summary.get('score', 0)}/{summary.get('full_score', 0)}"
        )
        return True

    except Exception as e:
        logger.error(
            f"智能体批改失败: task_id={task_id}, submission_id={submission_id}, "
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
                answer_json=answer_json,
                retry_count=retry_count + 1,
            )
        else:
            await _mark_task_failed(task_id, str(e), retry_count)

            logger.error(
                f"智能体批改最终失败（超过最大重试次数）: "
                f"task_id={task_id}, submission_id={submission_id}"
            )
            return False


def _parse_grading_result(text: str) -> dict:
    """从智能体响应文本中提取批改结果 JSON"""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise Exception(f"无法解析智能体响应为 JSON: {text[:200]}")


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


async def _upload_file(agent_url: str, api_key: str, file_path: str, content_type: str | None = None) -> str:
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

    media_type = content_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, media_type)}
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.post(upload_url, files=files, headers=headers)
            response.raise_for_status()

        data = response.json()
        file_id = data.get("id")
        logger.info(f"文件上传成功: file_id={file_id}")
        return file_id


async def _send_chat_message(
    agent_url: str,
    api_key: str,
    file_id: str,
    prompt: str,
    answer_json: str = "",
) -> str:
    """
    发送批改请求到智能体并收集完整流式响应

    参数：
        agent_url   — 智能体基础 URL
        api_key     — API Key
        file_id     — 上传的文件 ID
        prompt      — 评分标准
        answer_json — 参考答案 JSON

    返回值：
        智能体返回的完整响应文本
    """
    chat_url = f"{agent_url}/chat-messages"

    query = prompt or "请批改这份作业"
    if answer_json:
        query += (
            "\n请先 OCR 识别学生作业图片，再按 sys_da 中的标准答案 JSON 比对批改。"
            "\nsys_da 的格式是题号键名对象，例如：{\"1\":{\"answer\":\"D\",\"type\":\"option_letter\",\"score\":2}}。"
            "\ntype 取值为 option_letter、true_false、fill_blank。"
        )

    body = {
        "inputs": {
            "sys_da": answer_json or "",
            "sys_zy": {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": file_id,
            }
        },
        "query": query,
        "response_mode": "streaming",
        "conversation_id": "",
        "user": "study-monitor",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    chunks: list[str] = []
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", chat_url, json=body, headers=headers) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    for key in ("answer", "text", "message", "content"):
                        value = data.get(key)
                        if isinstance(value, str):
                            chunks.append(value)
                            break

    full_text = "".join(chunks).strip()
    logger.info(f"智能体流式响应收集完成: {len(full_text)} 字符")
    return full_text


async def _refresh_grading_status(assignment_id: int, db):
    """刷新作业的批改状态"""
    from sqlalchemy import func, and_
    pending_count = await db.scalar(
        select(func.count()).select_from(Submission).where(
            and_(Submission.assignment_id == assignment_id, Submission.status == "pending")
        )
    )
    if pending_count == 0:
        assignment = (await db.execute(select(Assignment).where(Assignment.id == assignment_id))).scalar_one_or_none()
        if assignment and assignment.grading_status != "graded":
            assignment.grading_status = "graded"


async def parse_answer_file_with_agent(file_path: str) -> dict:
    """Upload a PDF/Word answer file to the existing grading agent and return answer JSON."""
    agent_url = settings.GRADING_AGENT_URL
    api_key = settings.GRADING_AGENT_API_KEY
    if not agent_url or not api_key:
        raise RuntimeError("GRADING_AGENT_URL 或 GRADING_AGENT_API_KEY 未配置")

    file_id = await _upload_file(agent_url, api_key, file_path)
    if not file_id:
        raise RuntimeError("答案文件上传智能体失败")

    content = await _send_answer_parse_message(agent_url, api_key, file_id)
    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("智能体未返回有效答案 JSON")
    return parsed


async def _send_answer_parse_message(agent_url: str, api_key: str, file_id: str) -> str:
    chat_url = f"{agent_url}/chat-messages"
    body = {
        "inputs": {
            "sys_answer_file": {
                "type": "document",
                "transfer_method": "local_file",
                "upload_file_id": file_id,
            }
        },
        "query": (
            "请从答案文件中提取标准答案，只返回严格 JSON，不要输出说明文字。"
            "格式：{\"version\":1,\"items\":[{\"no\":\"1\",\"type\":\"choice|fill|judge\",\"answer\":\"A\"}]}。"
            "type 只能是 choice、fill、judge。"
        ),
        "response_mode": "streaming",
        "conversation_id": "",
        "user": "study-monitor-answer-parser",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    chunks: list[str] = []
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", chat_url, json=body, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip() or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                for key in ("answer", "text", "message", "content"):
                    value = data.get(key)
                    if isinstance(value, str):
                        chunks.append(value)

    return "".join(chunks).strip()


def _extract_json_object(text: str) -> dict:
    if not text:
        raise ValueError("empty answer parser response")

    candidates = [text.strip()]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("answer parser response is not JSON")
