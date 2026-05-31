---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '0be8dbbc-cf45-4425-a121-8418ce427c0f'
  PropagateID: '0be8dbbc-cf45-4425-a121-8418ce427c0f'
  ReservedCode1: 'f3e65f71-c048-43f7-ae7f-bf5cee0c9d3a'
  ReservedCode2: 'f3e65f71-c048-43f7-ae7f-bf5cee0c9d3a'
---

# 22中暑假网课学习进度监督系统

基于钉钉 H5 微应用的学生学习进度监督系统，支持有效学习时长精确采集、统计与提醒。

## 功能特性

- **有效学习时长统计**：30秒心跳 + 页面可见性检测 + 视频播放状态采集
- **防作弊机制**：5分钟无交互暂停、随机8-20分钟弹窗验证、单会话防多开、视频进度去重
- **钉钉免登**：学生/老师自动身份认证，无需手动登录
- **老师端统计看板**：班级概览 + ECharts 图表 + 学生详情列表
- **钉钉群消息推送**：学习提醒 + 每日报告 + 未完成学生名单
- **数据导出**：一键导出 Excel 学习时长报表

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python FastAPI + MySQL 8.0 + Redis 7 |
| 前端 | Vue3 + Vite + ECharts + 钉钉 JSAPI |
| 部署 | Docker Compose + Nginx |

## 快速启动

### 方式一：Docker 一键部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url> study-monitor && cd study-monitor

# 2. 配置环境变量
cp backend/.env.example .env
# 编辑 .env 填入钉钉 AppKey/AppSecret 等

# 3. 一键部署
bash scripts/deploy.sh

# 4. 访问
# 学生端：http://your-server-ip/
# 老师端：http://your-server-ip/teacher
# API文档：http://your-server-ip/api/docs
```

### 方式二：本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env
uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
```

## 项目结构

```
study-monitor/
├── backend/                # FastAPI 后端服务
│   ├── app/
│   │   ├── main.py         # 应用入口
│   │   ├── config.py       # 配置管理
│   │   ├── database.py     # 数据库连接
│   │   ├── models/         # 数据模型（User/Course/StudySession/HeartbeatLog）
│   │   ├── routers/        # API 路由
│   │   │   ├── auth.py     # 钉钉免登认证
│   │   │   ├── heartbeat.py # 心跳接口
│   │   │   ├── course.py   # 课程管理
│   │   │   ├── stats.py    # 统计接口
│   │   │   └── notify.py   # 通知推送 + 导出
│   │   ├── services/       # 业务逻辑
│   │   │   └── study_engine.py  # 有效时长引擎（核心）
│   │   └── utils/          # JWT 工具
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/               # Vue3 前端
│   └── src/
│       ├── views/          # 页面组件
│       │   ├── CourseList.vue       # 课程列表
│       │   ├── StudentLearn.vue     # 学生学习页（核心）
│       │   ├── StudentProgress.vue  # 学生进度页
│       │   └── TeacherDashboard.vue # 老师统计看板
│       ├── composables/    # 组合式函数
│       │   ├── useStudyTracker.js   # 学习追踪器（核心）
│       │   └── useDingTalk.js       # 钉钉 JSAPI 封装
│       ├── utils/          # 工具函数
│       └── router/         # 路由配置
├── nginx/                  # Nginx 反向代理配置
├── scripts/                # 部署脚本
└── docker-compose.yml
```

## API 接口一览

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/auth/dingtalk | 钉钉免登 | 公开 |
| GET | /api/auth/me | 当前用户 | 登录 |
| GET | /api/courses | 课程列表 | 登录 |
| POST | /api/courses | 创建课程 | 老师 |
| POST | /api/heartbeat/start | 开始学习 | 学生 |
| POST | /api/heartbeat/beat | 心跳上报 | 学生 |
| POST | /api/heartbeat/end | 结束学习 | 学生 |
| GET | /api/stats/class-overview | 班级概览 | 老师 |
| GET | /api/stats/my-progress | 我的进度 | 学生 |
| GET | /api/stats/daily-summary | 每日统计 | 老师 |
| GET | /api/stats/incomplete-students | 未完成学生 | 老师 |
| POST | /api/notify/study-reminder | 发送学习提醒 | 老师 |
| POST | /api/notify/daily-report | 发送每日报告 | 老师 |
| GET | /api/notify/export | 导出 Excel | 老师 |

## 有效学习时长判定规则

| 场景 | 计时 | 技术实现 |
|------|------|----------|
| 视频播放中 + 页面在前台 | 正常计时 | is_playing=true & is_page_visible=true |
| 视频暂停 <= 5分钟 | 正常计时 | 暂停时间 < PAUSE_TOLERANCE |
| 视频暂停 > 5分钟 | 暂停计时 | 暂停时间 >= PAUSE_TOLERANCE |
| 页面切到后台 | 立即暂停 | document.hidden=true |
| 心跳超时（>90秒） | 暂停计时 | gap > HEARTBEAT_TIMEOUT |
| 5分钟无交互 | 暂停 + 弹窗验证 | idle > IDLE_THRESHOLD |
| 随机验证弹窗未通过 | 暂停计时 | showVerify=true |

## 钉钉应用配置

1. 登录 [钉钉开发者后台](https://open.dingtalk.com)
2. 创建企业内部应用，添加「网页应用」能力
3. 配置应用首页地址（HTTPS URL）
4. 将后端域名加入安全域名列表
5. 获取 AppKey、AppSecret、CorpId 填入 `.env`
6. 设置可见范围（全校师生部门）
7. 添加接口权限（通讯录只读、消息通知等）

## 数据存储与迁移

### 数据存放位置

项目的数据分布在三个地方：

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 用户账号、课程、学习记录、心跳日志 | **MySQL 数据库** `study_monitor` | 4张表：`users`、`courses`、`study_sessions`、`heartbeat_logs` |
| 上传的视频文件 | **本地磁盘** `backend/uploads/videos/` | 课程中 `video_type=local` 的视频文件 |
| 钉钉 access_token 缓存 | **Redis** | 临时缓存（2小时过期），丢失无影响，会自动重新获取 |

### MySQL 核心表说明

| 表名 | 内容 | 关键字段 |
|------|------|---------|
| `users` | 教师学生账号、角色、密码哈希、钉钉ID、班级 | `dingtalk_user_id`、`role`、`password_hash`、`class_name` |
| `courses` | 课程标题、视频地址、要求学习时长、截止日期 | `video_type`、`video_url`、`require_minutes`、`end_date` |
| `study_sessions` | 每次学习的起止时间、有效秒数、播放进度 | `effective_seconds`、`video_progress`、`is_active` |
| `heartbeat_logs` | 每30秒一次的心跳快照（防刷课依据） | `is_playing`、`is_page_visible`、`action` |

### 服务器迁移步骤

换服务器部署时，**仅部署代码会创建空数据库，所有旧数据丢失**。需按以下步骤迁移：

```bash
# ====== 旧服务器操作 ======

# 1. 导出 MySQL 全量数据
mysqldump -u root study_monitor > study_monitor_backup.sql

# 2. 打包上传的视频文件
tar czf uploads_backup.tar.gz backend/uploads/

# 3. 备份 .env 配置（含钉钉密钥、JWT密钥等）
cp backend/.env env_backup.txt


# ====== 新服务器操作 ======

# 4. 克隆项目代码
git clone https://github.com/Sumutan/study-monitor.git && cd study-monitor

# 5. 先启动一次让 MySQL/Docker 初始化数据库
docker-compose up -d

# 6. 导入 MySQL 数据（覆盖空表）
#    Docker 部署时 MySQL 映射在 3306 端口，密码见 docker-compose.yml
mysql -h 127.0.0.1 -u root -p<密码> study_monitor < study_monitor_backup.sql

# 7. 还原视频文件
tar xzf uploads_backup.tar.gz

# 8. 还原 .env 配置（保持 JWT_SECRET 一致，否则旧 Token 全部失效）
cp env_backup.txt backend/.env

# 9. 重启服务
docker-compose restart
```

### 迁移注意事项

- **JWT_SECRET 必须保持一致**：新旧服务器的 `JWT_SECRET` 必须相同，否则已登录用户的 Token 全部失效，需要重新登录
- **钉钉平台更新首页地址**：如果新服务器的 IP/域名变了，需要到钉钉开放平台更新应用的移动端/PC端首页地址
- **视频文件路径**：课程表中 `video_url` 存的是文件名（如 `1_ea2096d5.mp4`），后端通过 `backend/uploads/videos/` 目录提供文件，确保视频文件放在正确目录即可
- **Redis 无需迁移**：只缓存临时 token，丢了会自动重新获取，不影响任何业务数据
- **验证迁移结果**：启动后检查教师端统计看板数据是否完整、学生视频能否正常播放

## 版本记录

- v0.1.0 - 项目脚手架
- v0.2.0 - 后端核心（认证+心跳+时长引擎）
- v0.3.0 - 后端补全（课程+统计+通知）
- v0.4.0 - 前端核心（学生学习页+追踪器）
- v0.5.0 - 前端补全（老师看板+导出）
- v0.6.0 - 部署配置（Docker+Nginx）
- v1.0.0 - 正式发布
- v2.0.0 - 浏览器登录 + 401跳转登录页
- v2.1.0 - 管理后台 + 自助改密 + 返回导航
- v2.1.1 - Bug修复：保存反馈/文件选择/视频进度显示
- v2.1.2 - Vite allowedHosts 支持 ngrok 穿透