# CivicLoopAI backend

The FastAPI service, its database migrations and its tests. Everything the backend needs is inside this folder, so you can
deploy this folder on its own (Render, Railway, Fly, a VM) without the web app or the phone apps.

```
backend/
  civicloop/         the application (API, services, engines, jobs, AI, tenancy)
  migrations/        Alembic revisions 0001 to 0007
  tests/             pytest suite (123 tests)
  alembic.ini
  pyproject.toml     the package and its dependencies (uv reads this)
  uv.lock            the exact versions uv installs
  requirements.txt   the same dependencies for hosts that use pip instead of uv
  .python-version    Python 3.12.8 for hosts that read it
  .env.example       every setting, documented
```

## Run it locally

This project uses [uv](https://docs.astral.sh/uv/) (install it once: `pip install uv`, or see the uv site). `uv sync` makes the environment and installs the
exact versions in `uv.lock`; you never activate anything, you just put `uv run` in front of a command.

```bash
cd backend
uv sync                                    # environment + dependencies + test tools
uv run uvicorn civicloop.api:app --host 127.0.0.1 --port 8000
```

Run everything from `backend/`. The development database is `civicloop.db` in the folder you start from. Interactive API docs
are at http://127.0.0.1:8000/docs and the health check is `GET /health`.

```bash
uv run pytest -q                                           # 123 tests
uv run python -m civicloop.make_admin --email you@example.org --name "You" --city Chandigarh --pincode 160017
uv run python -m civicloop.demo --city Chandigarh            # demo reports, work orders and routes
uv run python -m civicloop.ml_tools seed --city Chandigarh   # 1,500 SIMULATED reports for the risk model
uv run python -m civicloop.worker                            # a separate job worker (only with CIVICLOOP_QUEUE_BACKEND=redis)
```

## Deploy on Render

You need three things: a PostgreSQL database, this folder as a web service, and (for photos) somewhere durable to keep files.

### 1. Create the database

Either of these works. The app accepts the `postgres://` and `postgresql://` addresses both give you and converts them to its driver itself.

**Option A: Supabase PostgreSQL** (what this project is set up for)

1. Create a project, then open **Connect** and choose the **Session pooler** address. It looks like
   `postgresql://postgres.<project-ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
2. **Do not use the "Direct connection" address** (`db.<project-ref>.supabase.co`). It only has an IPv6 address, so Render (IPv4 only) and many home networks
   cannot reach it.
3. If the password has characters such as `@`, `/`, `:` or `#`, write them percent-encoded in the address (`@` is `%40`). The simplest fix is a password of letters and digits.
4. The app adds `sslmode=require` for Supabase hosts itself. The Transaction pooler (port 6543) also works: prepared statements are switched off for it automatically.
5. Tables are created by the migrations (`alembic upgrade head`, part of the start command). The migrations also switch on **row-level security with no policies** on every table and
   take every privilege from Supabase's `anon` and `authenticated` roles. Without that, Supabase would publish these tables through its own public REST API. The app is not affected
   because it connects as the owner (`postgres`) role. Never give the app, or anyone, the project's `anon` or `service_role` keys for this data.
6. The free plan allows few connections through the pooler, so the app keeps a small pool (5 plus 5 spare). Change it with `CIVICLOOP_DB_POOL_SIZE` and `CIVICLOOP_DB_MAX_OVERFLOW`.

**Option B: Render PostgreSQL**

Choose **New, PostgreSQL** in Render. When it is ready, copy its **Internal Database URL** (use the **External** one only to run commands from your own computer).

### 2. Create the web service

Choose **New, Web Service**, connect the GitHub repo, then:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Runtime | Python 3. Pin the version with `.python-version`, or set the variable `PYTHON_VERSION=3.12.8`. |
| Build Command | `uv sync --frozen --no-dev` (installs the exact versions in `uv.lock`; if uv is not found on the build image, use `pip install uv && uv sync --frozen --no-dev`) |
| Start Command | `uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn civicloop.api:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health Check Path | `/health` |

`--no-sync` stops `uv run` from reinstalling anything at start-up. If your host uses pip instead, the build command is `pip install -r requirements.txt` and the start command is the same without `uv run --no-sync`. The start command applies any new database migrations before the app starts, and `--proxy-headers` makes the sign-in and
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
- **Supabase Storage** speaks the S3 protocol, so the same project can hold the photos. Create a **private** bucket, then in Storage settings create S3 access keys and copy the S3 endpoint and
  region. Set `CIVICLOOP_STORAGE_BACKEND=s3`, `CIVICLOOP_STORAGE_BUCKET` (the bucket name), `CIVICLOOP_STORAGE_ENDPOINT` (`https://<project-ref>.supabase.co/storage/v1/s3`),
  `CIVICLOOP_STORAGE_REGION` (your project's region, for example `ap-southeast-1`), `CIVICLOOP_STORAGE_ACCESS_KEY` and `CIVICLOOP_STORAGE_SECRET_KEY`.
- Or use any S3-compatible bucket (Cloudflare R2, Backblaze B2, AWS S3): set `CIVICLOOP_STORAGE_BACKEND=s3`,
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
uv sync
CIVICLOOP_DATABASE_URL="<database URL>" \
CIVICLOOP_ADMIN_PASSWORD="a long password" \
uv run python -m civicloop.make_admin --email you@example.org --name "Your Name" --city Chandigarh --pincode 160017
```

(Run it after the first deploy has created the tables.) Then sign in on the web app as that admin and add supervisors and drivers
on the Users page. Optional demo data: `CIVICLOOP_DATABASE_URL=... uv run python -m civicloop.demo --city Chandigarh`.

### 5. Point the other apps at it

- **Web app** (deployed on its own, e.g. a second Render service with Root Directory `frontend`, build `npm install && npm run build`,
  start `npm run start`): set `BACKEND_URL=https://<your-api>.onrender.com`. The web app proxies the API itself, so no CORS setup is needed.
- **Phone apps:** start them with `EXPO_PUBLIC_API_URL=https://<your-api>.onrender.com`, or type the address on the sign-in screen.
  Render serves HTTPS, so no special build settings are needed.

### 6. Cross-origin browser access (CORS), only if you need it

You normally do not. The web app reaches the API through its own server, and the phone apps are not browsers, so neither triggers CORS. Only a browser app
that calls the API directly from another address needs it. Set `CIVICLOOP_CORS_ORIGINS` to that app's address (comma separated, no trailing slash):

```
CIVICLOOP_CORS_ORIGINS=https://my-frontend.onrender.com
```

It is off by default, and a browser from any address not listed is refused.

### 7. Check it works

`https://<your-api>.onrender.com/health` returns `{"status":"ok"}`, and `/docs` lists the routes. In the logs you should see the
migrations run, then Uvicorn start.

### Things to know on Render
- **Reset any password you have pasted into a chat or a file.** In Supabase it is Project Settings, Database, Reset database password. Then update `CIVICLOOP_DATABASE_URL` in Render.
- **A free Supabase project pauses after a period of inactivity.** Check Supabase's current terms, and resume it from the dashboard if the API stops answering.

- **Free web services sleep** after a quiet period and take a while to wake. The in-process job worker is asleep too; jobs left in
  the database are picked up again when it wakes. A paid instance stays awake.
- **Free databases have limits** (size and an expiry period). Check Render's current terms, and use a paid database for a pilot.
- **Memory:** the route planner (OR-Tools) and the risk model (scikit-learn) need a few hundred MB. If an instance runs out of memory
  use a larger one. Duplicate detection falls back to word overlap unless you add `fastembed` (about 1 GB of memory); set
  `CIVICLOOP_EMBEDDINGS=off` to skip it entirely.
- **Logs and secrets:** never put `.env` in the repository. Set values in Render's Environment tab.

## Settings

All settings are environment variables. To deploy, paste [`render.env.example`](render.env.example) into Render's Environment tab after filling in the `PASTE_...` values. [`.env.example`](.env.example) is for running on your own computer. The full list, with defaults, is in the two files and in
[section 7 of the main README](../README.md#7-configuration).
