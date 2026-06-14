#!/bin/bash
# ============================================================
# 从服务器获取真实视频文件名，更新 locustfile.py 中的 VIDEO_FILES
# ============================================================
#
# 用途：
#   压测脚本中的 VIDEO_FILES 列表需要与服务器上实际的视频文件名一致，
#   否则视频流压测会全部 404。此脚本通过 SSH 登录服务器，列出
#   uploads/videos/ 目录下的文件，并自动更新 locustfile.py。
#
# 使用方式：
#   ./fetch-video-names.sh
#
# 前置条件：
#   - SSH 可达 115.223.38.172:1000
#   - Python3 + paramiko 可用（或手动 SSH）
#
# ============================================================

set -e

SERVER="115.223.38.172"
SSH_PORT="1000"
REMOTE_DIR="/data/study-monitor/uploads/videos/"
LOCUST_FILE="$(cd "$(dirname "$0")" && pwd)/locustfile.py"

echo "从服务器获取视频文件列表..."
echo "  服务器: $SERVER:$SSH_PORT"
echo "  目录: $REMOTE_DIR"

# 尝试 SSH 连接获取文件列表
FILES=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p "$SSH_PORT" "root@$SERVER" "ls -1 $REMOTE_DIR 2>/dev/null" 2>/dev/null || echo "")

if [ -z "$FILES" ]; then
    echo "警告：无法通过 SSH 获取文件列表"
    echo "请手动 SSH 登录服务器执行："
    echo "  ssh -p $SSH_PORT root@$SERVER 'ls -1 $REMOTE_DIR'"
    echo ""
    echo "然后手动编辑 $LOCUST_FILE 中的 VIDEO_FILES 列表"
    exit 1
fi

# 解析文件列表为 Python 列表格式
PYTHON_LIST=""
while IFS= read -r file; do
    [ -z "$file" ] && continue
    if [ -z "$PYTHON_LIST" ]; then
        PYTHON_LIST="    \"$file\","
    else
        PYTHON_LIST="$PYTHON_LIST\n    \"$file\","
    fi
done <<< "$FILES"

echo "找到以下视频文件："
echo -e "$PYTHON_LIST"
echo ""

# 更新 locustfile.py 中的 VIDEO_FILES
if [ -n "$PYTHON_LIST" ]; then
    # 使用 Python 进行替换（更可靠）
    python3 -c "
import re
with open('$LOCUST_FILE', 'r') as f:
    content = f.read()

# 替换 VIDEO_FILES 列表
new_list = '''VIDEO_FILES = [
$PYTHON_LIST
]'''

pattern = r'VIDEO_FILES\s*=\s*\[.*?\]'
content = re.sub(pattern, new_list, content, count=1, flags=re.DOTALL)

with open('$LOCUST_FILE', 'w') as f:
    f.write(content)
print('locustfile.py 中 VIDEO_FILES 已更新')
"
fi
