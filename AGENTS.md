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

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Run

- Local backend: `cd backend; pip install -r requirements.txt; cp .env.example .env; uvicorn app.main:app --reload --port 8000`
- Local frontend: `cd frontend; npm install; npm run dev` on `:3000`; Vite proxies `/api` to `http://localhost:8000` and `allowedHosts=true`.
- Windows helper: `start.bat` launches backend and frontend in separate `cmd` windows.
- Docker deploy uses the root `.env`: `cp backend/.env.example .env && bash scripts/deploy.sh`
- Server update inside a deployed checkout: `bash scripts/remote-update.sh`

## Verify

- There is no automated test suite, CI workflow, linter, formatter, or typecheck config in this repo.
- Practical checks are `cd frontend && npm run build` plus starting backend and frontend locally.
- `load-test/` is a separate Locust project (`pip install -r load-test/requirements.txt`); it creates lots of `study_sessions` and `heartbeat_logs`.

## Architecture

### Backend (FastAPI + MySQL + Redis)

- Entrypoint is `backend/app/main.py`; startup order is `init_db()` -> `start_scheduler()` and shutdown calls `stop_scheduler()` -> `close_redis()`.
- 13 routers mounted under `/api/*`: `auth`, `heartbeat`, `course`, `section`, `stats`, `notify`, `admin`, `homework`, `ops`, `announcement`, `feedback`, `agent`, `login_log`.
- `backend/app/main.py` also serves uploaded files via `GET /api/uploads/{file_path:path}` with path-traversal protection. In Docker, Nginx serves `/uploads/videos/` directly (see `nginx/default.conf`); this endpoint handles homework files and fallback.
- **Config**: `backend/app/config.py` uses `pydantic-settings` with `@lru_cache` singleton. All env vars are read from `.env` or environment.
- **Database**: `backend/app/database.py` uses SQLAlchemy async engine with `aiomysql` driver. `expire_on_commit=False` to avoid implicit sync queries. Pool: `pool_size=20, max_overflow=10`.
- **Auth**: Dual-mode — DingTalk OAuth (免登) + account/password. JWT tokens carry `{sub: user_id, role}` payload. `get_current_user` dependency supports both `Authorization: Bearer <token>` and `X-API-Key` header. `require_role("teacher")` is a factory returning a FastAPI dependency; admin always passes.
- **Scheduler** (`backend/app/services/scheduler.py`): APScheduler `AsyncIOScheduler` with two jobs:
  - `cleanup_heartbeat_logs`: daily at 03:00, batch-deletes logs older than 7 days (10k rows per batch).
  - `trigger_auto_grading`: every minute, finds overdue assignments and processes submissions concurrently.

### Data Model (ORM in `backend/app/models/models.py`)

All models inherit from `Base` (SQLAlchemy `DeclarativeBase`). Key relationships:

```
User (account unique, role: student/teacher/admin)
 ├─ DingTalkBinding (1:N, one student can bind multiple DingTalk accounts)
 ├─ Course (teacher_id FK)
 │   ├─ Section (course_id FK, 1:N, each has independent video)
 │   │   ├─ Assignment (section_id FK unique, 1:1)
 │   │   │   └─ Submission (assignment_id FK, user_id FK)
 │   │   │       └─ GradingReport (submission_id FK unique, 1:1)
 │   │   │       └─ GradingTask (submission_id FK, tracks agent calls)
 │   │   └─ SectionFeedback (section_id FK, user_id FK)
 │   └─ Announcement (course_id FK nullable, null=platform-wide)
 ├─ StudySession (user_id + course_id + section_id, session_id unique UUID)
 │   └─ HeartbeatLog (session_id FK, every 30s snapshot)
 ├─ AnnouncementRead (announcement_id + user_id)
 ├─ ClassDef (class_name unique, v5.0 independent class list)
 └─ LoginLog (user_id nullable, device fingerprint + result)
```

- `Course.video_type/video_url/wukong_url/duration_seconds` still exist in DB for old data but are **deprecated**; new code uses `Section`.
- `StudySession.section_id` is nullable to support v2.x legacy data without section dimension.
- `heartbeat_logs` is the fastest-growing table (~96k rows/day for 100 students × 8h). Scheduler auto-cleans.

### Anti-Cheat Engine (`backend/app/services/study_engine.py`)

Core static methods: `process_heartbeat`, `get_active_session`, `end_active_sessions`.

- 30s heartbeat interval, 90s timeout threshold.
- Effective time uses **video-time mode**: `increment = min(video_delta, HEARTBEAT_INTERVAL*2+5)` — supports 2x speed naturally, caps at 65s per beat.
- Video progress is **monotonic** (only moves forward) — prevents rewind-replay abuse.
- New session auto-closes prior active sessions for same user+course (anti-multi-tab).
- Redis rate-limit: 5 beats per minute per user/course.

### Auto-Grading Pipeline

`backend/app/services/agent_caller.py` + `backend/app/services/image_stitcher.py`:

1. Scheduler finds overdue `Assignment` (deadline passed, `grading_triggered=False`).
2. For each pending `Submission`: stitch uploaded images into a single long image.
3. Upload stitched image to TeleAI `/files/upload` → get `file_id`.
4. POST `/chat-messages` (streaming SSE) with prompt + reference answer → collect full response.
5. Parse JSON result → write `GradingReport` → update `Submission.status` → update `Assignment.grading_status`.
6. Concurrency controlled by `asyncio.Semaphore(GRADING_CONCURRENCY_LIMIT)` (default 10).
7. Retries up to `GRADING_MAX_RETRIES` (default 3) with linear backoff.
8. Calls are **skipped** if `GRADING_AGENT_URL` or `GRADING_AGENT_API_KEY` is empty.

### Frontend (Vue 3 SPA)

- **Hash routing** (`createWebHashHistory()`) — required for DingTalk H5 micro-app; do NOT switch to history mode.
- **Auth store** (`frontend/src/utils/auth.js`): closure-based singleton (no Pinia). Manages `token` + `user` refs synced to `localStorage`. Handles DingTalk auto-login (`dd.ready` → `requestAuthCode` → backend JWT exchange).
- **API layer** (`frontend/src/utils/api.js`): Axios with `baseURL: '/api'`. Request interceptor injects Bearer token. 401 interceptor has **anti-race-condition** logic: only logs out if `_sentToken === currentToken`.
- **Study tracker** (`frontend/src/composables/useStudyTracker.js`): the frontend anti-cheat core. Runs 3 concurrent timers: heartbeat (30s), idle check (60s, triggers verify popup after 5min idle), random anti-AFK popup (8-20min). Uses `fetch({keepalive: true})` for `beforeunload` to guarantee session-end delivery. DingTalk WebView throttles `setInterval`, so `visibilitychange` handler restarts heartbeat on resume.
- **Role-based nav**: `router/index.js` `beforeEach` guard reads `localStorage.user.role`. `admin` passes all; `meta.role='teacher'` blocks students; `meta.role='student'` allows teachers too (preview).
- **No Pinia, no Vuex** — auth uses closure refs, all other state is local to components.

## Env And Data

- Two env files with different roles: `backend/.env` for local backend dev, root `.env` for `docker-compose.yml` and deploy scripts.
- `backend/app/config.py` sets `env_file = ".env"`. When you run `uvicorn` from `backend/`, it reads `backend/.env`; Docker Compose injects variables from the root `.env`.
- **No Alembic**. `init_db()` runs `Base.metadata.create_all()` plus inline `ALTER TABLE` migrations for schema evolution. New columns must be added manually in `database.py:init_db()` with existence checks.
- `JWT_SECRET` must stay stable across deploys or existing tokens become invalid.
- Docker mounts `./uploads` into both backend and frontend containers; uploaded videos and homework files are runtime data.
- Docker ports are loopback-bound: backend `127.0.0.1:8001->8000`, frontend `127.0.0.1:8080->80`.
- `CDN_DOMAIN` env var: when set, video URLs are rewritten to use CDN; when empty, Nginx serves directly (backward-compatible).
- Frontend env: `frontend/.env.production` holds `VITE_DINGTALK_CORP_ID` for DingTalk login.

## Gotchas

- Browser login `username` field maps to `User.account` (not `User.name`). `User.name` is the display name.
- Password hashing uses `PBKDF2-HMAC-SHA256` with random salt, stored as `salt:hash` in `User.password_hash`. Not bcrypt.
- DingTalk binding model: one student can bind **multiple** DingTalk accounts (father + mother), but each DingTalk ID binds to only **one** student.
- `DingTalkBinding` table is separate from `User.dingtalk_user_id` — the User field is legacy; new bindings go to `DingTalkBinding`.
- In Docker, Nginx serves `/uploads/videos/` directly from `nginx/default.conf` with `sendfile`/`mp4`; do not route video streaming through FastAPI.
- Frontend `api.js` 401 handler has race-condition protection via `_sentToken` — do not simplify this to unconditional logout.
- DingTalk WebView suspends `setInterval` when page is backgrounded. `useStudyTracker` compensates by restarting heartbeat on `visibilitychange`.
- `heartbeat_logs` retention is 7 days (not 30 as mentioned in some docs). Controlled by `HEARTBEAT_RETENTION_DAYS` in `scheduler.py`.
