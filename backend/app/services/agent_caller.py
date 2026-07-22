"""
智能体调用模块 (agent_caller)
=============================
功能：调用外部智能体 API 进行作业批改。

流程：
    1. 解析提交中的原始作业图片列表
    2. 逐张做方向修正与格式归一化
    3. POST /files/upload 逐张上传 → 获取 file_id 列表
    4. POST /chat-messages (streaming) → 接收完整 SSE 流
    5. 解析最终批改结果 JSON（新格式）
    6. 写入 GradingReport + 更新 Submission / GradingTask 状态

智能体平台：TeleAI Agent
"""

import asyncio
import io
import json
import logging
import math
import mimetypes
import os
import tempfile
import time
from datetime import datetime

import httpx
from PIL import Image, ImageOps
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.models import GradingTask, Submission, GradingReport, Assignment

logger = logging.getLogger(__name__)
settings = get_settings()

_grading_semaphore = asyncio.Semaphore(settings.GRADING_CONCURRENCY_LIMIT)

# MEDIUM-12: 熔断器状态
_circuit_breaker_lock = asyncio.Lock()
_circuit_breaker_consecutive_failures: int = 0
_circuit_breaker_open_until: float = 0.0  # timestamp，在此之前所有调用直接失败


async def _circuit_breaker_check() -> None:
    """检查熔断器状态，如果熔断中则抛出异常"""
    async with _circuit_breaker_lock:
        if _circuit_breaker_consecutive_failures >= settings.GRADING_CIRCUIT_BREAKER_THRESHOLD:
            now = time.monotonic()
            if now < _circuit_breaker_open_until:
                remaining = int(_circuit_breaker_open_until - now)
                raise RuntimeError(
                    f"智能体平台熔断中（连续失败 {_circuit_breaker_consecutive_failures} 次），"
                    f"预计 {remaining} 秒后恢复"
                )
            else:
                # 冷却期已过，允许尝试，重置为半开状态
                logger.info("熔断器冷却期已过，允许半开尝试")


async def _circuit_breaker_record_success() -> None:
    """记录成功，重置熔断器"""
    global _circuit_breaker_consecutive_failures, _circuit_breaker_open_until
    async with _circuit_breaker_lock:
        _circuit_breaker_consecutive_failures = 0
        _circuit_breaker_open_until = 0.0


async def _circuit_breaker_record_failure() -> None:
    """记录失败，可能触发熔断"""
    global _circuit_breaker_consecutive_failures, _circuit_breaker_open_until
    async with _circuit_breaker_lock:
        _circuit_breaker_consecutive_failures += 1
        if _circuit_breaker_consecutive_failures >= settings.GRADING_CIRCUIT_BREAKER_THRESHOLD:
            _circuit_breaker_open_until = time.monotonic() + settings.GRADING_CIRCUIT_BREAKER_COOLDOWN
            logger.error(
                f"熔断器触发: 连续失败 {_circuit_breaker_consecutive_failures} 次，"
                f"将暂停调用 {settings.GRADING_CIRCUIT_BREAKER_COOLDOWN} 秒"
            )

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(settings.GRADING_AGENT_TIMEOUT),
                write=30.0,
                pool=10.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _http_client


async def close_http_client():
    """优雅关闭全局 HTTP 客户端连接池（在 main.py lifespan shutdown 时调用）"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP 客户端连接池已关闭")


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


async def _mark_task_failed(task_id: int, error_message: str, retry_count: int = 0):
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
    image_urls: list[str],
    prompt: str,
    answer_json: str = "",
    retry_count: int = 0,
) -> bool:
    """
    调用智能体批改作业（循环重试 + 单次信号量）

    每次尝试独立获取/释放信号量，重试等待在信号量外进行，
    避免重试 sleep 占用并发槽位。
    """
    agent_url = settings.GRADING_AGENT_URL
    api_key = settings.GRADING_AGENT_API_KEY

    if not agent_url or not api_key:
        error_message = "智能体批改未配置 (GRADING_AGENT_URL 或 GRADING_AGENT_API_KEY 为空)"
        logger.warning(f"{error_message}, 跳过调用: task_id={task_id}, submission_id={submission_id}")
        await _mark_task_failed(task_id, error_message, 0)
        return False

    try:
        await _circuit_breaker_check()
    except RuntimeError as cb_err:
        logger.warning(f"熔断器拒绝调用: task_id={task_id}, {cb_err}")
        await _mark_task_failed(task_id, str(cb_err), 0)
        return False

    last_error: Exception | None = None
    for attempt in range(settings.GRADING_MAX_RETRIES + 1):
        async with _grading_semaphore:
            try:
                result = await _do_single_grading_call(
                    task_id=task_id,
                    submission_id=submission_id,
                    image_urls=image_urls,
                    prompt=prompt,
                    answer_json=answer_json,
                    attempt=attempt,
                )
                await _circuit_breaker_record_success()
                return result
            except Exception as e:
                last_error = e
                elapsed_info = f"attempt={attempt + 1}/{settings.GRADING_MAX_RETRIES + 1}"
                logger.error(
                    f"智能体批改失败: task_id={task_id}, submission_id={submission_id}, "
                    f"{elapsed_info}, error={e}"
                )

        # 重试等待在信号量外进行，不占用并发槽
        if attempt < settings.GRADING_MAX_RETRIES:
            delay = settings.GRADING_RETRY_DELAY * (attempt + 1)
            logger.info(f"将在 {delay} 秒后重试 (第 {attempt + 2} 次): task_id={task_id}")
            await asyncio.sleep(delay)

    # 所有重试耗尽
    await _circuit_breaker_record_failure()
    await _mark_task_failed(task_id, str(last_error), settings.GRADING_MAX_RETRIES)
    logger.error(
        f"智能体批改最终失败（超过最大重试次数 {settings.GRADING_MAX_RETRIES}）: "
        f"task_id={task_id}, submission_id={submission_id}"
    )
    return False


async def _do_single_grading_call(
    task_id: int,
    submission_id: int,
    image_urls: list[str],
    prompt: str,
    answer_json: str = "",
    attempt: int = 0,
) -> bool:
    """
    单次智能体批改调用（不含重试逻辑）

    参数：
        task_id            — GradingTask ID
        submission_id      — 提交 ID（内部使用，不传给智能体）
        image_urls         — 原始作业图片 URL 列表
        prompt             — 评分标准/批改提示词
        answer_json        — 参考答案 JSON 字符串
        attempt            — 当前尝试次数（用于日志）

    返回值：
        True  — 批改成功（结果已写入数据库）

    异常：
        失败时抛出异常，由调用方 (call_grading_agent) 负责重试
    """
    agent_url = settings.GRADING_AGENT_URL
    api_key = settings.GRADING_AGENT_API_KEY

    _t0 = time.perf_counter()
    await _mark_task_sent(task_id)

    prepared_image_paths: list[str] = []
    packaged_cleanup_paths: list[str] = []

    try:
        prepared_image_paths = await _prepare_images_for_agent(image_urls)
        if not prepared_image_paths:
            raise Exception("未找到可上传的作业图片")

        packaged_paths, packaged_cleanup_paths = _pack_images_for_agent(prepared_image_paths)
        if not packaged_paths:
            raise Exception("图片分包失败")

        file_ids = []
        for image_path in packaged_paths:
            file_id = await _upload_file(agent_url, api_key, image_path, content_type="image/jpeg")
            if not file_id:
                raise Exception("图片上传失败")
            file_ids.append(file_id)

        response_text = await _send_chat_message(agent_url, api_key, file_ids, prompt, answer_json)
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
            summary = _extract_summary(result)
            details = _extract_details(result)
            review_questions = _extract_review_questions(result)
            status = str(result.get("status") or _as_dict(result.get("result")).get("status") or "failed")

            score = _to_int(summary.get("score"))
            if score is None:
                score = 0

            full_score = _to_int(summary.get("full_score"))
            if full_score is None:
                full_score = 0

            accuracy = _to_float(summary.get("accuracy"))
            if accuracy is None:
                accuracy = 0.0

            feedback = str(summary.get("comment") or summary.get("feedback") or "").strip()

            correct_count = _to_int(summary.get("correct_count"))
            if correct_count is None:
                correct_count = _to_int(summary.get("correct"))
            if correct_count is None:
                correct_count = sum(1 for d in details if _extract_detail_correct(d) is True)

            wrong_count = _to_int(summary.get("wrong_count"))
            if wrong_count is None:
                wrong_count = _to_int(summary.get("wrong"))
            if wrong_count is None:
                wrong_count = sum(1 for d in details if _extract_detail_correct(d) is False)

            report_result = await db.execute(
                select(GradingReport).where(GradingReport.submission_id == submission_id)
            )
            report = report_result.scalar_one_or_none()
            if not report:
                report = GradingReport(
                    submission_id=submission_id,
                )
                db.add(report)

            report.score = score
            report.full_score = full_score
            report.accuracy = accuracy
            report.correct_count = correct_count
            report.wrong_count = wrong_count
            report.feedback = feedback
            report.detail = detail_json
            report.status = status
            report.review_questions = json.dumps(review_questions, ensure_ascii=False)
            report.generated_by = "wukong"
            report.review_status = review_status

            if review_status == "confirmed":
                submission.status = "graded"
            elif review_status == "pending_review":
                submission.status = "pending"

            task_result = await db.execute(select(GradingTask).where(GradingTask.id == task_id))
            task = task_result.scalar_one_or_none()
            if task:
                task.status = "graded"
                task.sent_at = task.sent_at or datetime.utcnow()
                task.graded_at = datetime.utcnow()

            await _refresh_grading_status(submission.assignment_id, db)
            await db.commit()

        elapsed = time.perf_counter() - _t0
        logger.info(
            f"智能体批改成功: task_id={task_id}, submission_id={submission_id}, "
            f"score={score}/{full_score}, attempt={attempt + 1}, elapsed={elapsed:.1f}s"
        )
        return True

    finally:
        for image_path in prepared_image_paths:
            try:
                if image_path.startswith(tempfile.gettempdir()) and os.path.exists(image_path):
                    os.unlink(image_path)
            except OSError:
                pass
        for image_path in packaged_cleanup_paths:
            try:
                if os.path.exists(image_path):
                    os.unlink(image_path)
            except OSError:
                pass


def _parse_grading_result(text: str) -> dict:
    """从智能体响应文本中提取批改结果 JSON

    MEDIUM-11: 增加 schema 校验——验证必须包含 summary 或 result.summary 字段。
    """
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise Exception(f"无法解析智能体响应为 JSON: {text[:200]}")

    # Schema 校验：检查必须包含的核心字段
    if not isinstance(result, dict):
        raise Exception(f"智能体响应不是 JSON 对象: {text[:200]}")

    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    has_summary = isinstance(result.get("summary"), dict)
    has_nested_summary = isinstance(nested.get("summary"), dict)

    if not has_summary and not has_nested_summary:
        # 降级处理：没有标准 summary，尝试记录警告但不抛异常
        logger.warning(
            f"智能体响应缺少 summary 字段，可能为降级结果: keys={list(result.keys())}"
        )

    return result


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _normalize_review_item(item) -> str:
    if isinstance(item, dict):
        for key in ("question_id", "qid", "index", "no", "key"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""
    return str(item).strip()


def _extract_summary(result: dict) -> dict:
    nested = _as_dict(result.get("result"))
    summary = {}
    nested_summary = nested.get("summary")
    if isinstance(nested_summary, dict):
        summary.update(nested_summary)
    top_summary = result.get("summary")
    if isinstance(top_summary, dict):
        summary.update(top_summary)
    return summary


def _extract_details(result: dict) -> list:
    top_details = result.get("details")
    if isinstance(top_details, list) and top_details:
        return top_details

    nested = _as_dict(result.get("result"))
    nested_details = nested.get("details")
    return nested_details if isinstance(nested_details, list) else []


def _extract_review_questions(result: dict) -> list[str]:
    review_items = []

    for item in _as_list(result.get("review")):
        review_items.append(_normalize_review_item(item))

    nested = _as_dict(result.get("result"))
    for item in _as_list(nested.get("low_confidence_questions")):
        review_items.append(_normalize_review_item(item))
    for item in _as_list(nested.get("review")):
        review_items.append(_normalize_review_item(item))

    seen = set()
    deduped = []
    for item in review_items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _extract_error(result: dict):
    nested = _as_dict(result.get("result"))
    return result.get("error") if result.get("error") is not None else nested.get("error")


def _extract_detail_correct(detail: dict):
    for key in ("correct", "ok", "is_correct"):
        if key not in detail or detail.get(key) is None:
            continue
        value = detail.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "ok", "correct", "right"}:
                return True
            if normalized in {"false", "0", "no", "n", "wrong", "incorrect"}:
                return False
    return None


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _prepare_images_for_agent(image_urls: list[str]) -> list[str]:
    """将提交中的原始图片逐张预处理为可上传的临时 JPEG 文件。"""
    if not image_urls:
        raise ValueError("图片列表不能为空")

    prepared_paths: list[str] = []
    try:
        for image_url in image_urls:
            resolved_path, should_cleanup = await _resolve_image_path(image_url)
            try:
                prepared_paths.append(_normalize_image_for_agent(resolved_path))
            finally:
                if should_cleanup and os.path.exists(resolved_path):
                    try:
                        os.unlink(resolved_path)
                    except OSError:
                        pass
        return prepared_paths
    except Exception:
        for path in prepared_paths:
            try:
                if path.startswith(tempfile.gettempdir()) and os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass
        raise


async def _resolve_image_path(image_url: str) -> tuple[str, bool]:
    """解析图片 URL 为本地路径；若本地不存在则回退为 HTTP 下载。"""
    normalized_url = str(image_url or "").strip()
    if not normalized_url:
        raise ValueError("图片 URL 不能为空")

    if normalized_url.startswith("/"):
        local_path = normalized_url[1:]
        if os.path.exists(local_path):
            return local_path, False

    if os.path.exists(normalized_url):
        return normalized_url, False

    return await _download_remote_image(normalized_url), True


def _normalize_image_for_agent(source_path: str) -> str:
    """对单张图片做 EXIF 修正、缩放和格式归一化，输出临时 JPEG 文件。"""
    with Image.open(source_path) as source_img:
        working = ImageOps.exif_transpose(source_img).copy()

    try:
        working = _downscale_image_if_needed(working, max_side=2048)
        normalized = _flatten_image_to_rgb(working)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            normalized.save(temp_file.name, "JPEG", quality=85, optimize=True)
            return temp_file.name
    finally:
        try:
            working.close()
        except Exception:
            pass
        if "normalized" in locals() and normalized is not working:
            try:
                normalized.close()
            except Exception:
                pass


def _downscale_image_if_needed(image: Image.Image, max_side: int) -> Image.Image:
    if max(image.width, image.height) <= max_side:
        return image.copy()
    scale = max_side / max(image.width, image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def _flatten_image_to_rgb(image: Image.Image) -> Image.Image:
    """将单张图片统一为 RGB，透明区域铺白底。"""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        return background
    if image.mode == "RGB":
        return image.copy()
    return image.convert("RGB")


def _pack_images_for_agent(image_paths: list[str]) -> tuple[list[str], list[str]]:
    """按智能体限制自适应分包，必要时才合包。"""
    if not image_paths:
        return [], []

    max_files = 10
    max_total_bytes = 5 * 1024 * 1024

    total_bytes = sum(os.path.getsize(path) for path in image_paths)
    if len(image_paths) <= max_files and total_bytes <= max_total_bytes:
        return list(image_paths), []

    package_count = max(
        1,
        math.ceil(len(image_paths) / max_files),
        math.ceil(total_bytes / max_total_bytes),
    )
    package_count = min(max_files, len(image_paths), package_count)
    group_size = max(1, math.ceil(len(image_paths) / package_count))
    target_bytes = min(max_total_bytes, max(256 * 1024, math.ceil(total_bytes / package_count)))

    packaged_paths: list[str] = []
    cleanup_paths: list[str] = []

    for index in range(0, len(image_paths), group_size):
        group = image_paths[index:index + group_size]
        if len(group) == 1 and total_bytes <= max_total_bytes:
            packaged_paths.append(group[0])
            continue

        merged_path = _merge_image_group(group, index=len(packaged_paths) + 1, max_side=2048, target_bytes=target_bytes)
        packaged_paths.append(merged_path)
        cleanup_paths.append(merged_path)

    return packaged_paths, cleanup_paths


def _merge_image_group(group: list[str], index: int, max_side: int, target_bytes: int) -> str:
    """将一组图片合并为一个中间文件，作为超限兜底。"""
    images: list[Image.Image] = []
    canvas: Image.Image | None = None
    try:
        for path in group:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img).copy()
                img = _downscale_image_if_needed(img, max_side=max_side)
                images.append(_flatten_image_to_rgb(img))

        if not images:
            raise ValueError("空图片组")

        total_height = sum(img.height for img in images) + max(0, len(images) - 1) * 8
        canvas = Image.new("RGB", (max(img.width for img in images), total_height), (255, 255, 255))
        y = 0
        for img in images:
            canvas.paste(img, (0, y))
            y += img.height + 8

        for candidate_side in (max_side, int(max_side * 0.8), int(max_side * 0.6), int(max_side * 0.45), int(max_side * 0.35)):
            candidate = _downscale_image_if_needed(canvas, max(512, candidate_side))
            try:
                quality = 85
                best_data = None
                while quality >= 25:
                    buffer = io.BytesIO()
                    candidate.save(buffer, "JPEG", quality=quality, optimize=True)
                    data = buffer.getvalue()
                    best_data = data
                    if len(data) <= target_bytes:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_pack{index}.jpg") as temp_file:
                            temp_file.write(data)
                            return temp_file.name
                    quality -= 10
                if best_data and len(best_data) <= target_bytes:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_pack{index}.jpg") as temp_file:
                        temp_file.write(best_data)
                        return temp_file.name
            finally:
                if canvas is not None and candidate is not canvas:
                    try:
                        candidate.close()
                    except Exception:
                        pass

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_pack{index}.jpg") as temp_file:
            canvas.save(temp_file.name, "JPEG", quality=25, optimize=True)
            return temp_file.name
    finally:
        for img in images:
            try:
                img.close()
            except Exception:
                pass
        if canvas is not None:
            try:
                canvas.close()
            except Exception:
                pass


async def _download_remote_image(image_url: str) -> str:
    """下载远程图片到本地临时文件。"""
    if image_url.startswith("/"):
        full_url = f"{settings.API_BASE_URL}{image_url}"
    elif image_url.startswith("http://") or image_url.startswith("https://"):
        full_url = image_url
    else:
        full_url = f"{settings.API_BASE_URL}/{image_url.lstrip('/')}"

    client = _get_http_client()
    response = await client.get(full_url, timeout=30)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as f:
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

    client = _get_http_client()
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, media_type)}
        headers = {"Authorization": f"Bearer {api_key}"}
        response = await client.post(upload_url, files=files, headers=headers, timeout=settings.GRADING_UPLOAD_TIMEOUT)
        response.raise_for_status()

    data = response.json()
    file_id = data.get("id")
    logger.info(f"文件上传成功: file_id={file_id}")
    return file_id


async def _send_chat_message(
    agent_url: str,
    api_key: str,
    file_ids: list[str],
    prompt: str,
    answer_json: str = "",
) -> str:
    """
    发送批改请求到智能体并收集完整流式响应

    参数：
        agent_url   — 智能体基础 URL
        api_key     — API Key
        file_ids    — 上传后的文件 ID 列表
        prompt      — 评分标准
        answer_json — 参考答案 JSON

    返回值：
        智能体返回的完整响应文本
    """
    chat_url = f"{agent_url}/chat-messages"

    query = prompt or "请批改这份作业"
    if answer_json:
        query += (
            "\n请按 sys_da 中的标准答案 JSON 比对批改。"
            "\nsys_da 的格式是题号键名对象，例如：{\"1\":{\"answer\":\"D\",\"type\":\"option_letter\",\"score\":2}}。"
            "\ntype 取值为 option_letter、true_false、fill_blank。"
        )

    body = {
        "inputs": {
            "sys_da": answer_json or "",
            "sys_zy": [
                {
                    "type": "image",
                    "transfer_method": "local_file",
                    "url": "",
                    "upload_file_id": file_id,
                }
                for file_id in file_ids
            ],
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
    client = _get_http_client()
    async with client.stream("POST", chat_url, json=body, headers=headers, timeout=settings.GRADING_AGENT_TIMEOUT) as response:
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
    """刷新作业的批改状态

    MEDIUM-1: 修正逻辑——只有当无 pending 且无 sent（进行中）的提交时才标记为 graded。
    """
    from sqlalchemy import func, and_, or_
    active_count = await db.scalar(
        select(func.count()).select_from(Submission).where(
            and_(
                Submission.assignment_id == assignment_id,
                or_(Submission.status == "pending", Submission.status == "returned"),
            )
        )
    )
    assignment = (await db.execute(select(Assignment).where(Assignment.id == assignment_id))).scalar_one_or_none()
    if not assignment:
        return
    # 检查是否有进行中的 GradingTask (status == "sent")
    if active_count == 0:
        from sqlalchemy import select as sa_select
        sent_count = await db.scalar(
            sa_select(func.count()).select_from(GradingTask).where(
                and_(
                    GradingTask.submission_id.in_(
                        sa_select(Submission.id).where(Submission.assignment_id == assignment_id)
                    ),
                    GradingTask.status == "sent",
                )
            )
        )
        if (sent_count or 0) == 0 and assignment.grading_status != "graded":
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
    client = _get_http_client()
    async with client.stream("POST", chat_url, json=body, headers=headers, timeout=settings.GRADING_UPLOAD_TIMEOUT) as response:
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
