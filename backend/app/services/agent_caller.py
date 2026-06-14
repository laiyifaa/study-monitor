"""
智能体调用模块 (agent_caller)
=============================
功能：调用外部智能体 API 进行作业批改。

在系统中的角色：
    批改任务的执行者——将拼接后的作业图片URL和评分标准发送给智能体，
    智能体完成批改后回调 /api/homework/grading-callback 写入结果。

当前状态：
    智能体 API 的地址、请求格式、响应格式尚未确定，
    本模块为占位实现，仅记录日志。待 API 确定后填充具体逻辑。
"""

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


async def call_grading_agent(submission_id: int, stitched_image_url: str, prompt: str):
    """
    调用智能体批改作业（占位实现）

    参数：
        submission_id      — 提交 ID，用于回调时关联
        stitched_image_url — 拼接后的作业图片 URL
        prompt             — 评分标准/批改提示词

    返回值：无（异步调用，智能体完成后回调 grading-callback）

    待实现：
        1. 根据 GRADING_AGENT_URL 构造请求
        2. 发送 POST 请求（图片URL + 提示词 + submission_id + callback_url）
        3. 处理响应和异常
    """
    settings = get_settings()
    agent_url = settings.GRADING_AGENT_URL

    if not agent_url:
        logger.warning(
            f"智能体批改未配置 (GRADING_AGENT_URL 为空), "
            f"跳过调用: submission_id={submission_id}"
        )
        return

    logger.info(
        f"智能体批改调用 (占位): submission_id={submission_id}, "
        f"image_url={stitched_image_url}, prompt_len={len(prompt)}, "
        f"agent_url={agent_url}"
    )

    # TODO: 待智能体 API 确定后实现具体调用逻辑
    # 示例：
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         agent_url,
    #         json={
    #             "submission_id": submission_id,
    #             "image_url": stitched_image_url,
    #             "prompt": prompt,
    #             "callback_url": f"{settings.API_BASE_URL}/api/homework/grading-callback",
    #         },
    #         timeout=30,
    #     )
    #     response.raise_for_status()
