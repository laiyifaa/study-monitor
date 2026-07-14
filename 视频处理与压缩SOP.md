---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'ce5f8e8c-68a0-4b04-8503-324c9aa3fe00'
  PropagateID: 'ce5f8e8c-68a0-4b04-8503-324c9aa3fe00'
  ReservedCode1: '055c6e55-49ff-45f9-a692-1709211fb75a'
  ReservedCode2: '055c6e55-49ff-45f9-a692-1709211fb75a'
---

# 视频处理与压缩 SOP

> 适用项目：在线学习平台（study-monitor）
> 最后更新：2026-07-14

---

## 一、背景

平台课程视频通过 Nginx 提供流媒体服务，存储路径为服务器 `/data/study-monitor/uploads/videos/`（容器内 `/app/uploads/videos/`）。视频需满足以下条件才能正常播放：

1. **moov atom 前置**（faststart）：浏览器需先读取 moov 才能播放，moov 在文件末尾会导致加载缓慢。
2. **编码格式兼容**：H.264 视频 + AAC 音频，容器格式 MP4。
3. **文件大小合理**：录屏课分辨率通常 1080p，码率偏高，压缩可节省 5-7 倍空间。

---

## 二、前置条件

- 服务器 SSH 访问权限（端口 1000）
- 服务器已安装 `ffmpeg`、`ffprobe`、`python3`
- 数据库访问：`study_monitor` / `Sm2026Prod_Secure`

---

## 三、操作步骤

### Step 1：获取数据库中所有视频记录

```bash
# 查询所有 local 类型视频文件名
docker exec -i study-monitor-mysql mysql \
  -u study_monitor -pSm2026Prod_Secure \
  --default-character-set=utf8mb4 study_monitor \
  -N -e "SELECT video_url FROM sections WHERE video_type='local';"
```

### Step 2：扫描所有视频的编码与 faststart 状态

在本地（Mac）创建扫描脚本，SCP 到服务器执行：

```bash
#!/bin/bash
# scan_videos.sh — 批量检测视频编码与 faststart 状态

VIDEOS_DIR="/data/study-monitor/uploads/videos"

for f in $(ls "$VIDEOS_DIR"/*.mp4 2>/dev/null | sort -V); do
  fname=$(basename "$f")
  size=$(ls -lh "$f" | awk '{print $5}')

  # 检测编码
  codec=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)
  acodec=$(ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)

  # 检测 moov atom 位置
  moov_offset=$(python3 -c "
import struct
f = open('$f', 'rb')
offset = 0
while True:
    f.seek(offset)
    data = f.read(8)
    if len(data) < 8: break
    box_size = struct.unpack('>I', data[:4])[0]
    box_type = data[4:8].decode('ascii', errors='replace')
    if box_type == 'moov':
        print(offset)
        break
    if box_type in ('ftyp','moov','mdat','free','skip'):
        offset += box_size
    else:
        offset += box_size if box_size > 0 else 1
    if box_size == 0: break
f.close()
" 2>/dev/null)

  # moov 在文件前 1MB 内视为 faststart
  if [ -n "$moov_offset" ] && [ "$moov_offset" -lt 1048576 ]; then
    fast="OK"
  else
    fast="NEED_FIX"
  fi

  echo "$fname | $size | v:$codec a:$acodec | faststart:$fast"
done
```

```bash
# 上传并执行
scp -P 1000 scan_videos.sh root@115.223.38.90:/tmp/
ssh -p 1000 root@115.223.38.90 'bash /tmp/scan_videos.sh'
```

### Step 3：分类处理

根据扫描结果，将视频分为三类：

| 分类 | 条件 | 处理方式 |
|------|------|----------|
| 无需处理 | `faststart=OK` 且 `v:h264 a:aac` | 跳过 |
| 仅需 Remux | `faststart=NEED_FIX` 但编码正确 | `ffmpeg -i input.mp4 -c copy -movflags +faststart output.mp4` |
| 需要转码 | 非 H.264 或非 AAC | `ffmpeg -i input.mp4 -c:v libx264 -crf 28 -r 20 -c:a aac -movflags +faststart output.mp4` |

### Step 4：批量处理脚本

```bash
#!/bin/bash
# batch_process.sh — 批量 remux / transcode + faststart

SRC_DIR="/data/study-monitor/uploads/videos"
OUT_DIR="/data/study-monitor/uploads/processed"

mkdir -p "$OUT_DIR"

for f in $(ls "$SRC_DIR"/*.mp4 2>/dev/null | sort -V); do
  fname=$(basename "$f")

  # 检测 faststart
  moov_offset=$(python3 -c "
import struct
fi = open('$f', 'rb')
offset = 0
while True:
    fi.seek(offset)
    data = fi.read(8)
    if len(data) < 8: break
    box_size = struct.unpack('>I', data[:4])[0]
    box_type = data[4:8].decode('ascii', errors='replace')
    if box_type == 'moov': print(offset); break
    if box_type in ('ftyp','moov','mdat','free','skip'): offset += box_size
    else: offset += box_size if box_size > 0 else 1
    if box_size == 0: break
fi.close()
" 2>/dev/null)

  # 检测编码
  codec=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)
  acodec=$(ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)

  need_transcode=0
  need_faststart=0

  [ "$codec" != "h264" ] && need_transcode=1
  [ "$acodec" != "aac" ] && need_transcode=1
  [ -z "$moov_offset" ] || [ "$moov_offset" -ge 1048576 ] && need_faststart=1

  if [ $need_transcode -eq 0 ] && [ $need_faststart -eq 0 ]; then
    echo "SKIP: $fname (already OK)"
    continue
  fi

  if [ $need_transcode -eq 1 ]; then
    echo "TRANSCODE: $fname"
    ffmpeg -i "$f" -c:v libx264 -crf 28 -r 20 -c:a aac -movflags +faststart -y "$OUT_DIR/$fname" 2>/dev/null
  else
    echo "REMUX: $fname"
    ffmpeg -i "$f" -c copy -movflags +faststart -y "$OUT_DIR/$fname" 2>/dev/null
  fi
done
```

**关键参数说明：**

| 参数 | 值 | 说明 |
|------|----|------|
| `-crf 28` | 恒定质量模式 | 数值越高质量越低，28 对录屏课几乎没有视觉损失 |
| `-r 20` | 帧率 20fps | 录屏课 20fps 足够，大幅减少文件体积 |
| `-c copy` | 仅复制流 | 不重新编码，仅重排 moov atom，速度极快 |
| `-movflags +faststart` | moov 前置 | 将 moov atom 移到文件开头，浏览器可立即播放 |

### Step 5：替换服务器视频

```bash
# 1. 备份原始目录（可选，磁盘允许时做）
# cp -r /data/study-monitor/uploads/videos /data/study-monitor/uploads/videos_bak

# 2. 用处理后的文件覆盖原始文件
cp -f /data/study-monitor/uploads/processed/*.mp4 /data/study-monitor/uploads/videos/

# 3. 确保文件权限正确
chmod 644 /data/study-monitor/uploads/videos/*.mp4
```

### Step 6：验证

```bash
#!/bin/bash
# verify_videos.sh — 验证所有视频 faststart + HTTP 可访问性

VIDEOS_DIR="/data/study-monitor/uploads/videos"

# 数据库中的视频文件名
DB_FILES=$(docker exec -i study-monitor-mysql mysql \
  -u study_monitor -pSm2026Prod_Secure \
  --default-character-set=utf8mb4 study_monitor \
  -N -e "SELECT video_url FROM sections WHERE video_type='local';" 2>/dev/null)

OK=0; FAIL=0; MISSING=0

for f in $DB_FILES; do
  filepath="$VIDEOS_DIR/$f"

  # 文件存在性
  if [ ! -f "$filepath" ]; then
    echo "MISSING: $f"
    MISSING=$((MISSING+1))
    continue
  fi

  # faststart 检测
  moov_offset=$(python3 -c "
import struct
fi = open('$filepath', 'rb')
offset = 0
while True:
    fi.seek(offset)
    data = fi.read(8)
    if len(data) < 8: break
    box_size = struct.unpack('>I', data[:4])[0]
    box_type = data[4:8].decode('ascii', errors='replace')
    if box_type == 'moov': print(offset); break
    if box_type in ('ftyp','moov','mdat','free','skip'): offset += box_size
    else: offset += box_size if box_size > 0 else 1
    if box_size == 0: break
fi.close()
" 2>/dev/null)

  if [ -n "$moov_offset" ] && [ "$moov_offset" -lt 1048576 ]; then
    OK=$((OK+1))
  else
    echo "FASTSTART FAIL: $f (moov at $moov_offset)"
    FAIL=$((FAIL+1))
  fi
done

echo ""
echo "结果: OK=$OK, FASTSTART_FAIL=$FAIL, MISSING=$MISSING"
```

### Step 7：清理

```bash
# 删除处理中间目录
rm -rf /data/study-monitor/uploads/processed

# 删除本地下载的临时视频文件（如果是本地处理模式）
# rm -rf ~/Desktop/temp_videos/
```

---

## 四、大文件特殊处理（校园视频 >200MB）

对于超大文件（如校园宣传片），单独压缩：

```bash
ffmpeg -i campus_video_original.mp4 \
  -c:v libx264 -crf 28 -preset slow \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  campus_video_compressed.mp4
```

- `crf 28 + preset slow`：比默认 preset 更精细，压缩率更高
- 压缩后部署：`scp -P 1001` 上传，`chmod 644` 确保权限

---

## 五、注意事项

1. **磁盘空间**：批量处理前检查剩余空间，processed 目录会占用与原文件等同的空间
2. **排序问题**：文件名含中文数字时，使用 `sort -V`（自然排序）避免顺序错乱
3. **替换时机**：建议在低峰期操作，替换期间视频短暂不可用
4. **备份原则**：首次操作建议保留 `videos_bak`，确认无误后删除
5. **权限**：所有视频文件必须 `644` 权限，否则 Nginx 无法读取
6. **钉钉WebView**：视频播放走 Range 请求，faststart 是必须条件，否则首帧加载慢

---

## 六、快速参考命令

```bash
# 单文件 faststart 修复
ffmpeg -i input.mp4 -c copy -movflags +faststart output.mp4

# 单文件转码压缩（录屏课推荐参数）
ffmpeg -i input.mp4 -c:v libx264 -crf 28 -r 20 -c:a aac -movflags +faststart output.mp4

# 检测 moov 位置
python3 -c "
import struct
f = open('video.mp4', 'rb')
offset = 0
while True:
    f.seek(offset)
    data = f.read(8)
    if len(data) < 8: break
    bs = struct.unpack('>I', data[:4])[0]
    bt = data[4:8].decode('ascii', errors='replace')
    if bt == 'moov': print(f'moov at {offset}'); break
    if bt in ('ftyp','moov','mdat','free','skip'): offset += bs
    else: offset += bs if bs > 0 else 1
    if bs == 0: break
f.close()
"

# 查看 DB 中视频数量
docker exec -i study-monitor-mysql mysql -u study_monitor -pSm2026Prod_Secure \
  --default-character-set=utf8mb4 study_monitor \
  -N -e "SELECT COUNT(*) FROM sections WHERE video_type='local';"
```