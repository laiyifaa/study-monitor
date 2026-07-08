#!/bin/bash
# 批量创建章节并上传视频
# 用法: bash upload_course.sh

API="http://115.223.38.90:1001/api"
KEY="sk_e3c4b87af275631b7f7df5c4fdad1681170c68166ee4a70490b87cd017e54529"
SRC="/Users/sh/Desktop/CTWZ/AI 中心项目/study-monitor/src"

upload_course() {
  local course_id=$1
  local course_dir=$2
  local shift_num=$3  # 视频文件名中提取课时的偏移

  echo "=========================================="
  echo "处理课程 ID=$course_id, 目录=$course_dir"
  echo "=========================================="

  # 按文件名排序获取视频
  local videos=()
  while IFS= read -r f; do
    videos+=("$f")
  done < <(find "$course_dir" -maxdepth 2 -name "*.mp4" -o -name "*.webm" -o -name "*.mov" 2>/dev/null | sort)

  local total=${#videos[@]}
  echo "找到 $total 个视频文件"

  local idx=0
  for video in "${videos[@]}"; do
    idx=$((idx + 1))
    local filename=$(basename "$video")
    local title="第${idx}讲"

    echo ""
    echo "--- [$idx/$total] $title ---"
    echo "  文件: $filename ($(du -h "$video" | cut -f1))"

    # 创建章节
    echo "  创建章节..."
    local resp=$(curl -s --max-time 15 -X POST "$API/sections" \
      -H "X-API-Key: $KEY" \
      -H "Content-Type: application/json" \
      -d "{\"course_id\":$course_id,\"title\":\"$title\",\"sort_order\":$idx,\"video_type\":\"local\"}")

    local section_id=$(echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('id','ERROR'))" 2>/dev/null)

    if [ "$section_id" = "ERROR" ] || [ -z "$section_id" ]; then
      echo "  ❌ 创建章节失败: $resp"
      continue
    fi
    echo "  章节ID=$section_id"

    # 上传视频
    echo "  上传视频中..."
    local upload_resp=$(curl -s --max-time 600 -X POST "$API/sections/$section_id/upload-video" \
      -H "X-API-Key: $KEY" \
      -F "file=@$video" \
      --progress-bar 2>&1)

    if echo "$upload_resp" | grep -q '"code":0'; then
      echo "  ✅ 上传成功"
    else
      echo "  ❌ 上传失败: $upload_resp"
    fi
  done

  echo ""
  echo "课程 $course_id 完成！共处理 $idx 个视频"
}

# 化学 - 12个视频(扁平目录)
upload_course 18 "$SRC/2026初高中衔接化学" 0

# 语文 - 12个视频(子目录结构，第10课无视频)
upload_course 19 "$SRC/2026初高中衔接语文" 0

# 英语 - 12个视频(子目录: 英语/初高中衔接英语/初高中衔接英语 视频/)
upload_course 20 "$SRC/英语/初高中衔接英语" 0

echo ""
echo "=========================================="
echo "全部课程上传完成！"
echo "=========================================="
