---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '9623b379-583f-4a9b-b707-1877d089d463'
  PropagateID: '9623b379-583f-4a9b-b707-1877d089d463'
  ReservedCode1: 'c007c84c-1bf9-4351-a12c-efdaa8023ffc'
  ReservedCode2: 'c007c84c-1bf9-4351-a12c-efdaa8023ffc'
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

## 版本记录

- v0.1.0 - 项目脚手架
- v0.2.0 - 后端核心（认证+心跳+时长引擎）
- v0.3.0 - 后端补全（课程+统计+通知）
- v0.4.0 - 前端核心（学生学习页+追踪器）
- v0.5.0 - 前端补全（老师看板+导出）
- v0.6.0 - 部署配置（Docker+Nginx）
- v1.0.0 - 正式发布