"""
图片拼接模块 (image_stitcher)
=============================
功能：将多张作业图片纵向拼接为一张长图，供智能体批改使用。

在系统中的角色：
    智能体批改的前处理——学生提交多张图片，智能体只能接受单张图片URL，
    因此在调用智能体前，需要将多张图片拼接为一张长图。

拼接策略：
    1. EXIF 方向修正（无条件）——修正手机拍照的 EXIF 方向标记
    2. OCR 方向检测（可选）——检测文字朝向，自动旋转
       - 优先使用 Tesseract OSD
       - 降级为水平投影法（numpy 梯度方差分析）
    3. 统一宽度为 800px，按原始纵横比缩放
    4. 纵向排列，图片之间加 10px 白色间隔
    5. 输出为 JPEG 格式，quality=85

降级策略：
    tesseract + numpy 全装 → EXIF + Tesseract OSD + 旋转 + 拼接
    仅 numpy            → EXIF + 水平投影法 + 旋转 + 拼接
    都没装              → EXIF + 直接拼接（和旧版行为一致）
"""

import os
import logging
from typing import List

from PIL import Image, ImageOps

# numpy — 可选，水平投影法降级用
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# pytesseract — 可选，OCR 方向检测用
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

logger = logging.getLogger(__name__)

STITCHED_DIR = "uploads/homework/stitched"
STITCH_WIDTH = 800
STITCH_GAP = 10
STITCH_QUALITY = 85


def detect_orientation(img: Image.Image) -> int:
    """
    检测图片文字朝向，返回需要旋转的角度: 0, 90, 或 -90。

    检测策略（双阶段降级）：
        阶段 1：Tesseract OSD — 对 0°/90°/-90° 三个方向做 OCR 方向检测，
                取 confidence 最高的角度。
        阶段 2：水平投影法 — 用 numpy 计算各方向旋转后的水平投影梯度方差，
                方差最大的方向即为文字水平方向。
        阶段 3：都不可用 — 返回 0（不旋转）。

    参数：
        img — PIL Image 对象（已经过 EXIF 修正）

    返回值：
        需要旋转的角度: 0, 90, 或 -90
    """
    # ── 预处理：缩放 + DPI ──
    processed_img = img.copy()
    max_dim = 2000
    if processed_img.width > max_dim or processed_img.height > max_dim:
        scale = max_dim / max(processed_img.width, processed_img.height)
        new_w = int(processed_img.width * scale)
        new_h = int(processed_img.height * scale)
        processed_img = processed_img.resize((new_w, new_h), Image.LANCZOS)
    processed_img.info["dpi"] = (300, 300)

    # ── 阶段 1：Tesseract OSD ──
    if HAS_TESSERACT:
        try:
            result = _detect_with_tesseract_osd(processed_img)
            if result is not None:
                processed_img.close()
                return result
        except Exception as e:
            logger.debug(f"Tesseract OSD 检测异常: {e}")

        logger.debug("Tesseract OSD 无法确定方向，尝试水平投影法")

    # ── 阶段 2：水平投影法 ──
    if HAS_NUMPY:
        try:
            result = _detect_with_projection(processed_img)
            processed_img.close()
            return result
        except Exception as e:
            logger.debug(f"水平投影法检测异常: {e}")

    processed_img.close()
    return 0


def _detect_with_tesseract_osd(processed_img: Image.Image) -> int | None:
    """使用 Tesseract OSD 检测文字方向"""
    gray = processed_img.convert("L")
    gray = gray.point(lambda x: 0 if x < 140 else 255, "1")
    osd_img = gray.convert("RGB")
    osd_img.info["dpi"] = (300, 300)

    results = []
    for angle in [0, 90, -90]:
        test_img = osd_img.rotate(angle, expand=True) if angle != 0 else osd_img
        try:
            osd = pytesseract.image_to_osd(
                test_img,
                output_type=pytesseract.Output.DICT,
                config="--psm 0",
            )
            confidence = osd.get("confidence", 0)
            rotate = osd.get("rotate", 0)
            logger.debug(
                f"  [OSD] angle={angle:>3d}°  rotate={rotate}  confidence={confidence:.1f}"
            )
            results.append({
                "angle": angle,
                "rotate": rotate,
                "confidence": confidence,
            })
        except Exception:
            continue

    osd_img.close()
    gray.close()

    if not results:
        return None

    # 有 confidence > 0 的结果，取最高的
    confident = [r for r in results if r["confidence"] > 0]
    if confident:
        best = max(confident, key=lambda r: r["confidence"])
        rotate_deg = best["rotate"]
        if rotate_deg == 270:
            final_angle = -90
        elif rotate_deg in (90, 180):
            final_angle = rotate_deg
        else:
            final_angle = 0
        logger.debug(f"  [OSD] → 旋转 {final_angle}° (confidence={best['confidence']:.1f})")
        return final_angle

    # confidence 全为 0，找 rotate=0 的结果
    correct = [r for r in results if r["rotate"] == 0]
    if correct:
        non_zero = [r for r in results if r["rotate"] != 0]
        if non_zero:
            logger.debug(f"  [OSD] → 旋转 {correct[0]['angle']}° (rotate=0 确认)")
            return correct[0]["angle"]

    return None


def _detect_with_projection(processed_img: Image.Image) -> int:
    """使用水平投影法检测文字方向（numpy 梯度方差分析）"""
    gray = processed_img.convert("L")
    arr = np.array(gray)

    best_var = -1.0
    best_angle = 0

    for angle in [0, 90, -90]:
        if angle != 0:
            rotated = gray.rotate(angle, expand=True)
            test_arr = np.array(rotated)
            rotated.close()
        else:
            test_arr = arr

        # 水平投影：每行的平均灰度值
        projection = test_arr.mean(axis=1)
        # 梯度（相邻行的差值），波动越大说明行间距越明显
        gradient = np.abs(np.diff(projection))
        var = float(np.var(gradient))

        logger.debug(f"  [投影] angle={angle:>3d}°  梯度方差={var:.4f}")

        if var > best_var:
            best_var = var
            best_angle = angle

    gray.close()

    if best_angle != 0:
        direction = "顺时针" if best_angle < 0 else "逆时针"
        logger.debug(f"  [投影] → {direction} {abs(best_angle)}° (方差={best_var:.4f})")
    else:
        logger.debug(f"  [投影] → 无需旋转 (方差={best_var:.4f})")

    return best_angle


def stitch_images(
    image_paths: List[str],
    output_filename: str,
    use_ocr: bool = True,
) -> str:
    """
    将多张图片纵向拼接为一张长图

    参数：
        image_paths     — 本地文件路径列表（如 ["uploads/homework/abc.jpg", ...]）
        output_filename — 输出文件名（如 "stitched_123.jpg"）
        use_ocr         — 是否启用 OCR 方向检测（默认 True）
                          需要 tesseract 或 numpy，缺失时自动降级

    返回值：拼接后图片的 URL 路径（如 "/uploads/homework/stitched/stitched_123.jpg"）

    异常：如果所有图片都无法打开，抛出 ValueError
    """
    if not image_paths:
        raise ValueError("图片列表不能为空")

    os.makedirs(STITCHED_DIR, exist_ok=True)

    # 检查 OCR 可用性
    ocr_enabled = use_ocr and (HAS_TESSERACT or HAS_NUMPY)
    if use_ocr and not ocr_enabled:
        logger.warning(
            "OCR 方向检测不可用: 未安装 pytesseract 或 numpy，"
            "将仅使用 EXIF 修正。安装方式: pip install pytesseract numpy"
        )

    pil_images = []
    for path in image_paths:
        try:
            img = Image.open(path)

            # 1. EXIF 方向修正（解决手机拍照方向错误）
            img = ImageOps.exif_transpose(img)

            # 2. OCR 方向检测 + 旋转（可选）
            if ocr_enabled:
                logger.debug(f"[OCR] {path} ({img.width}x{img.height}) 检测文字方向...")
                angle = detect_orientation(img)
                if angle != 0:
                    img = img.rotate(angle, expand=True)
                    logger.info(f"图片旋转 {angle}°: {path}")

            # 3. 颜色模式转换
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # 4. 等比缩放到统一宽度
            scale = STITCH_WIDTH / img.width
            new_height = int(img.height * scale)
            img = img.resize((STITCH_WIDTH, new_height), Image.LANCZOS)
            pil_images.append(img)

        except Exception as e:
            logger.warning(f"图片打开失败，跳过: {path}, 错误: {e}")

    if not pil_images:
        raise ValueError("所有图片均无法打开")

    # ── 纵向拼接 ──
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
