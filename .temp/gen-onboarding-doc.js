const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak, TableOfContents
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };
const headerShading = { fill: "1F4E79", type: ShadingType.CLEAR };
const altShading = { fill: "F2F7FB", type: ShadingType.CLEAR };

function hCell(text, width) {
  return new TableCell({
    borders: cellBorders, width: { size: width, type: WidthType.DXA },
    shading: headerShading, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 40 },
      children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 20, font: "Microsoft YaHei" })] })]
  });
}

function dCell(text, width, shading) {
  return new TableCell({
    borders: cellBorders, width: { size: width, type: WidthType.DXA },
    shading: shading || undefined, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { before: 30, after: 30 },
      children: [new TextRun({ text, size: 20, font: "Microsoft YaHei" })] })]
  });
}

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200 },
    children: [new TextRun({ text })] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 160 },
    children: [new TextRun({ text })] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 120 },
    children: [new TextRun({ text })] });
}
function p(text, opts = {}) {
  return new Paragraph({ spacing: { before: 60, after: 60, line: 360 }, ...opts,
    children: [new TextRun({ text, size: 22, font: "Microsoft YaHei", ...opts.run })] });
}
function pBold(label, text) {
  return new Paragraph({ spacing: { before: 60, after: 60, line: 360 },
    children: [
      new TextRun({ text: label, size: 22, font: "Microsoft YaHei", bold: true }),
      new TextRun({ text, size: 22, font: "Microsoft YaHei" })
    ] });
}
function bullet(text) {
  return new Paragraph({ numbering: { reference: "bl", level: 0 }, spacing: { before: 40, after: 40, line: 340 },
    children: [new TextRun({ text, size: 22, font: "Microsoft YaHei" })] });
}
function bulletBold(label, text) {
  return new Paragraph({ numbering: { reference: "bl", level: 0 }, spacing: { before: 40, after: 40, line: 340 },
    children: [
      new TextRun({ text: label, size: 22, font: "Microsoft YaHei", bold: true }),
      new TextRun({ text, size: 22, font: "Microsoft YaHei" })
    ] });
}

function makeTable(headers, rows, colWidths) {
  return new Table({
    columnWidths: colWidths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => hCell(h, colWidths[i])) }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map((c, i) => dCell(c, colWidths[i], ri % 2 === 1 ? altShading : undefined))
      }))
    ]
  });
}

const children = [];

// Title page
children.push(new Paragraph({ spacing: { before: 2400 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Study-Monitor", size: 72, bold: true, color: "1F4E79", font: "Microsoft YaHei" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 100 },
  children: [new TextRun({ text: "\u5728\u7EBF\u5B66\u4E60\u8FDB\u5EA6\u76D1\u7763\u7CFB\u7EDF", size: 40, color: "2E75B6", font: "Microsoft YaHei" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600 },
  children: [new TextRun({ text: "\u65B0\u540C\u4E8B\u9879\u76EE\u4E0A\u624B\u6307\u5357", size: 32, bold: true, font: "Microsoft YaHei" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400 },
  children: [new TextRun({ text: "\u7248\u672C v4.0  |  2026 \u5E74 7 \u6708", size: 22, color: "808080", font: "Microsoft YaHei" })] }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// TOC
children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("\u76EE\u5F55")] }));
children.push(new TableOfContents("\u76EE\u5F55", { hyperlink: true, headingStyleRange: "1-3" }));
children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(h1("一、项目概述"));
children.push(p("Study-Monitor（暑期在线学习平台）是一套面向中学暑假网课场景的学习进度监督系统。系统以钉钉 H5 微应用为载体，围绕\u201C有效学习时长\u201D这一核心指标，实现了从视频播放、进度追踪、防作弊、统计汇总到提醒推送的全链路闭环。"));
children.push(p("一句话概括：打开页面不算学习，视频在播 + 页面在前台 + 心跳在跳才计入有效时长。"));

children.push(h2("1.1 核心能力"));
children.push(bulletBold("有效学习时长采集：", "30 秒心跳 + 页面可见性检测 + 视频播放状态三位一体"));
children.push(bulletBold("防作弊体系：", "5 分钟无交互暂停、随机弹窗验证、防多开、视频进度去重"));
children.push(bulletBold("视频时间模式：", "时长按视频内容时间计算（非墙钟时间），天然支持 2 倍速，封顶 65 秒/心跳"));
children.push(bulletBold("钉钉免登：", "学生/教师打开钉钉即自动登录，无需手动输入账号"));
children.push(bulletBold("教师统计看板：", "ECharts 图表 + 班级概览 + 学生详情 + 数据导出"));
children.push(bulletBold("作业与批改：", "多文件上传 + 迟交标记 + 智能体批改（预留接口）"));
children.push(bulletBold("消息推送：", "钉钉机器人发送学习提醒和每日报告"));
children.push(bulletBold("运维面板：", "服务器资源、容器状态、业务数据一站式监控"));

children.push(h1("二、技术架构"));
children.push(h2("2.1 整体架构图"));
children.push(p("系统采用前后端分离 + Docker 容器化部署，整体数据流如下："));
children.push(p("钉钉客户端 / 浏览器 → 宿主机 Nginx (:1001) → 前端容器 (Nginx 托管 Vue SPA) → 后端容器 (FastAPI :8000) → MySQL + Redis", { run: { color: "2E75B6" } }));

children.push(h2("2.2 Docker 容器编排"));
children.push(makeTable(
  ["服务", "基础镜像", "容器端口", "宿主机映射", "说明"],
  [
    ["frontend", "node:20-alpine → nginx", "80", "127.0.0.1:8080", "Vue3 构建后由 Nginx 托管"],
    ["backend", "python:3.11-slim", "8000", "127.0.0.1:8001", "FastAPI 应用"],
    ["mysql", "mysql:8.0", "3306", "未映射", "仅 Docker 内部访问"],
    ["redis", "redis:7-alpine", "6379", "未映射", "限流 + 缓存"]
  ],
  [1400, 2200, 1200, 1800, 2760]
));

children.push(h2("2.3 技术栈明细"));
children.push(makeTable(
  ["层级", "技术", "版本", "用途"],
  [
    ["后端框架", "FastAPI", "0.110.0", "异步 REST API"],
    ["ORM", "SQLAlchemy", "2.0", "异步模式，无 Alembic 迁移"],
    ["数据库", "MySQL", "8.0", "aiomysql 异步驱动"],
    ["缓存", "Redis", "7", "钉钉 access_token 缓存 + 限流"],
    ["认证", "python-jose (JWT)", "", "HS256，72 小时过期"],
    ["定时任务", "APScheduler", "3.10", "心跳清理 + 自动批改"],
    ["前端框架", "Vue 3", "3.4.21", "组合式 API"],
    ["路由", "vue-router", "4", "Hash 模式（钉钉 H5 必需）"],
    ["HTTP 客户端", "Axios", "1.6", "请求/响应拦截器"],
    ["钉钉集成", "dingtalk-jsapi", "2.15", "免登 + 导航 + 文件预览"],
    ["图表", "ECharts", "5.5", "教师看板、签到日历"],
    ["构建工具", "Vite", "5.2", "开发端口 3000"],
    ["Web 服务器", "Nginx", "", "容器反代 + 宿主机 :1001"],
    ["部署", "Docker Compose", "", "一键构建 + 启动"]
  ],
  [1600, 2000, 1200, 4560]
));

children.push(h1("三、开发环境搭建"));
children.push(h2("3.1 前置条件"));
children.push(bullet("Git、Node.js 20+、Python 3.11+"));
children.push(bullet("Docker Desktop（全栈部署时需要）"));
children.push(bullet("VPN 代理端口 7890（访问 GitHub 等外网资源时需要）"));

children.push(h2("3.2 后端本地开发"));
children.push(p("1. 克隆仓库后进入 backend 目录"));
children.push(p("2. 复制 .env.example 为 .env，填入数据库和钉钉凭据"));
children.push(p("3. 安装依赖：pip install -r requirements.txt"));
children.push(p("4. 启动服务：uvicorn app.main:app --reload --port 8000"));
children.push(p("5. 访问 http://localhost:8000/api/docs 查看 Swagger API 文档", { run: { color: "2E75B6" } }));

children.push(h2("3.3 前端本地开发"));
children.push(p("1. 进入 frontend 目录"));
children.push(p("2. 安装依赖：npm install"));
children.push(p("3. 启动开发服务器：npm run dev（默认端口 3000，Vite 自动代理 /api 到 localhost:8000）"));
children.push(p("4. 访问 http://localhost:3000", { run: { color: "2E75B6" } }));

children.push(h2("3.4 Docker 全栈部署"));
children.push(p("一键启动：bash scripts/deploy.sh"));
children.push(p("远程更新：bash scripts/remote-update.sh（自动 git pull + rebuild + restart）"));

children.push(h2("3.5 关键环境变量"));
children.push(makeTable(
  ["变量名", "用途", "必填"],
  [
    ["DT_APP_KEY / DT_APP_SECRET / DT_CORP_ID", "钉钉开放平台凭据", "是"],
    ["DT_ROBOT_WEBHOOK / DT_ROBOT_SECRET", "钉钉机器人推送", "是"],
    ["MYSQL_PASSWORD", "数据库密码", "是"],
    ["JWT_SECRET", "JWT 签名密钥（跨服务器必须一致）", "是"],
    ["CDN_DOMAIN", "天翼云 CDN 域名（可选）", "否"],
    ["GRADING_AGENT_URL", "智能体批改服务地址（可选，当前为 stub）", "否"]
  ],
  [3200, 4160, 1000]
));
children.push(p("注意：后端 .env 在 backend/.env（pydantic-settings 读取），根目录 .env 给 docker-compose 用，两者是不同的文件！", { run: { bold: true, color: "C00000" } }));

children.push(h1("四、代码结构说明"));
children.push(h2("4.1 后端目录（backend/app/）"));
children.push(makeTable(
  ["文件/目录", "职责"],
  [
    ["main.py", "应用入口，注册 13 个路由模块 + 中间件 + 生命周期事件"],
    ["config.py", "pydantic-settings 配置管理，从 .env 读取所有环境变量"],
    ["database.py", "SQLAlchemy 异步引擎（aiomysql），自动建表 create_all()"],
    ["database_redis.py", "Redis 异步连接"],
    ["models/models.py", "12 个 ORM 模型定义"],
    ["routers/auth.py", "认证：钉钉免登 + 浏览器登录 + API Key"],
    ["routers/heartbeat.py", "心跳：防刷课核心接口"],
    ["routers/course.py", "课程 CRUD"],
    ["routers/section.py", "小节 CRUD + 视频上传"],
    ["routers/stats.py", "统计看板（7 个接口）"],
    ["routers/notify.py", "钉钉消息推送 + Excel 导出"],
    ["routers/admin.py", "管理后台（用户 + 班级管理）"],
    ["routers/homework.py", "作业管理（最大路由文件，1094 行）"],
    ["routers/ops.py", "运维监控面板"],
    ["routers/announcement.py", "公告管理（含未读/已读）"],
    ["routers/feedback.py", "小节评价反馈"],
    ["routers/agent.py", "智能体专用 API（需 API Key 认证）"],
    ["services/study_engine.py", "防刷课核心引擎（最精巧的模块）"],
    ["services/scheduler.py", "APScheduler 定时任务"],
    ["services/agent_caller.py", "智能体批改调用（当前为 stub）"],
    ["services/image_stitcher.py", "作业图片拼接（Pillow）"],
    ["utils/jwt_helper.py", "JWT + API Key 双重认证"]
  ],
  [3200, 6160]
));

children.push(h2("4.2 前端目录（frontend/src/）"));
children.push(makeTable(
  ["文件/目录", "职责"],
  [
    ["main.js", "入口，Hash 路由模式"],
    ["App.vue", "根组件"],
    ["router/index.js", "18 条路由 + 权限守卫"],
    ["views/StudentLearn.vue", "学生学习页（核心交互页）"],
    ["views/TeacherDashboard.vue", "教师统计看板"],
    ["views/HomeworkManage.vue", "作业管理"],
    ["views/AdminPanel.vue", "管理后台"],
    ["views/OpsPanel.vue", "运维监控"],
    ["views/Login.vue", "登录页"],
    ["composables/useStudyTracker.js", "学习心跳追踪器"],
    ["composables/useDingTalk.js", "钉钉 JSAPI 封装"],
    ["utils/api.js", "Axios 封装（401 自动跳登录）"],
    ["utils/auth.js", "认证状态管理"]
  ],
  [3600, 5760]
));

children.push(h1("五、核心业务逻辑"));
children.push(h2("5.1 有效学习时长计算"));
children.push(p("系统的核心设计理念——不是\u201C在线就算学习\u201D，而是同时满足三个条件才计时："));
children.push(bulletBold("视频在播放", "（is_playing = true）"));
children.push(bulletBold("页面在前台", "（is_page_visible = true）"));
children.push(bulletBold("心跳未超时", "（90 秒内收到心跳）"));

children.push(p("这套逻辑封装在 StudyEngine 类（services/study_engine.py）中，是整个系统最精巧的模块。关键常量："));
children.push(makeTable(
  ["常量", "值", "含义"],
  [
    ["HEARTBEAT_INTERVAL", "30 秒", "前端心跳上报间隔"],
    ["HEARTBEAT_TIMEOUT", "90 秒", "3 次未收到心跳则标记会话超时"],
    ["PAUSE_TOLERANCE", "300 秒", "5 分钟无交互自动暂停计时"],
    ["MAX_SECONDS_PER_BEAT", "65 秒", "单次心跳封顶，防止 3 倍速以上刷时长"]
  ],
  [2800, 1200, 5360]
));

children.push(h2("5.2 视频时间模式"));
children.push(p("有效时长按视频内容时间计算（而非墙钟时间）："));
children.push(bullet("1 倍速播放 30 秒 = 30 秒有效时长"));
children.push(bullet("2 倍速播放 30 秒 = 60 秒有效时长（天然支持 2 倍速）"));
children.push(bullet("单次心跳封顶 65 秒，防止 3 倍速以上刷时长"));

children.push(h2("5.3 课程-小节两级结构"));
children.push(p("Course 是宏观概念（如\u201C初高中衔接数学\u201D），Section 是计时最小单元（如\u201C第 1 讲 集合\u201D）。每个 Section 有独立视频和开播时间，学生学习时针对具体 Section 计时。"));

children.push(h2("5.4 防作弊体系"));
children.push(bulletBold("5 分钟无交互暂停：", "鼠标/键盘无操作超过 5 分钟自动暂停"));
children.push(bulletBold("随机弹窗验证：", "学习过程中随机弹出确认弹窗，未响应则暂停"));
children.push(bulletBold("防多开：", "同一用户同一小节只允许一个活跃会话"));
children.push(bulletBold("视频进度去重：", "重复观看同一进度区间不计入时长"));

children.push(h2("5.5 双重认证机制"));
children.push(makeTable(
  ["认证方式", "适用场景", "有效期", "传递方式"],
  [
    ["JWT Token", "浏览器 / 钉钉客户端", "72 小时", "Authorization: Bearer <token>"],
    ["API Key", "智能体 / 外部程序", "长期有效", "X-API-Key: sk_xxx"]
  ],
  [1800, 2600, 1600, 3360]
));
children.push(p("jwt_helper.py 的 get_current_user() 同时支持两种方式，自动识别请求头类型。"));

children.push(h1("六、数据库设计"));
children.push(h2("6.1 表结构总览（12 张表）"));
children.push(makeTable(
  ["表名", "用途", "核心字段", "增长速度"],
  [
    ["users", "用户", "dingtalk_user_id, name, role, class_name, password_hash, api_key", "极慢"],
    ["courses", "课程", "title, teacher_id, require_minutes, start_date, end_date", "极慢"],
    ["sections", "小节", "course_id, title, sort_order, video_url, duration_seconds", "极慢"],
    ["study_sessions", "学习会话", "user_id, section_id, session_id(UUID), effective_seconds", "中等"],
    ["heartbeat_logs", "心跳日志", "session_id, is_playing, is_page_visible, video_current_time", "极快"],
    ["assignments", "作业", "section_id, question_files, grading_prompt, reference_answer", "极慢"],
    ["submissions", "作业提交", "assignment_id, user_id, images(JSON), status, is_late", "中等"],
    ["grading_reports", "批改报告", "submission_id, score, feedback, detail(JSON)", "中等"],
    ["grading_tasks", "批改任务", "submission_id, stitched_image_url, agent_task_id, status", "中等"],
    ["announcements", "公告", "course_id(nullable), title, content, priority", "极慢"],
    ["announcement_reads", "已读记录", "announcement_id, user_id, read_at", "极慢"],
    ["section_feedbacks", "小节评价", "section_id, user_id, rating(1-5), comment", "极慢"]
  ],
  [1800, 1400, 4000, 1000]
));

children.push(h2("6.2 关系图"));
children.push(p("User → 1:N → StudySession → 1:N → HeartbeatLog"));
children.push(p("Course → 1:N → Section → 1:1 → Assignment → 1:N → Submission → 1:1 → GradingReport"));
children.push(p("Submission → 1:N → GradingTask"));
children.push(p("User → 1:N → AnnouncementRead / SectionFeedback"));

children.push(h2("6.3 重要设计决策"));
children.push(bulletBold("无 Alembic 迁移：", "使用 create_all() 自动建表，只建不更新。改表结构需手动 SQL 或重建。"));
children.push(bulletBold("heartbeat_logs 定时清理：", "APScheduler 每日 03:00 自动删除 30 天前数据（100 人/小时 ≈ 12000 行）。"));
children.push(bulletBold("兼容性字段：", "Course 表保留废弃的视频字段，MySQL 在线 DROP COLUMN 不安全。"));

children.push(h1("七、API 路由总览"));
children.push(p("后端共 13 个路由模块，提供约 80+ 个 API 端点。所有接口统一返回格式：{code: 0, data: ...} 或 {code: 1, msg: 错误信息}"));
children.push(p("完整 API 文档可访问 http://服务器地址/api/docs（Swagger UI 自动生成）", { run: { color: "2E75B6" } }));

children.push(makeTable(
  ["路由前缀", "模块", "核心功能", "权限"],
  [
    ["/api/auth", "认证", "钉钉免登 + 浏览器登录 + API Key 管理", "公开/登录"],
    ["/api/heartbeat", "心跳", "开始/上报/结束学习会话", "登录+限流"],
    ["/api/courses", "课程", "课程 CRUD", "teacher/admin 写"],
    ["/api/sections", "小节", "小节 CRUD + 视频上传", "teacher/admin 写"],
    ["/api/stats", "统计", "班级概览/进度/排行榜/签到/报告", "按接口区分"],
    ["/api/notify", "通知", "钉钉推送 + Excel 导出", "teacher/admin"],
    ["/api/admin", "管理", "用户 + 班级管理", "teacher/admin"],
    ["/api/homework", "作业", "作业发布/提交/批改", "按操作区分"],
    ["/api/announcements", "公告", "公告 CRUD + 已读标记", "按操作区分"],
    ["/api/feedback", "评价", "小节评分反馈", "student 提交"],
    ["/api/ops", "运维", "服务器/容器/业务监控", "admin"],
    ["/api/agent", "智能体", "学生/课程/进度查询", "API Key"],
    ["/api/health", "健康检查", "服务可用性探测", "公开"]
  ],
  [1600, 1200, 3400, 2160]
));

children.push(h1("八、钉钉集成"));
children.push(h2("8.1 免登流程"));
children.push(p("学生打开钉钉 → 工作台点击应用 → 前端调用 dd.runtime.permission.requestAuthCode(corpId) → 获取 authCode → POST /api/auth/dingtalk → 后端用 authCode 换取 userid → 查钉钉通讯录获取姓名/手机号 → 本地查找或自动创建用户 → 签发 JWT Token 返回前端 → 前端存 localStorage 后续请求自动携带"));

children.push(h2("8.2 机器人推送"));
children.push(bullet("HMAC-SHA256 加签验证"));
children.push(bullet("两种推送：学习提醒（未完成学生名单）+ 每日报告（今日统计 + 标兵）"));
children.push(bullet("消息格式：Markdown（标题 + 正文 + 名单）"));

children.push(h2("8.3 H5 微应用配置要点"));
children.push(makeTable(
  ["配置项", "值/说明"],
  [
    ["前端路由模式", "Hash 模式（createWebHashHistory），钉钉不支持 History 模式"],
    ["AppID", "193d6a8d-ab56-4021-aa9f-c23e5f50a03d"],
    ["AgentId", "4631331229"],
    ["应用首页地址", "HTTPS URL，需在钉钉开放平台配置"],
    ["安全域名", "后端域名需加入白名单"],
    ["实名同步", "每次免登自动从通讯录 API 同步 real_name 和 phone"]
  ],
  [2400, 6960]
));

children.push(h1("九、部署与运维"));
children.push(h2("9.1 网络与端口"));
children.push(makeTable(
  ["对外端口", "服务", "说明"],
  [
    [":1001", "宿主机 Nginx", "对外唯一入口，反代到 :8080"],
    [":8080", "前端容器", "仅本地访问"],
    [":8001", "后端容器", "仅本地访问"],
    [":1000", "SSH", "远程管理（密码认证）"]
  ],
  [1600, 2000, 5760]
));

children.push(h2("9.2 部署流程"));
children.push(bulletBold("一键部署：", "bash scripts/deploy.sh（构建 + 启动 + 健康检查）"));
children.push(bulletBold("远程更新：", "bash scripts/remote-update.sh（git pull + rebuild + restart）"));
children.push(bulletBold("视频上传：", "通过 API 上传（后端接口）或 SCP 直传服务器 uploads/videos/ 目录"));

children.push(h2("9.3 运维监控"));
children.push(p("访问运维面板：登录管理员账号 → 运维监控页面。可查看："));
children.push(bullet("服务器资源（CPU/内存/磁盘）"));
children.push(bullet("Docker 容器状态"));
children.push(bullet("服务健康检查"));
children.push(bullet("业务数据统计"));
children.push(bullet("存储空间信息"));

children.push(h2("9.4 数据备份"));
children.push(bullet("uploads/ 目录已通过 Docker Volume 持久化"));
children.push(bullet("MySQL 数据需定期 mysqldump 备份"));
children.push(bullet("容器日志已配置 json-file 驱动，单文件 10MB / 最多 3 个"));

children.push(h1("十、常见坑点与注意事项"));
children.push(makeTable(
  ["坑点", "说明", "应对"],
  [
    ["无 Alembic 迁移", "create_all() 只建不更新", "改表需手动写 ALTER SQL"],
    ["前端 Hash 路由", "钉钉 H5 不支持 History 模式", "切勿改成 createWebHistory"],
    ["JWT_SECRET 一致性", "换服务器时必须相同", "否则所有 Token 失效"],
    ["两个 .env 位置", "backend/.env 和根目录 .env 不同", "分别给 pydantic 和 docker-compose 用"],
    ["uploads 持久化", "Docker 重建容器后文件丢失", "已挂载，勿删除 volume 配置"],
    ["requirements.txt BOM", "首行 Unicode BOM 导致 pip 报错", "用 fix_encoding.py 修复"],
    ["Vite 端口", "开发端口 3000 不是默认 5173", "vite.config.js 已配置"],
    ["智能体批改为 stub", "agent_caller.py 只打日志", "需配 GRADING_AGENT_URL"],
    ["CORS 当前 *", "生产环境应收窄", "修改 main.py 的 CORSMiddleware"],
    ["heartbeat_logs 膨胀", "增长最快的表", "APScheduler 自动清理 30 天前数据"]
  ],
  [2200, 3400, 3760]
));

children.push(h1("十一、开发规范"));
children.push(h2("11.1 代码风格"));
children.push(bullet("每个模块顶部有详尽文档字符串（功能说明 + API 列表 + 角色权限矩阵）"));
children.push(bullet("中文注释丰富，\u201C可当文档读\u201D"));
children.push(bullet("防刷课常量大写：HEARTBEAT_INTERVAL、HEARTBEAT_TIMEOUT 等"));
children.push(bullet("统一返回格式：{code: 0, data: ...} / {code: 1, msg: ...}"));

children.push(h2("11.2 Git 协作"));
children.push(bullet("主分支：main"));
children.push(bullet("功能开发：从 main 创建 feature/xxx 分支"));
children.push(bullet("提交前确保后端 uvicorn 和前端 npm run dev 均可正常启动"));
children.push(bullet("API 文档自动生成，新增接口记得写 docstring"));

children.push(h2("11.3 前端路由规范"));
children.push(p("前端 18 条路由，通过 router/index.js 中的权限守卫控制访问："));
children.push(bullet("student 角色只能访问学习、作业、公告等页面"));
children.push(bullet("teacher 角色可访问看板、管理、推送等页面"));
children.push(bullet("admin 角色拥有全部权限包括运维面板"));

children.push(h2("11.4 测试"));
children.push(p("测试清单参见 TEST_CHECKLIST.md，覆盖："));
children.push(bullet("登录/认证流程"));
children.push(bullet("学习心跳与防刷课逻辑"));
children.push(bullet("作业提交与批改"));
children.push(bullet("通知推送"));
children.push(bullet("数据导出"));

children.push(h1("十二、建议上手路径"));
children.push(p("以下按推荐顺序逐步熟悉项目："));
children.push(pBold("第 1 步：", "阅读本文档 + README.md"));
children.push(pBold("第 2 步：", "本地启动后端，访问 /api/docs 浏览全部 API"));
children.push(pBold("第 3 步：", "阅读 services/study_engine.py，理解防刷课核心逻辑"));
children.push(pBold("第 4 步：", "阅读 models/models.py，理解数据模型关系"));
children.push(pBold("第 5 步：", "前端 npm run dev，体验学生端完整学习流程"));
children.push(pBold("第 6 步：", "阅读 routers/auth.py，理解钉钉免登 + JWT 双重认证"));
children.push(pBold("第 7 步：", "Docker 全栈部署一次，熟悉部署流程"));
children.push(pBold("第 8 步：", "选择一个小功能（如公告或评价），从路由 → 服务 → 模型完整走一遍"));

children.push(new Paragraph({ spacing: { before: 400 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "— End of Document —", size: 22, color: "808080", font: "Microsoft YaHei" })] }));


const doc = new Document({
  styles: {
    default: { document: { run: { font: "Microsoft YaHei", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal",
        run: { size: 56, bold: true, color: "1F4E79", font: "Microsoft YaHei" },
        paragraph: { spacing: { before: 240, after: 120 }, alignment: AlignmentType.CENTER } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: "1F4E79", font: "Microsoft YaHei" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: "2E75B6", font: "Microsoft YaHei" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "404040", font: "Microsoft YaHei" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } }
    ]
  },
  numbering: {
    config: [{
      reference: "bl",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
    }]
  },
  sections: [{
    properties: {
      page: {
        margin: { top: 1440, right: 1200, bottom: 1440, left: 1200 },
        size: { width: 11906, height: 16838 }
      }
    },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "Study-Monitor \u65B0\u540C\u4E8B\u4E0A\u624B\u6307\u5357", size: 16, color: "808080", font: "Microsoft YaHei" })] })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "\u7B2C ", size: 16, color: "808080", font: "Microsoft YaHei" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "808080", font: "Microsoft YaHei" }),
          new TextRun({ text: " \u9875", size: 16, color: "808080", font: "Microsoft YaHei" })] })] })
    },
    children
  }]
});

const outPath = "/Users/sh/Desktop/CTWZ/AI \u4E2D\u5FC3\u9879\u76EE/study-monitor/\u65B0\u540C\u4E8B\u9879\u76EE\u4E0A\u624B\u6307\u5357.docx";
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log("OK: " + outPath + " (" + buf.length + " bytes)");
});
