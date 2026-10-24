# CivicLoopAI backend

The FastAPI service, its database migrations and its tests. Everything the backend needs is inside this folder, so you can
deploy this folder on its own (Render, Railway, Fly, a VM) without the web app or the phone apps.

```
backend/
  civicloop/         the application (API, services, engines, jobs, AI, tenancy)
  migrations/        Alembic revisions 0001 to 0007
  tests/             pytest suite (123 tests)
  alembic.ini
  pyproject.toml     the package and its optional extras
  requirements.txt   what a host installs (pip install -r requirements.txt)
  .python-version    Python 3.12.8 for hosts that read it
  .env.example       every setting, documented
```

## Run it locally

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt            # or: pip install -e ".[api,ai,ml,migrations,queue,storage,postgres,dev]"
uvicorn civicloop.api:app --host 127.0.0.1 --port 8000
```

Run everything from `backend/`. The development database is `civicloop.db` in the folder you start from. Interactive API docs
are at http://127.0.0.1:8000/docs and the health check is `GET /health`.

```bash
python -m pytest -q                                        # 123 tests
python -m civicloop.make_admin --email you@example.org --name "You" --city Chandigarh --pincode 160017
python -m civicloop.demo --city Chandigarh                 # demo reports, work orders and routes
python -m civicloop.ml_tools seed --city Chandigarh        # 1,500 SIMULATED reports for the risk model
python -m civicloop.worker                                 # a separate job worker (only with CIVICLOOP_QUEUE_BACKEND=redis)
```

## Deploy on Render

You need three things: a PostgreSQL database, this folder as a web service, and (for photos) somewhere durable to keep files.

### 1. Create the database

In Render choose **New, PostgreSQL**. When it is ready, copy its **Internal Database URL** (use the **External** one only to run
commands from your own computer). Render gives it as `postgresql://...`; the app converts it to the psycopg driver itself.

### 2. Create the web service

Choose **New, Web Service**, connect the GitHub repo, then:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Runtime | Python 3. Pin the version with `.python-version`, or set the variable `PYTHON_VERSION=3.12.8`. |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `alembic upgrade head && uvicorn civicloop.api:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health Check Path | `/health` |

The start command applies any new database migrations before the app starts, and `--proxy-headers` makes the sign-in and
sign-up throttles see each visitor's real address instead of Render's.

### 3. Environment variables

| Variable | Value |
| --- | --- |
| `CIVICLOOP_ENV` | `production` |
| `CIVICLOOP_AUTH_SECRET` | a long random string (Render can generate one). **Required**, 32+ characters. |
| `CIVICLOOP_DATABASE_URL` | the Internal Database URL from step 1 |
| `CIVICLOOP_ALLOW_SINGLE_PROCESS` | `1`. You run one process with the in-process job worker. Jobs live in the database and are re-queued after a restart. (For several processes use `CIVICLOOP_QUEUE_BACKEND=redis` and a second service running `python -m civicloop.worker`.) |
| `CIVICLOOP_STORAGE_BACKEND` | `s3` (recommended) or `local`, see below |
| `CIVICLOOP_AI_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | your key (a new one: rotate any key that was ever pasted into a chat or a file) |
| `CIVICLOOP_PLATFORM_ADMINS` | the admin email(s) allowed to manage every city, comma separated |
| `CIVICLOOP_MODEL_DIR` | a folder on a persistent disk, if you train risk models (otherwise trained models are lost on redeploy and the app falls back to the built-in score) |

**Photos need durable storage.** A Render web service's own disk is wiped on every deploy.
- Use an S3-compatible bucket (Cloudflare R2, Backblaze B2, AWS S3): set `CIVICLOOP_STORAGE_BACKEND=s3`,
  `CIVICLOOP_STORAGE_BUCKET`, `CIVICLOOP_STORAGE_ENDPOINT` (for R2 and B2), `CIVICLOOP_STORAGE_REGION`,
  `CIVICLOOP_STORAGE_ACCESS_KEY` and `CIVICLOOP_STORAGE_SECRET_KEY`.
- Or attach a Render **persistent disk** to the service (a paid feature), mount it at `/var/data`, and set
  `CIVICLOOP_STORAGE_BACKEND=local` and `CIVICLOOP_STORAGE_ROOT=/var/data/uploads`.

The app refuses to start in production with in-memory storage, because every photo would vanish on a restart.

### 4. Create the first administrator

An address in `CIVICLOOP_PLATFORM_ADMINS` cannot be claimed through the sign-up form. From your own computer, point the command at
the database's **External Database URL**:

```bash
cd backend
pip install -r requirements.txt
CIVICLOOP_DATABASE_URL="<External Database URL>" \
CIVICLOOP_ADMIN_PASSWORD="a long password" \
python -m civicloop.make_admin --email you@example.org --name "Your Name" --city Chandigarh --pincode 160017
```

(Run it after the first deploy has created the tables.) Then sign in on the web app as that admin and add supervisors and drivers
on the Users page. Optional demo data: `CIVICLOOP_DATABASE_URL=... python -m civicloop.demo --city Chandigarh`.

### 5. Point the other apps at it

- **Web app** (deployed on its own, e.g. a second Render service with Root Directory `frontend`, build `npm install && npm run build`,
  start `npm run start`): set `BACKEND_URL=https://<your-api>.onrender.com`. The web app proxies the API itself, so no CORS setup is needed.
- **Phone apps:** start them with `EXPO_PUBLIC_API_URL=https://<your-api>.onrender.com`, or type the address on the sign-in screen.
  Render serves HTTPS, so no special build settings are needed.

### 6. Check it works

`https://<your-api>.onrender.com/health` returns `{"status":"ok"}`, and `/docs` lists the routes. In the logs you should see the
migrations run, then Uvicorn start.

### Things to know on Render

- **Free web services sleep** after a quiet period and take a while to wake. The in-process job worker is asleep too; jobs left in
  the database are picked up again when it wakes. A paid instance stays awake.
- **Free databases have limits** (size and an expiry period). Check Render's current terms, and use a paid database for a pilot.
- **Memory:** the route planner (OR-Tools) and the risk model (scikit-learn) need a few hundred MB. If an instance runs out of memory
  use a larger one. Duplicate detection falls back to word overlap unless you add `fastembed` (about 1 GB of memory); set
  `CIVICLOOP_EMBEDDINGS=off` to skip it entirely.
- **Logs and secrets:** never put `.env` in the repository. Set values in Render's Environment tab.

## Settings

All settings are environment variables. The full list, with defaults, is in [`.env.example`](.env.example) and in
[section 7 of the main README](../README.md#7-configuration).
