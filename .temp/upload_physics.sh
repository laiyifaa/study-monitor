#!/bin/bash
# 上传物理课程 —— 使用自然排序（sort -V）避免字典序乱序
# 乱序根因：find | sort 按字典序排列，"第10课"排在"第1课"前面
# 修复：用 sort -V (version/natural sort) 使数字正确排序

API="http://115.223.38.90:1001/api"
KEY="sk_e3c4b87af275631b7f7df5c4fdad1681170c68166ee4a70490b87cd017e54529"
COURSE_ID=21
SRC="/Users/sh/Desktop/CTWZ/AI 中心项目/study-monitor/src/2026初高中衔接物理"

echo "=========================================="
echo "上传物理课程 ID=$COURSE_ID"
echo "源目录: $SRC"
echo "=========================================="

# 用 sort -V 实现自然排序：第1课→第2课→...→第10课→第11课→第12课
videos=()
while IFS= read -r f; do
  videos+=("$f")
done < <(find "$SRC" -maxdepth 2 -name "*.mp4" | sort -V)

total=${#videos[@]}
echo "找到 $total 个视频文件"

# 先预览排序结果
echo ""
echo "--- 排序预览 ---"
for i in "${!videos[@]}"; do
  echo "  [$((i+1))] $(basename "${videos[$i]}")"
done
echo ""

idx=0
for video in "${videos[@]}"; do
  idx=$((idx + 1))
  filename=$(basename "$video")
  # 从目录名提取标题，如 "第1课——走进高中物理" → "第1课 走进高中物理"
  dirname=$(basename "$(dirname "$video")")
  title="$dirname"

  echo "--- [$idx/$total] $title ---"
  echo "  文件: $filename ($(du -h "$video" | cut -f1))"

  # 创建章节
  echo "  创建章节..."
  resp=$(curl -s --max-time 15 -X POST "$API/sections" \
    -H "X-API-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"course_id\":$COURSE_ID,\"title\":\"$title\",\"sort_order\":$idx,\"video_type\":\"local\"}")

  section_id=$(echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('id','ERROR'))" 2>/dev/null)

  if [ "$section_id" = "ERROR" ] || [ -z "$section_id" ]; then
    echo "  ❌ 创建章节失败: $resp"
    continue
  fi
  echo "  章节ID=$section_id"

  # 上传视频
  echo "  上传视频中..."
  upload_resp=$(curl -s --max-time 600 -X POST "$API/sections/$section_id/upload-video" \
    -H "X-API-Key: $KEY" \
    -F "file=@$video")

  if echo "$upload_resp" | grep -q '"code":0'; then
    echo "  ✅ 上传成功"
  else
    echo "  ❌ 上传失败: $upload_resp"
  fi
done

echo ""
echo "=========================================="
echo "物理课程上传完成！共处理 $idx 个视频"
echo "=========================================="
