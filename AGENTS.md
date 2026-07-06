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

## Run

- Local backend: `cd backend && pip install -r requirements.txt && cp .env.example .env && uvicorn app.main:app --reload --port 8000`
- Local frontend: `cd frontend && npm install && npm run dev` on `:3000`; Vite proxies `/api` to `http://localhost:8000` and `allowedHosts=true`.
- Windows helper: `start.bat` launches backend and frontend in separate `cmd` windows.
- Docker deploy uses the root `.env`: `cp backend/.env.example .env && bash scripts/deploy.sh`
- Server update inside a deployed checkout: `bash scripts/remote-update.sh`

## Verify

- There is no automated test suite, CI workflow, linter, formatter, or typecheck config in this repo.
- Practical checks are `cd frontend && npm run build` plus starting backend and frontend locally.
- `load-test/` is a separate Locust project (`pip install -r load-test/requirements.txt`); it creates lots of `study_sessions` and `heartbeat_logs`.

## Architecture

- Backend entrypoint is `backend/app/main.py`; startup order is `init_db()` -> `start_scheduler()` and shutdown calls `stop_scheduler()` -> `close_redis()`.
- The FastAPI app mounts 12 business routers under `/api/*`: `auth`, `heartbeat`, `course`, `section`, `stats`, `notify`, `admin`, `homework`, `ops`, `announcement`, `feedback`, `agent`.
- Frontend is a Vue 3 SPA using `createWebHashHistory()` in `frontend/src/router/index.js`; keep hash routing for DingTalk H5.
- Course data is `Course -> Section`; `Course.video_type`, `video_url`, `wukong_url`, and `duration_seconds` still exist in the model for old DBs but new code uses `Section`.

## Env And Data

- `backend/app/config.py` sets `env_file = ".env"`. When you run `uvicorn` from `backend/`, it reads `backend/.env`; Docker Compose injects variables from the root `.env`.
- There are two env files with different roles: `backend/.env` for local backend dev, root `.env` for `docker-compose.yml` and deploy scripts.
- There is no Alembic. `init_db()` only runs `Base.metadata.create_all()`, so schema changes need manual SQL or table recreation.
- `JWT_SECRET` must stay stable across deploys or existing tokens become invalid.
- Docker mounts `./uploads` into both backend and frontend containers; uploaded videos and homework files are runtime data.

## Gotchas

- Browser login `username` maps to `User.name`; there is no separate username column.
- Anti-cheat logic is in `backend/app/services/study_engine.py`: 30s heartbeat interval, 90s timeout, Redis limit of 5 beats per minute per user/course, new sessions close prior active sessions for the same user/course, and video progress only moves forward.
- Scheduler behavior is in `backend/app/services/scheduler.py`: it batch-deletes `heartbeat_logs` older than 30 days at 03:00 and checks every minute for overdue auto-grading. If the backend scheduler is not running, `heartbeat_logs` will keep growing.
- Auto-grading in `backend/app/services/agent_caller.py` is a real TeleAI flow: download stitched image -> upload to `/files/upload` -> consume streaming `/chat-messages`. Calls are skipped if `GRADING_AGENT_URL` or `GRADING_AGENT_API_KEY` is empty.
- In Docker, Nginx serves `/uploads/videos/` directly from `nginx/default.conf` with `sendfile`/`mp4`; do not route local video streaming through FastAPI.
- Docker ports are loopback-bound: backend `127.0.0.1:8001->8000`, frontend `127.0.0.1:8080->80`.
