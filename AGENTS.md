# AGENTS.md

## Project

暑期在线学习平台 — DingTalk H5 micro-app for tracking student study progress with anti-cheat mechanisms.

## Commands

### Local development
```bash
# Backend (requires MySQL + Redis running locally)
cd backend
pip install -r requirements.txt
cp .env.example .env   # edit .env with real credentials
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev            # Vite dev server on :3000, proxies /api → localhost:8000
```

### Docker deployment
```bash
cp backend/.env.example .env   # fill in DingTalk keys, DB passwords, JWT_SECRET
bash scripts/deploy.sh         # build + up + health check
```

### Remote update (on server)
```bash
bash scripts/remote-update.sh  # git pull → rebuild → restart → health check
```

## Architecture

- **Backend entry**: `backend/app/main.py` — FastAPI app with lifespan (init_db → start_scheduler → yield → stop_scheduler → close_redis)
- **7 routers**: auth, heartbeat, course, stats, notify, admin, homework — all mounted at `/api/*`
- **Core logic**: `services/study_engine.py` — anti-cheat effective-study-time engine (heartbeat validation, pause tolerance, page visibility, multi-tab prevention)
- **Scheduled jobs**: `services/scheduler.py` — APScheduler: cleans `heartbeat_logs` older than 30 days daily at 03:00; checks for assignments past deadline every minute and triggers auto-grading
- **Auto-grading pipeline**: `services/agent_caller.py` (stub — logs intent but doesn't call any API yet) + `services/image_stitcher.py` (Pillow-based vertical stitching of homework images to 800px width)
- **Models**: single file `backend/app/models/models.py` — User, Course, StudySession, HeartbeatLog, Assignment, Submission, GradingReport
- **Frontend entry**: `frontend/src/main.js` — Vue3 SPA with hash-mode router (`createWebHashHistory`, not history mode — required for DingTalk H5)
- **Key composables**: `useStudyTracker.js` (heartbeat sender), `useDingTalk.js` (DingTalk JSAPI wrapper)
- **Video serving**: Nginx serves videos directly from `/uploads/videos/` (not FastAPI) for performance — mounted read-only into frontend container

## Homework Management

- **Feature**: Teachers publish assignments, students submit homework images, AI agents grade and generate reports
- **Relationship**: One course = one assignment (1:1, enforced by `Assignment.course_id` unique constraint)
- **Models**: `Assignment` (作业), `Submission` (提交), `GradingReport` (批改报告)
- **Router**: `backend/app/routers/homework.py`
- **Key APIs**:
  - `GET/POST/PUT /api/homework/assignments/{course_id}` — CRUD for course assignment
  - `POST /api/homework/upload` — upload homework images
  - `POST /api/homework/submissions` — student submit homework
  - `POST /api/homework/grading-callback` — AI agent callback (requires `X-API-Key` header)
  - `GET /api/homework/reports/{submission_id}` — view grading report
- **Frontend pages**: `HomeworkManage.vue` (teacher), `StudentHomework.vue` (student)
- **AI agent integration**: Agent calls `/api/homework/grading-callback` with `X-API-Key` header; `agent_caller.py` is currently a stub (GRADING_AGENT_URL env var is empty by default)

## Important conventions & gotchas

- **No Alembic**: DB tables auto-created via `init_db()` → `Base.metadata.create_all()`. Schema changes require manual SQL or dropping/recreating. Do NOT rely on migrations.
- **No tests**: No test framework or test files exist. No linter/formatter config either.
- **requirements.txt line 1**: Previously had invisible Unicode characters before `fastapi`. If pip install fails with encoding error, check for hidden chars.
- **Two .env locations**: `.env.example` is in `backend/`; `deploy.sh` copies it to repo root as `.env` for `docker-compose.yml`. For local dev, `backend/.env` is used by `pydantic-settings`.
- **Docker port mapping**: backend=127.0.0.1:8001→8000, frontend=127.0.0.1:8080→80, host Nginx on :1001→8080. Do NOT expose backend/frontend ports publicly.
- **Hash router**: Frontend uses `createWebHashHistory()` (URLs contain `#`). Changing to history mode breaks DingTalk in-app navigation.
- **Anti-cheat constants** (in `StudyEngine`): HEARTBEAT_INTERVAL=30s, HEARTBEAT_TIMEOUT=90s, PAUSE_TOLERANCE=300s
- **heartbeat_logs growth**: ~12k rows/hour for 100 concurrent students. Scheduler auto-cleans >30 day records daily at 03:00. Without scheduler (local dev), table grows unbounded.
- **JWT_SECRET consistency**: Must stay the same across server migrations, otherwise all existing tokens invalidate.
- **Uploads not persisted in Docker**: `docker-compose.yml` does NOT mount `backend/uploads/` to a named volume. Uploaded videos/homework images are lost on container rebuild. Production must add a volume mount.
- **DingTalk dependency**: Auth (免登) requires DingTalk AppKey/AppSecret/CorpId. Without these, login falls back to username/password (v2.0.0+).
- **Login field**: API uses `username` in request body, which maps to `User.name` field in database (not a separate username column).
- **Password hashing**: PBKDF2-SHA256 with 100k iterations, format `salt:hash`. See `backend/app/routers/auth.py` `hash_password()`.
- **Frontend dev server port**: Vite runs on port 3000 (not default 5173), configured in `vite.config.js`.
- **MySQL version**: Docker uses MySQL 8.0, but winget may install MySQL 8.4. Both work, but 8.4 removed `default-authentication-plugin` option (use `mysql_native_password=ON` in my.ini instead).
- **CDN_DOMAIN**: Optional env var. Empty = no CDN (videos served directly from Nginx). Set to `https://cdn.example.com` to enable Tianyi Cloud CDN.
- **GRADING_AGENT_URL**: Optional env var. Empty = auto-grading stub just logs (no real API call). Set to the agent's endpoint to enable actual grading.
