"""
暑期在线学习平台 — Locust 压测脚本
===================================

功能说明：
    模拟真实用户行为对在线学习平台进行压力测试，覆盖三个核心场景：
    1. 学生学习流程：登录→获取课程→开始会话→心跳上报→结束会话
    2. 视频流并发：模拟多用户同时下载/播放视频文件（测试 Nginx sendfile 带宽瓶颈）
    3. 教师看板：登录→查看班级统计→查看未完成学生

使用方式：
    # Web UI 模式（推荐，可实时查看图表）
    locust -f locustfile.py --host=http://115.223.38.172:1001

    # 无头模式（适合云端批量运行）
    locust -f locustfile.py --host=http://115.223.38.172:1001 \
        --headless -u 200 -r 20 -t 5m --csv=result

    # 分布式模式（Master，在主控机运行）
    locust -f locustfile.py --host=http://115.223.38.172:1001 \
        --master --expect-workers=3

    # 分布式模式（Worker，在从属机运行）
    locust -f locustfile.py --worker --master-host=<MASTER_IP>

参数说明：
    -u / --users       : 并发用户总数
    -r / --spawn-rate  : 每秒启动用户数
    -t / --run-time    : 运行时长（如 5m, 1h）
    --csv              : 导出 CSV 报告前缀

压测策略（按并发量递进）：
    第一轮：200 并发 — 验证系统基础承载能力
    第二轮：400 并发 — 发现瓶颈点（CPU/内存/带宽）
    第三轮：800 并发 — 极限测试，确认 Nginx sendfile + HDD 上限

注意事项：
    - 负载生成机的下行带宽必须远大于服务器的上行带宽（597Mbps），
      否则压不到服务器极限。建议使用 3+ 台天翼云 VM（每台 200Mbps）。
    - 视频流测试使用 range 请求模拟真实播放器行为。
    - 心跳上报间隔 30 秒，与前端一致。

测试账号（已在系统中创建）：
    学生：王小明/123456, 李小红/123456, 刘大伟/123456, 陈思思/123456, 赵天宇/123456
    教师：张老师/teacher123
    管理员：管理员/admin123
"""

import json
import time
import random
import logging
from locust import HttpUser, task, between, tag, events
from locust.runners import MasterRunner, WorkerRunner

# ============================================================
# 配置常量
# ============================================================

# 测试账号池 — 学生账号用于学习流程，教师账号用于看板
STUDENT_ACCOUNTS = [
    {"username": "王小明", "password": "123456"},
    {"username": "李小红", "password": "123456"},
    {"username": "刘大伟", "password": "123456"},
    {"username": "陈思思", "password": "123456"},
    {"username": "赵天宇", "password": "123456"},
]

TEACHER_ACCOUNTS = [
    {"username": "张老师", "password": "teacher123"},
    {"username": "管理员", "password": "admin123"},
]

# 已知课程 ID（与服务器数据一致，确保请求合法）
# 如课程数据有变动，需更新此列表
COURSE_IDS = [1, 2, 3, 4, 5]

# 已知视频文件名（用于视频流压测）
# 如有新视频上传，需更新此列表
VIDEO_FILES = [
    "1_ea2096d5.mp4",
    "3_09f15471.mp4",
    "5_6f662c1e.mp4",
]

# 心跳上报间隔（秒），与前端 useStudyTracker 保持一致
HEARTBEAT_INTERVAL = 30

# 每次心跳模拟的视频播放秒数（略有抖动，模拟真实播放）
VIDEO_PLAY_SECONDS_PER_BEAT = 30


# ============================================================
# 工具函数
# ============================================================

def pick_student():
    """随机选择一个学生账号"""
    return random.choice(STUDENT_ACCOUNTS)


def pick_teacher():
    """随机选择一个教师账号"""
    return random.choice(TEACHER_ACCOUNTS)


def pick_course():
    """随机选择一个课程ID"""
    return random.choice(COURSE_IDS)


def pick_video():
    """随机选择一个视频文件名"""
    return random.choice(VIDEO_FILES)


# ============================================================
# 学生用户 — 模拟完整学习流程
# ============================================================

class StudentUser(HttpUser):
    """
    学生学习者 — 模拟真实学生的学习行为链路

    行为链路：
        1. 浏览器登录获取 JWT Token
        2. 获取课程列表
        3. 随机进入一门课程，创建学习会话
        4. 持续上报心跳（每30秒一次，模拟视频播放）
        5. 学习一段时间后结束会话
        6. 查看自己的学习进度

    权重：占压测用户总数的 70%（主要场景）
    """
    # 两次学习之间的等待时间（模拟学生翻看课程列表、选课等操作）
    wait_time = between(5, 15)
    weight = 70  # 在混合场景中占 70%

    def on_start(self):
        """
        用户初始化 — 登录系统获取 JWT Token
        每个虚拟用户启动时执行一次
        """
        account = pick_student()
        self.username = account["username"]
        self.token = None
        self.session_id = None
        self.current_course_id = None
        self.video_current_time = 0.0  # 模拟视频播放进度（秒）

        # 第一步：登录
        resp = self.client.post(
            "/api/auth/login",
            json={"username": account["username"], "password": account["password"]},
            name="/api/auth/login [学生登录]",
        )
        try:
            data = resp.json()
            if data.get("code") == 0:
                self.token = data["data"]["token"]
                logging.debug(f"学生 {self.username} 登录成功")
            else:
                logging.warning(f"学生 {self.username} 登录失败: {data.get('msg')}")
        except Exception as e:
            logging.error(f"学生登录响应解析失败: {e}")

    def _headers(self):
        """构造带 JWT Token 的请求头"""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    @tag("student", "learn")
    def start_and_study(self):
        """
        核心学习流程 — 开始学习 + 心跳 + 结束

        这是最重要的测试场景，模拟了完整的会话生命周期：
        start → beat(×N) → end

        每次心跳间隔 HEARTBEAT_INTERVAL 秒（30秒），
        模拟前端视频播放器的定时上报行为。
        """
        if not self.token:
            return

        course_id = pick_course()
        self.current_course_id = course_id
        self.video_current_time = random.uniform(0, 300)  # 随机起始播放位置

        # --- 开始学习会话 ---
        resp = self.client.post(
            "/api/heartbeat/start",
            json={"course_id": course_id},
            headers=self._headers(),
            name="/api/heartbeat/start",
        )
        try:
            data = resp.json()
            if data.get("code") == 0:
                self.session_id = data["data"]["session_id"]
            else:
                return  # 会话创建失败，跳过心跳
        except Exception:
            return

        # --- 心跳循环：模拟持续学习 ---
        # 随机学习 2~6 个心跳周期（1~3 分钟），模拟真实学习时长分布
        beat_count = random.randint(2, 6)
        for i in range(beat_count):
            # 模拟视频播放进度增长（30秒 + 随机抖动）
            self.video_current_time += VIDEO_PLAY_SECONDS_PER_BEAT + random.uniform(-2, 2)

            # 构造心跳请求体（与前端 useStudyTracker 一致）
            beat_data = {
                "course_id": course_id,
                "is_playing": True,
                "is_page_visible": True,
                "video_current_time": round(self.video_current_time, 2),
                "action": "heartbeat",
            }

            # 心跳上报
            self.client.post(
                "/api/heartbeat/beat",
                json=beat_data,
                headers=self._headers(),
                name="/api/heartbeat/beat",
            )

            # 随机模拟暂停事件（10% 概率）
            if random.random() < 0.1:
                self.client.post(
                    "/api/heartbeat/beat",
                    json={
                        "course_id": course_id,
                        "is_playing": False,
                        "is_page_visible": True,
                        "video_current_time": round(self.video_current_time, 2),
                        "action": "pause",
                    },
                    headers=self._headers(),
                    name="/api/heartbeat/beat [暂停]",
                )
                time.sleep(random.uniform(3, 10))  # 暂停 3~10 秒
                # 恢复播放
                self.client.post(
                    "/api/heartbeat/beat",
                    json={
                        "course_id": course_id,
                        "is_playing": True,
                        "is_page_visible": True,
                        "video_current_time": round(self.video_current_time, 2),
                        "action": "play",
                    },
                    headers=self._headers(),
                    name="/api/heartbeat/beat [恢复播放]",
                )

            # 等待下一个心跳周期（缩短为 2 秒以加速压测，真实场景为 30 秒）
            # 注意：此处用 time.sleep 会阻塞 Locust 的协程调度，
            # 但 Locust 的 gevent 协程模型可以正确处理
            time.sleep(2)  # 压测加速：2秒替代30秒真实间隔

        # --- 结束学习会话 ---
        self.client.post(
            "/api/heartbeat/end",
            json={
                "course_id": course_id,
                "is_playing": False,
                "is_page_visible": True,
                "video_current_time": round(self.video_current_time, 2),
                "action": "end",
            },
            headers=self._headers(),
            name="/api/heartbeat/end",
        )
        self.session_id = None

    @task(3)
    @tag("student", "browse")
    def browse_courses(self):
        """
        浏览课程列表 — 模拟学生查看可选课程

        这是一个轻量级 API，用于测试基础读性能
        """
        if not self.token:
            return
        self.client.get(
            "/api/courses?status=active",
            headers=self._headers(),
            name="/api/courses [学生浏览]",
        )

    @task(2)
    @tag("student", "progress")
    def check_my_progress(self):
        """
        查看学习进度 — 模拟学生查看自己的学习完成情况
        """
        if not self.token:
            return
        self.client.get(
            "/api/stats/my-progress",
            headers=self._headers(),
            name="/api/stats/my-progress",
        )


# ============================================================
# 教师用户 — 模拟管理看板操作
# ============================================================

class TeacherUser(HttpUser):
    """
    教师管理者 — 模拟教师在管理后台查看统计数据的操作

    行为链路：
        1. 浏览器登录获取 JWT Token
        2. 查看班级学习概览
        3. 查看每日统计汇总
        4. 查看未完成学生列表
        5. 查看课程列表

    权重：占压测用户总数的 10%（教师数量远少于学生）
    """
    wait_time = between(10, 30)  # 教师浏览间隔较长
    weight = 10  # 在混合场景中占 10%

    def on_start(self):
        """教师登录"""
        account = pick_teacher()
        self.username = account["username"]
        self.token = None

        resp = self.client.post(
            "/api/auth/login",
            json={"username": account["username"], "password": account["password"]},
            name="/api/auth/login [教师登录]",
        )
        try:
            data = resp.json()
            if data.get("code") == 0:
                self.token = data["data"]["token"]
        except Exception:
            pass

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)
    @tag("teacher", "dashboard")
    def view_class_overview(self):
        """查看班级学习概览 — 教师最常用的接口"""
        if not self.token:
            return
        course_id = pick_course()
        self.client.get(
            f"/api/stats/class-overview?course_id={course_id}",
            headers=self._headers(),
            name="/api/stats/class-overview",
        )

    @task(2)
    @tag("teacher", "stats")
    def view_daily_summary(self):
        """查看每日学习统计"""
        if not self.token:
            return
        course_id = pick_course()
        self.client.get(
            f"/api/stats/daily-summary?course_id={course_id}",
            headers=self._headers(),
            name="/api/stats/daily-summary",
        )

    @task(2)
    @tag("teacher", "stats")
    def view_incomplete_students(self):
        """查看未完成学生列表"""
        if not self.token:
            return
        course_id = pick_course()
        self.client.get(
            f"/api/stats/incomplete-students?course_id={course_id}",
            headers=self._headers(),
            name="/api/stats/incomplete-students",
        )

    @task(1)
    @tag("teacher", "browse")
    def browse_courses(self):
        """浏览课程列表"""
        if not self.token:
            return
        self.client.get(
            "/api/courses?status=all",
            headers=self._headers(),
            name="/api/courses [教师浏览]",
        )


# ============================================================
# 视频流用户 — 模拟视频并发下载/播放
# ============================================================

class VideoStreamUser(HttpUser):
    """
    视频流播放者 — 模拟多用户并发观看视频

    核心目的：
        测试 Nginx sendfile + mp4 模块的并发视频分发能力。
        这是整个系统最大的瓶颈点（HDD 随机读 + 带宽上限）。

    行为链路：
        1. 先登录获取 Token（部分视频路径可能需要鉴权）
        2. 并发请求视频文件，使用 Range 头模拟真实播放器行为
        3. 每次请求 256KB~2MB 的视频块（模拟流式播放）

    权重：占压测用户总数的 20%（视频流是带宽大户）
    注意：800 并发视频流是极限场景，需确保负载机带宽充足

    性能基线参考：
        - 服务器上行带宽：597 Mbps
        - HDD 随机读上限：~20MB/s（800 并发）
        - 3 个视频文件总计 110MB
    """
    wait_time = between(1, 3)  # 视频流请求间隔短，模拟持续播放
    weight = 20  # 在混合场景中占 20%

    def on_start(self):
        """初始化 — 登录并选择视频"""
        account = pick_student()
        self.token = None
        self.video_file = pick_video()
        self.current_byte = 0  # 当前读取位置（模拟播放进度）

        # 学生登录
        resp = self.client.post(
            "/api/auth/login",
            json={"username": account["username"], "password": account["password"]},
            name="/api/auth/login [视频流用户]",
        )
        try:
            data = resp.json()
            if data.get("code") == 0:
                self.token = data["data"]["token"]
        except Exception:
            pass

    @task(5)
    @tag("video", "stream")
    def stream_video_chunk(self):
        """
        流式请求视频块 — 模拟 HTML5 video 标签的 HTTP Range 请求

        真实浏览器行为：
            1. 首先请求前 0-1 字节获取文件大小
            2. 然后分块请求，每次 256KB~2MB
            3. 收到 206 Partial Content 响应

        压测模拟：
            每次请求一段视频数据（chunk_size 随机），
            模拟播放器持续拉取视频流的行为。
            不实际保存下载内容（stream=True + 不读取 body），
            只验证服务器能否正确响应 Range 请求。
        """
        # 随机选择视频文件
        video = pick_video()

        # 模拟 Range 请求：随机请求视频的某一段
        # 真实播放器通常请求 256KB~2MB 的块
        chunk_size = random.randint(256 * 1024, 2 * 1024 * 1024)
        start_byte = random.randint(0, 100 * 1024 * 1024)  # 随机起始位置（假设视频<100MB）
        end_byte = start_byte + chunk_size - 1

        headers = {"Range": f"bytes={start_byte}-{end_byte}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # 使用 stream=True 避免将整个响应体加载到内存
        # 注意：Locust 默认会等待完整响应，此处仅测试响应速度
        with self.client.get(
            f"/uploads/videos/{video}",
            headers=headers,
            name="/uploads/videos/* [Range流式]",
            stream=True,
            catch_response=True,
        ) as resp:
            # 验证响应状态码
            if resp.status_code in (200, 206):
                resp.success()
            elif resp.status_code == 404:
                # 视频文件不存在（可能文件名不匹配）
                resp.failure(f"视频文件不存在: {video}")
            else:
                resp.failure(f"视频请求异常: HTTP {resp.status_code}")

    @task(2)
    @tag("video", "initial")
    def video_initial_request(self):
        """
        视频初始请求 — 模拟播放器首次加载视频文件

        真实行为：
            HTML5 video 标签首次加载时会请求整个文件，
            服务器返回 200 + Content-Length，或 206 + Content-Range。

        压测中仅验证首个 Range 请求的响应速度。
        """
        video = pick_video()
        headers = {"Range": "bytes=0-1"}  # 最小 Range 请求，获取 Accept-Ranges 和文件大小
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with self.client.get(
            f"/uploads/videos/{video}",
            headers=headers,
            name="/uploads/videos/* [首次加载]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 206):
                resp.success()
            else:
                resp.failure(f"视频首次加载失败: HTTP {resp.status_code}")


# ============================================================
# 事件钩子 — 压测结果统计
# ============================================================

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    压测结束回调 — 输出汇总统计

    在 Web UI 模式下，统计数据可在 UI 中查看；
    在无头模式下，此回调提供命令行汇总输出。
    CSV 报告会由 --csv 参数自动生成。
    """
    if isinstance(environment.runner, MasterRunner):
        # Master 模式下不输出（Worker 汇报给 Master）
        return

    stats = environment.stats
    print("\n" + "=" * 60)
    print("  压测结果汇总")
    print("=" * 60)
    print(f"  总请求数:     {stats.total.num_requests}")
    print(f"  失败请求数:   {stats.total.num_failures}")
    print(f"  平均响应时间: {stats.total.avg_response_time:.1f} ms")
    print(f"  中位数响应:   {stats.total.median_response_time:.1f} ms")
    print(f"  95% 响应时间: {stats.total.get_response_time_percentile(0.95):.1f} ms")
    print(f"  99% 响应时间: {stats.total.get_response_time_percentile(0.99):.1f} ms")
    print(f"  总 RPS:       {stats.total.total_rps:.1f}")
    print("=" * 60)

    # 输出各 API 端点的统计
    print("\n  各端点统计:")
    print("-" * 60)
    for name, entry in sorted(stats.entries.items()):
        if entry.num_requests > 0:
            print(f"  {name}")
            print(f"    请求数={entry.num_requests}  失败={entry.num_failures}  "
                  f"平均={entry.avg_response_time:.0f}ms  "
                  f"P95={entry.get_response_time_percentile(0.95):.0f}ms")
    print("-" * 60)
