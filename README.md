---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'a2292b48-fab4-48b7-8abe-df51802763d3'
  PropagateID: 'a2292b48-fab4-48b7-8abe-df51802763d3'
  ReservedCode1: '223ceb36-a089-4306-ad6a-ebca791ebee9'
  ReservedCode2: '223ceb36-a089-4306-ad6a-ebca791ebee9'
---

# 22中暑假网课学习进度监督系统

基于钉钉 H5 微应用的学生学习进度监督系统，支持有效学习时长精确采集、统计与提醒。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python FastAPI + MySQL 8.0 + Redis 7 |
| 前端 | Vue3 + Vite + ECharts + 钉钉 JSAPI |
| 部署 | Docker Compose + Nginx |

## 快速启动

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 .env 填入钉钉 AppKey/AppSecret 等

# 2. 一键启动
docker-compose up -d

# 3. 访问
# 学生端：https://your-domain.com/
# 老师端：https://your-domain.com/teacher
# API文档：https://your-domain.com/api/docs
```

## 项目结构

```
study-monitor/
├── backend/           # FastAPI 后端服务
│   ├── app/
│   │   ├── models/    # 数据模型
│   │   ├── routers/   # API 路由
│   │   ├── services/  # 业务逻辑
│   │   └── utils/     # 工具函数
│   └── requirements.txt
├── frontend/          # Vue3 前端
│   └── src/
│       ├── views/     # 页面组件
│       ├── composables/ # 组合式函数
│       └── utils/     # 工具
├── nginx/             # Nginx 配置
└── docker-compose.yml
```

## 版本记录

- v0.1.0 - 项目脚手架
- v0.2.0 - 后端核心（认证+心跳+时长引擎）
- v0.3.0 - 后端补全（课程+统计+通知）
- v0.4.0 - 前端核心（学生学习页+追踪器）
- v0.5.0 - 前端补全（老师看板+导出）
- v0.6.0 - 部署配置（Docker+Nginx）
- v1.0.0 - 正式发布