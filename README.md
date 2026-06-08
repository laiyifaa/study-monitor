

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

| 层级 | 技术                                 |
| ---- | ------------------------------------ |
| 后端 | Python FastAPI + MySQL 8.0 + Redis 7 |
| 前端 | Vue3 + Vite + ECharts + 钉钉 JSAPI   |
| 部署 | Docker Compose + Nginx               |

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

| 方法 | 路径                           | 说明         | 权限 |
| ---- | ------------------------------ | ------------ | ---- |
| POST | /api/auth/dingtalk             | 钉钉免登     | 公开 |
| GET  | /api/auth/me                   | 当前用户     | 登录 |
| GET  | /api/courses                   | 课程列表     | 登录 |
| POST | /api/courses                   | 创建课程     | 老师 |
| POST | /api/heartbeat/start           | 开始学习     | 学生 |
| POST | /api/heartbeat/beat            | 心跳上报     | 学生 |
| POST | /api/heartbeat/end             | 结束学习     | 学生 |
| GET  | /api/stats/class-overview      | 班级概览     | 老师 |
| GET  | /api/stats/my-progress         | 我的进度     | 学生 |
| GET  | /api/stats/daily-summary       | 每日统计     | 老师 |
| GET  | /api/stats/incomplete-students | 未完成学生   | 老师 |
| POST | /api/notify/study-reminder     | 发送学习提醒 | 老师 |
| POST | /api/notify/daily-report       | 发送每日报告 | 老师 |
| GET  | /api/notify/export             | 导出 Excel   | 老师 |

## 有效学习时长判定规则

| 场景                    | 计时            | 技术实现                               |
| ----------------------- | --------------- | -------------------------------------- |
| 视频播放中 + 页面在前台 | 正常计时        | is_playing=true & is_page_visible=true |
| 视频暂停 <= 5分钟       | 正常计时        | 暂停时间 < PAUSE_TOLERANCE             |
| 视频暂停 > 5分钟        | 暂停计时        | 暂停时间 >= PAUSE_TOLERANCE            |
| 页面切到后台            | 立即暂停        | document.hidden=true                   |
| 心跳超时（>90秒）       | 暂停计时        | gap > HEARTBEAT_TIMEOUT                |
| 5分钟无交互             | 暂停 + 弹窗验证 | idle > IDLE_THRESHOLD                  |
| 随机验证弹窗未通过      | 暂停计时        | showVerify=true                        |

## 钉钉应用配置

1. 登录 [钉钉开发者后台](https://open.dingtalk.com)
2. 创建企业内部应用，添加「网页应用」能力
3. 配置应用首页地址（HTTPS URL）
4. 将后端域名加入安全域名列表
5. 获取 AppKey、AppSecret、CorpId 填入 `.env`
6. 设置可见范围（全校师生部门）
7. 添加接口权限（通讯录只读、消息通知等）

## 数据存储与迁移

### 全部运行时产物

| 序号 | 产物类型        | 本地开发路径                        | Docker 部署路径                             | 是否持久化               | 清理机制                     |
| ---- | --------------- | ----------------------------------- | ------------------------------------------- | ------------------------ | ---------------------------- |
| 1    | 上传视频        | `backend/uploads/videos/`         | `/app/uploads/videos/`                    | **否（未挂载卷）** | 删课程时同步删；重上传时删旧 |
| 2    | MySQL 数据      | 本地 MySQL `study_monitor` 库     | 命名卷 `mysql_data` → `/var/lib/mysql` | 是                       | **无自动清理**         |
| 3    | Redis 缓存      | 本地 Redis 6379                     | 命名卷 `redis_data` → `/data`          | 是                       | Key 自动过期（TTL）          |
| 4    | .env 配置       | `backend/.env`、`frontend/.env` | 环境变量注入容器                            | 宿主机文件               | 手动管理                     |
| 5    | Excel 导出      | 不落盘（内存流直返）                | 同左                                        | -                        | 不产生残留                   |
| 6    | Nginx 日志      | 本地不用 Nginx                      | `/var/log/nginx/`                         | **否（未挂载）**   | 容器重启丢失                 |
| 7    | Docker 容器日志 | Docker 内部                         | Docker 内部                                 | 是                       | **无大小限制**         |

### MySQL 核心表说明

| 表名               | 内容                                                | 增长速度                        | 清理建议                             |
| ------------------ | --------------------------------------------------- | ------------------------------- | ------------------------------------ |
| `users`          | 教师学生账号、角色、密码哈希、钉钉ID、API Key、班级 | 极慢（按用户数）                | 无需清理                             |
| `courses`        | 课程标题、视频地址、要求学习时长、截止日期          | 极慢（按课程数）                | 无需清理                             |
| `study_sessions` | 每次学习的起止时间、有效秒数、播放进度              | 中等（每人每天1-5条）           | 可清理1年前记录                      |
| `heartbeat_logs` | 每30秒一次的心跳快照（防刷课依据）                  | **快（每学生每30秒1条）** | **必须定期清理，建议保留30天** |

> **heartbeat_logs 增长估算**：100人同时学1小时 = 12,000条；1天8小时 = 约96,000条。长期运行必须加定时清理。

### 备份清单（换服务器前必须备份的文件）

| 优先级         | 备份项           | 路径                     | 命令                                             |
| -------------- | ---------------- | ------------------------ | ------------------------------------------------ |
| **必须** | MySQL 全量数据   | 数据库 `study_monitor` | `mysqldump -u root study_monitor > backup.sql` |
| **必须** | 上传的视频文件   | `backend/uploads/`     | `tar czf uploads.tar.gz backend/uploads/`      |
| **必须** | 后端 .env 配置   | `backend/.env`         | `cp backend/.env env_backup.txt`               |
| **必须** | 前端 .env 配置   | `frontend/.env`        | `cp frontend/.env frontend_env_backup.txt`     |
| 可选           | Redis 持久化文件 | Redis RDB/AOF            | Docker 卷 `redis_data` 自动持久化              |

### 服务器迁移步骤

换服务器部署时，**仅部署代码会创建空数据库，所有旧数据丢失**。需按以下步骤迁移：

```bash
# ====== 旧服务器操作 ======

# 1. 导出 MySQL 全量数据
mysqldump -u root study_monitor > study_monitor_backup.sql

# 2. 打包上传的视频文件
tar czf uploads_backup.tar.gz backend/uploads/

# 3. 备份 .env 配置（含钉钉密钥、JWT密钥等，丢失无法恢复）
cp backend/.env backend_env_backup.txt
cp frontend/.env frontend_env_backup.txt


# ====== 新服务器操作 ======

# 4. 克隆项目代码
git clone https://github.com/Sumutan/study-monitor.git && cd study-monitor

# 5. 还原 .env 配置（必须在启动前还原，否则 JWT_SECRET 不一致导致旧 Token 失效）
cp backend_env_backup.txt backend/.env
cp frontend_env_backup.txt frontend/.env

# 6. 启动服务（Docker 会自动创建空数据库）
docker-compose up -d

# 7. 导入 MySQL 数据（覆盖空表）
#    Docker 部署时 MySQL 映射在 3306 端口，密码见 backend/.env
mysql -h 127.0.0.1 -u root -p<密码> study_monitor < study_monitor_backup.sql

# 8. 还原视频文件
tar xzf uploads_backup.tar.gz

# 9. 重启服务
docker-compose restart

# 10. 验证迁移结果
#     - 访问教师端统计看板检查数据是否完整
#     - 播放一门本地视频课程确认视频可访问
#     - 用旧 API Key 测试智能体接口是否可用
```

### 迁移注意事项

- **JWT_SECRET 必须保持一致**：新旧服务器的 `JWT_SECRET` 必须相同，否则已登录用户的 Token 全部失效，需要重新登录
- **API Key 保持有效**：API Key 存在 MySQL `users.api_key` 字段中，随数据库一起迁移，迁移后智能体无需重新配置
- **钉钉平台更新首页地址**：如果新服务器的 IP/域名变了，需要到钉钉开放平台更新应用的移动端/PC端首页地址
- **视频文件路径**：课程表中 `video_url` 存的是文件名（如 `1_ea2096d5.mp4`），后端通过 `backend/uploads/videos/` 目录提供文件，确保视频文件放在正确目录即可
- **Redis 无需迁移**：只缓存临时 token 和限流计数器，丢了会自动重建，不影响任何业务数据
- **验证迁移结果**：检查教师端统计看板数据、学生视频播放、API Key 接口调用是否正常

### Docker 部署注意事项

**上传视频持久化**：当前 `docker-compose.yml` 未将 `backend/uploads/` 挂载到宿主机，容器重建后上传的视频会丢失。生产环境必须添加卷挂载：

```yaml
# docker-compose.yml → backend 服务
backend:
  volumes:
    - ./uploads:/app/uploads
```

**容器日志限制**：Docker 默认日志无大小限制，长期运行可能占满磁盘。建议为每个服务添加：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

**心跳日志清理**：`heartbeat_logs` 表是增长最快的表，建议添加定时任务清理30天前的记录：

```sql
-- 手动清理（可加入 crontab 每天执行）
DELETE FROM heartbeat_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

## 天翼云 CDN 部署方案

### 方案概述

| 方案                | 源站                      | CDN                  | 适用场景                     | 月成本                 |
| ------------------- | ------------------------- | -------------------- | ---------------------------- | ---------------------- |
| **A（推荐）** | 本地服务器 115.223.38.172 | 天翼云 CDN（IP源站） | 有物理服务器、短期间歇性使用 | ~750-1000元（5TB流量） |
| **B**         | 天翼云主机（4C8G）        | 天翼云 CDN（IP源站） | 无物理服务器、需要稳定运行   | CDN + 云主机           |

### CDN 工作原理

```
学生浏览器 → CDN 边缘节点（就近加速） → 回源到源站 Nginx → 视频文件
                  ↑                              ↑
              缓存命中直接返回              首次请求/缓存过期时回源
```

### 启用 CDN 的步骤

1. **天翼云控制台创建 CDN 加速域名**：

   - 业务类型：网页/小文件
   - 源站类型：IP 源站
   - 源站地址：`115.223.38.172`（方案A）或云主机公网IP（方案B）
   - 回源端口：80（HTTP回源）或 443（HTTPS回源）
   - 加速区域：国内
2. **配置域名 CNAME**：在域名 DNS 解析中，将加速域名 CNAME 到天翼云分配的 CNAME 地址
3. **后端配置 CDN 域名**：在 `backend/.env` 或 `docker-compose.yml` 的 environment 中添加：

   ```
   CDN_DOMAIN=https://cdn.your-domain.com
   ```
4. **（可选）配置 HTTPS**：

   - CDN 控制台上传证书或申请免费证书
   - 如需 HTTPS 回源，参考 `nginx/https.conf` 配置源站 HTTPS
5. **重启服务**：

   ```bash
   docker compose restart backend
   ```

### CDN 关键配置项

| 配置项       | 推荐值 | 说明                           |
| ------------ | ------ | ------------------------------ |
| 缓存过期时间 | 7天    | 视频文件不变，可长缓存         |
| 回源协议     | HTTP   | 降低源站 SSL 开销              |
| Range 回源   | 开启   | 支持视频拖动进度条             |
| 过滤参数     | 不忽略 | 视频伪流式需要保留 ?start 参数 |
| 防盗链       | 按需   | 可设 Referer 白名单防外部盗用  |

### 无 CDN 降级

CDN_DOMAIN 为空时，系统自动降级到 Nginx 直连模式（视频请求直接到源站），无需任何代码修改。

## 远程更新部署

服务器上一键拉取最新代码并重启：

```bash
# SSH 登录服务器后
cd /data/study-monitor
bash scripts/remote-update.sh
```

或从开发机远程触发：

```bash
ssh root@115.223.38.172 -p 1000 "cd /data/study-monitor && bash scripts/remote-update.sh"
```

脚本会自动：检测代码变更 → 构建镜像 → 重启容器 → 健康检查

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
- v2.2.1 - 钉盘集成开发后回退（权限模型不可行）
- v2.2.2 - 天翼云CDN资源需求估算文档
- v2.3.0 - CDN集成代码预备：CDN_DOMAIN配置、Nginx CORS头、HTTPS模板、远程更新脚本
