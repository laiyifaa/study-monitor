---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '4609e59a-5285-42c9-9c8f-8969ca27c3b2'
  PropagateID: '4609e59a-5285-42c9-9c8f-8969ca27c3b2'
  ReservedCode1: '2dc678a2-cfab-4cb5-b6b4-c1cef173220a'
  ReservedCode2: '2dc678a2-cfab-4cb5-b6b4-c1cef173220a'
---

# AGENTS.md

暑期钉钉 H5 微应用，用于追踪学生学习进度并带有反作弊机制。

## Commands

```bash
# Local dev (requires MySQL + Redis running)
cd backend && pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev   # Vite on :3000, proxies /api -> :8000

# Windows: double-click start.bat (launches both in separate cmd windows)

# Docker deploy
cp backend/.env.example .env; bash scripts/deploy.sh

# Server update
bash scripts/remote-update.sh
```

## Architecture

- **Backend**: FastAPI, 12 routers at `/api/*`: auth, heartbeat, course, section, stats, notify, admin, homework, ops, announcement, feedback, agent
- **Entry**: `backend/app/main.py` lifespan: `init_db()` -> `start_scheduler()` -> yield -> `stop_scheduler()` -> `close_redis()`
- **Anti-cheat**: `services/study_engine.py` validates heartbeats (30s interval, 90s timeout, 300s pause tolerance) and prevents multi-tab study
- **Scheduler**: `services/scheduler.py` cleans `heartbeat_logs` older than 30d daily at 03:00 and auto-grades expired assignments every minute
- **Auto-grading**: `services/agent_caller.py` is real TeleAI integration (download image -> upload to agent -> SSE chat), not a stub; `services/image_stitcher.py` stitches homework images
- **Models**: `backend/app/models/models.py` has 12 models, including `AnnouncementRead` for announcement read-tracking
- **Frontend**: Vue3 SPA, `createWebHashHistory()` is required for DingTalk H5; Vite dev server is fixed to port 3000
- **Video**: Nginx serves `/uploads/videos/` directly with sendfile/mp4 support; do not route video streaming through FastAPI
- **Load testing**: `load-test/` contains Locust scripts for API/video load tests

## Conventions & Gotchas

- **No Alembic**: `init_db()` calls `Base.metadata.create_all()`. Schema changes require manual SQL or recreating tables.
- **No automated tests, CI, linter, or formatter config** exists in this repo.
- **Two `.env` locations**: `backend/.env` for local backend dev; root `.env` for `docker-compose.yml` and deploy scripts.
- **Docker ports**: backend `127.0.0.1:8001->8000`, frontend `127.0.0.1:8080->80`, host Nginx commonly maps `:1001->8080`.
- **JWT_SECRET** must stay stable across migrations or all existing tokens become invalid.
- **Uploads are not persisted in Docker**: `docker-compose.yml` does not mount `backend/uploads/` to a named volume, so uploaded videos/homework images can be lost on rebuild.
- **Login request field** `username` maps to `User.name`; there is no separate username column.
- **CORS is wide open** in `backend/app/main.py` with `allow_origins=["*"]`.
- **Auto-grading agent** requires both `GRADING_AGENT_URL` and `GRADING_AGENT_API_KEY`; calls are skipped if either is empty.
- **heartbeat_logs growth** is high under concurrency; cleanup only runs when the backend scheduler is running.
- **requirements.txt line 1** previously had invisible Unicode before `fastapi`; check hidden bytes if `pip install -r requirements.txt` fails unexpectedly.
