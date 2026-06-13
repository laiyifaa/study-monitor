"""
暑期在线学习平台 — 视频流极限压测专用脚本
=========================================

功能说明：
    专注于测试 Nginx sendfile + mp4 模块的并发视频分发能力。
    不做登录、心跳等 API 调用，仅大量并发请求视频文件，
    以找到服务器的带宽和磁盘 I/O 瓶颈。

    与主脚本 locustfile.py 的区别：
    - 主脚本模拟完整业务流程（登录+学习+心跳+视频）
    - 本脚本只压视频流，用于确定 Nginx sendfile 上限

使用方式：
    # Web UI 模式
    locust -f video_only.py --host=http://115.223.38.172:1001

    # 无头模式 — 800 并发视频流
    locust -f video_only.py --host=http://115.223.38.172:1001 \
        --headless -u 800 -r 50 -t 5m --csv=video_result

性能基线参考：
    服务器上行带宽：597 Mbps ≈ 74.6 MB/s
    HDD 随机读（800 并发）：~20 MB/s（磁盘瓶颈可能先于带宽到达）
    3 个视频文件总计 110MB
    单个 1080p 视频码率：~5 Mbps

理论分析：
    - 800 用户同时播放 5Mbps 视频 = 4000 Mbps >> 597 Mbps（带宽瓶颈）
    - 实际 Nginx sendfile 走内核，不经过 Python，效率远超 FastAPI FileResponse
    - HDD 随机读是最大瓶颈：800 个并发 seek → 吞吐量骤降
    - 解决方案：SSD 或 CDN 缓存热点视频
"""

import random
from locust import HttpUser, task, between

# 服务器上实际的视频文件
VIDEO_FILES = [
    "1_ea2096d5.mp4",
    "3_09f15471.mp4",
    "5_6f662c1e.mp4",
]


class VideoOnlyUser(HttpUser):
    """
    纯视频流用户 — 持续请求视频数据块

    模拟 HTML5 video 标签的流式播放行为：
    初始加载 + 持续拉取后续块。
    不走 API 认证，直接请求 Nginx 静态资源路径。
    """
    wait_time = between(0.5, 2)  # 视频播放器拉取间隔很短

    def on_start(self):
        """每次用户启动时选择一个视频"""
        self.video = random.choice(VIDEO_FILES)
        self.current_byte = random.randint(0, 50 * 1024 * 1024)  # 随机起始播放位置

    @task(10)
    def stream_chunk(self):
        """
        流式请求视频块 — 模拟播放器持续拉取

        每次请求 256KB~1MB 的视频数据块，
        使用 HTTP Range 头模拟真实播放器行为。
        """
        chunk_size = random.randint(256 * 1024, 1024 * 1024)
        start = self.current_byte
        end = start + chunk_size - 1

        with self.client.get(
            f"/uploads/videos/{self.video}",
            headers={"Range": f"bytes={start}-{end}"},
            name="/uploads/videos/* [Range]",
            stream=True,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 206):
                resp.success()
            elif resp.status_code == 404:
                resp.failure(f"视频文件不存在: {self.video}")
            else:
                resp.failure(f"异常: HTTP {resp.status_code}")

        # 播放位置前进
        self.current_byte = end + 1
        # 超过 100MB（视频长度上限）则回到开头
        if self.current_byte > 100 * 1024 * 1024:
            self.current_byte = 0

    @task(3)
    def initial_load(self):
        """
        视频初始加载 — 播放器首次打开视频文件

        浏览器首次加载会发送 Range: bytes=0- 请求，
        Nginx 返回 200 或 206 + Content-Length。
        """
        with self.client.get(
            f"/uploads/videos/{self.video}",
            headers={"Range": "bytes=0-"},
            name="/uploads/videos/* [初始加载]",
            stream=True,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 206):
                resp.success()
            else:
                resp.failure(f"初始加载失败: HTTP {resp.status_code}")

    @task(1)
    def seek_random(self):
        """
        随机拖动进度条 — 模拟用户 seek 行为

        播放器 seek 时会发送新的 Range 请求到目标位置，
        这会导致 HDD 随机读，是最慢的操作。
        """
        seek_pos = random.randint(0, 80 * 1024 * 1024)
        chunk = random.randint(128 * 1024, 512 * 1024)

        with self.client.get(
            f"/uploads/videos/{self.video}",
            headers={"Range": f"bytes={seek_pos}-{seek_pos + chunk - 1}"},
            name="/uploads/videos/* [Seek]",
            stream=True,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 206):
                resp.success()
            elif resp.status_code == 416:
                # Range Not Satisfiable — seek 超出文件大小
                resp.success()  # 这是正常情况，不算失败
            else:
                resp.failure(f"Seek 失败: HTTP {resp.status_code}")
