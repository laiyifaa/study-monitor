"""
图片拼接模块 (image_stitcher)
=============================
功能：将多张作业图片纵向拼接为一张长图，供智能体批改使用。

在系统中的角色：
    智能体批改的前处理——学生提交多张图片，智能体只能接受单张图片URL，
    因此在调用智能体前，需要将多张图片拼接为一张长图。

拼接策略：
    - 统一宽度为 800px，按原始纵横比缩放
    - 纵向排列，图片之间加 10px 白色间隔
    - 输出为 JPEG 格式，quality=85
"""

import os
import logging
from typing import List

from PIL import Image

logger = logging.getLogger(__name__)

STITCHED_DIR = "uploads/homework/stitched"
STITCH_WIDTH = 800
STITCH_GAP = 10
STITCH_QUALITY = 85


def stitch_images(image_paths: List[str], output_filename: str) -> str:
    """
    将多张图片纵向拼接为一张长图

    参数：
        image_paths    — 本地文件路径列表（如 ["uploads/homework/abc.jpg", ...]）
        output_filename — 输出文件名（如 "stitched_123.jpg"）

    返回值：拼接后图片的 URL 路径（如 "/uploads/homework/stitched/stitched_123.jpg"）

    异常：如果所有图片都无法打开，抛出 ValueError
    """
    if not image_paths:
        raise ValueError("图片列表不能为空")

    os.makedirs(STITCHED_DIR, exist_ok=True)

    pil_images = []
    for path in image_paths:
        try:
            img = Image.open(path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            scale = STITCH_WIDTH / img.width
            new_height = int(img.height * scale)
            img = img.resize((STITCH_WIDTH, new_height), Image.LANCZOS)
            pil_images.append(img)
        except Exception as e:
            logger.warning(f"图片打开失败，跳过: {path}, 错误: {e}")

    if not pil_images:
        raise ValueError("所有图片均无法打开")

    total_height = sum(img.height for img in pil_images) + STITCH_GAP * (len(pil_images) - 1)
    result = Image.new("RGB", (STITCH_WIDTH, total_height), (255, 255, 255))

    y_offset = 0
    for img in pil_images:
        result.paste(img, (0, y_offset))
        y_offset += img.height + STITCH_GAP

    output_path = os.path.join(STITCHED_DIR, output_filename)
    result.save(output_path, "JPEG", quality=STITCH_QUALITY)

    for img in pil_images:
        img.close()
    result.close()

    logger.info(f"图片拼接完成: {len(pil_images)} 张 → {output_path}")
    return f"/uploads/homework/stitched/{output_filename}"


def image_url_to_local_path(url: str) -> str:
    """
    将图片 URL 转换为本地文件路径

    参数：url — 如 "/uploads/homework/abc.jpg"
    返回值：本地路径 — 如 "uploads/homework/abc.jpg"
    """
    if url.startswith("/"):
        return url[1:]
    return url
