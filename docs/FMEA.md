# CivicLoopAI: Failure Mode and Effects Analysis (FMEA) and edge-case audit

Audit date: 2026-10-24. Scope: the whole backend (`civicloop/`), migrations, job worker, fleet tracking, the Next.js web app's auth handling and the Expo apps' storage. The analysis was written first without changing code; section 0 records the fixes made afterwards.

How it was done: static reading of the code with file and line numbers, plus what the test suite (93 tests) and the running test server showed earlier. **Nothing below was reproduced by running an attack or a load test.** Where a row depends on something I could not confirm, it says so (marked *unverified*).

Assumptions (correct me if wrong):

1. Target deployment is one FastAPI process (uvicorn) with Postgres in production; SQLite is only for development and demos. (`db.py:14-23` has Postgres pool settings, so this was intended.)
2. `CIVICLOOP_ENV` is the production switch (`api.py:135`).
3. Anyone on the internet can reach `/api/v1/auth/register` and `/api/v1/auth/login` (the apps require it).
4. The web app proxies `/api` through Next.js, so the API has no CORS rules (no `CORSMiddleware` anywhere in `civicloop/`).

Scoring: Severity (S), Likelihood (L), Detectability (D, where 10 = nobody would notice until it hurts), each 1-10. **RPN = S × L × D.**

---

## 0. Fix status (updated 2026-10-24, after the fixes)

Every row below was worked on; the table in section 2 is kept as it was found so you can see what each fix answers. 118 backend tests pass (93 earlier + 25 new in `tests/test_hardening.py`, plus a last-admin test in `tests/test_tenancy.py`); the full chain of migrations 0001 to 0007 builds a database the code accepts, and the web sign-in change was checked in a real browser.

| ID | Status | What changed and where | What is still true |
|---|---|---|---|
| F-01 | Fixed | `AttemptLimiter` in `api.py`: 8 wrong passwords per address+email per 5 min then 429 (`CIVICLOOP_LOGIN_ATTEMPTS`), a success resets it; sign-up limited to 60 per address per hour (`CIVICLOOP_REGISTER_LIMIT`); `max_length` on email and password | The counters live in one process. With several API processes, move them to Redis. |
| F-02 | Fixed | `JobRepository.claim/reclaim_stale/queued_ids`, `recover_jobs()` in `worker.py` (at start and every 60 s), `JobWorker.run_once` claims a job atomically and skips duplicates; a failed enqueue no longer loses the job | A job running longer than 10 minutes is treated as lost and run again, so handlers must be safe to repeat. |
| F-03 | Fixed | `db.py` turns on foreign keys, WAL and a 5 s lock wait for SQLite files. This exposed one real bug (the default city was inserted after rows pointing at it), fixed in `tenancy.default_tenant` | SQLite is still one writer. Use Postgres for a shared deployment. |
| F-04 | Fixed | `create_app` refuses in-memory storage or queue when `CIVICLOOP_ENV=production` | The default outside production is still memory. |
| F-05 | Fixed | A listed platform-admin address cannot be claimed through sign-up (403). New CLI `python -m civicloop.make_admin` creates the first administrator | There is still no email verification for ordinary sign-ups. |
| F-06 | Fixed | `assert_schema_current()` runs at start in production. A from-scratch `alembic upgrade head` was failing (migration 0003 omitted the `verified` column); fixed. New migration `0007_hardening` | Development still uses `create_all`, so delete an old dev database after a model change. |
| F-07 | Fixed | `InMemoryJobQueue.retry` uses a timer instead of `time.sleep` | |
| F-08 | Fixed in code, not run | Gemini client gets a 30 s HTTP timeout (`ai.py`) | The `google-genai` package is not installed in this Python, so that line was not executed here. |
| F-09 | Fixed | A session serving a signed-in request refuses `bind_tenant(None)`; the platform routes and `/auth/me` use the explicit `lift_scope()` | Reads are still filtered by one hook, not by the database (no row-level security). A route-by-route cross-city walk test was not added. |
| F-10 | Fixed | `municipal_integration.IMPORTABLE`: only real moves are accepted; others are skipped and show up as `received` minus `imported` | |
| F-11 | Fixed | New `civicloop/images.py`: JPEG, PNG, WebP and HEIC are recognised by their first bytes, stored under the real type, and photos are served with `nosniff` and a sandbox policy | |
| F-12 | Fixed | `Idempotency-Key` header on `POST /incidents`, unique `(reporter_id, client_key)`; the web form and both mobile apps send one key per report | |
| F-13 | **Finding was wrong** | `FleetService.record` already deletes pings older than 7 days (`KEEP_HISTORY`) on every ingest, so the table does not grow without bound | That delete runs on every fix; if it ever shows in profiles, run it once a minute instead. |
| F-14 | Fixed | Partial unique index `uq_work_order_live_per_incident`, `get_locked()` on the work-order read, the race now returns a clear 400 | Row locks only act on Postgres; on SQLite the file lock serialises writers anyway. |
| F-15 | Fixed | Unknown emails now verify against a dummy hash, so the timing matches | |
| F-16 | Partly fixed | Dashboard reads at most 50,000 reports, counts routes in SQL, loads stops only for open orders | Still builds its numbers in Python from up to 90 days of reports. Move to SQL aggregates if a city passes tens of thousands a quarter. |
| F-17 | Fixed | `occurred_at` is read as UTC when no zone is given and cannot be more than 5 minutes ahead | |
| F-18 | Fixed | Redis retries go in a sorted set and are promoted when due | Tested with a fake Redis, not a real server. |
| F-19 | Partly fixed | A route now loads its work orders and reports in 2 queries instead of 2 per stop; the plan list is capped at 100 | The list still runs about 4 queries per plan. |
| F-20 | Partly fixed | At most 8 photos per report; the upload no longer holds two copies | A photo is still held in memory (10 MB limit) before it is stored. |
| F-21 | Fixed | The incident row is locked, and an analysis made in the last 30 s is returned instead of paying for another | |
| F-22 | Fixed | `users.token_version` in every token; changing a password or `POST /auth/logout-all` ends all earlier sign-ins | |
| F-23 | Fixed | The vehicle row is locked while a position is recorded | Acts on Postgres only. |
| F-24 | **You must do this** | Nothing in code can fix a key that was pasted into a chat | Rotate the Gemini key now and keep `.env` out of zips and git (already excluded). |
| F-25 | Fixed | The web app now signs in through `frontend/src/app/api/v1/[...path]/route.ts`: the token lives in an httpOnly cookie (SameSite=Lax, Secure in production), the page keeps only a marker (who, role, expiry) that cannot call the API, and cross-site POSTs are refused. Security headers added in `next.config.ts` | No Content-Security-Policy yet: the map embeds need a tested policy. The mobile apps keep their token in the phone's secure storage. |
| F-26 | Fixed | Maximum lengths on descriptions, passwords, override reasons, system names, sensor readings and every list (routes 60, clusters 50, municipal 500) | |
| F-27 | Fixed | 240 requests per minute per vehicle on `/telemetry/gps`, then 429 | Per process. |
| F-28 | Fixed | One TTL variable (`CIVICLOOP_TOKEN_TTL_SECONDS`); a warning is logged when a random development secret is used | |
| F-29 | Fixed | Model and pointer files are written to a temporary name then swapped in; a failed model load is logged | A writable model folder is still a code-execution risk (it holds pickles). Keep it owned by the service account only. |
| F-30 | Fixed | Route requests are limited to 60 jobs | |
| F-31 | Fixed | `%` and `_` are escaped in the city search | |
| F-32 | Fixed | A city must be disabled before it can be merged | |
| F-33 | Fixed | The last active administrator of a city cannot be demoted or switched off | |
| F-34 | Fixed | A duplicate email or a city created at the same moment gives 409 or reuses the city, not a 500 | |
| F-35 | Fixed | `civicloop.api.app` is built on first use, not at import | |
| F-36 | Fixed | Job status needs a staff role | |
| F-37 | Fixed | A damaged stored hash is a failed sign-in | |

---

## 1. Architecture and entry points

**Architecture (8 lines)**

1. One FastAPI app built by `create_app()` (`api.py:118`); a module-level `app = create_app()` runs at import (`api.py:499`).
2. SQLAlchemy 2 over SQLite or Postgres. Schema is created by `Base.metadata.create_all` at startup (`db.py:33-37`, `api.py:148`); Alembic 0001-0006 exist but are not run by the app.
3. Auth: scrypt passwords, HMAC bearer tokens (`auth.py`), role and active state re-read from the DB on every request (`api.py:168-191`).
4. Multi-tenancy: a session-level hook adds `tenant_id = X` to every SELECT and stamps every INSERT (`tenancy.py:130-160`). Platform admins can switch city with `X-Tenant-Id`.
5. Work flow: incident → AI analysis (Gemini or open-weight) → supervisor work order → assignment to a driver → route per driver (OR-Tools) → worker evidence → supervisor verification.
6. Background jobs: `JobDispatcher` writes a `jobs` row then enqueues its id; a single `WorkerThread` in the API process (in-memory queue) or `python -m civicloop.worker` (Redis) runs it (`jobs.py:173-343`, `worker.py`).
7. Storage: in-memory, local disk, or S3 (`storage.py:229-247`); default is **in-memory**.
8. Fleet: phone positions and tracker pings go through `FleetService.record` (`services/fleet.py:153`) into `vehicles` and `vehicle_pings`.

**Entry points**

| Kind | Where | What |
|---|---|---|
| Public HTTP | `api.py:199, 203, 218, 277` | `/health`, `/api/v1/tenants?q=`, `/auth/register`, `/auth/login` |
| Authenticated HTTP (core) | `api.py:285-454` | incidents (create/list/get/status), media upload/list, analysis, job status |
| Authenticated HTTP (ops) | `routes_ops.py` (about 55 routes) | `/auth/me`, `/platform/cities*`, `/me/badges`, `/users*`, `/audit`, `/system/status`, `/jobs*`, risk/override/timeline/duplicates, `/queue`, `/work-orders*`, `/routes*` (incl. `/routes/mine`), verification, `/media/{id}/content`, `/evaluations*`, `/pilots*`, `/sensors*`, `/dashboard/*`, `/ml/*`, `/municipal/export|import` |
| Authenticated HTTP (fleet) | `routes_fleet.py` | `/vehicles*`, `/vehicles/mine`, `/vehicles/{id}/position`, `/vehicles/{id}/trail` |
| Device HTTP (no user) | `routes_fleet.py` `POST /telemetry/gps` | `X-Device-Key` header only |
| Background jobs | `job_handlers.py:49-64` | analyze_incident, detect_duplicates, calculate_hotspot_risk, generate_route, evaluate_dataset, pilot_metrics, municipal_export, sensor_ingest |
| Webhooks | none | no inbound webhooks; outbound only to Gemini / open-weight model (`ai.py`) |
| CLI | `python -m civicloop.worker` (`worker.py:66`), `civicloop.demo`, `civicloop.gps_sim`, `civicloop.ml_tools`, `alembic upgrade head`, `scripts/*.py` | worker, seed data, GPS simulator, model tools |

---

## 2. FMEA table (sorted by RPN, highest first)

| ID | Component | Failure mode | Cause | Impact | S | L | D | **RPN** | Current mitigation | Recommended fix |
|---|---|---|---|---|---|---|---|---|---|---|
| F-01 | `api.py:277-283`, `api.py:218-275`, `auth.py:36,46` | Credential stuffing and CPU exhaustion on login/register | No rate limit or lockout anywhere. scrypt (n=2^14, about 50 ms of CPU) runs inside sync handlers on the shared thread pool. `LoginRequest` and `RegisterRequest.password` have no max length (`api.py:60-62, 53`) | Accounts guessed with no throttle; a few hundred requests/second pin every worker thread so the whole API stalls | 7 | 7 | 8 | **392** | Passwords ≥ 12 chars; generic "Invalid credentials" | Per-IP+email attempt limiter, max lengths, cheap early reject (Fix 1) |
| F-02 | `jobs.py:304, 132-133, 222-226`; `repositories.py:411-416` | Jobs stuck `RUNNING` or never run | `mark_running` has no lease or timeout. If the process dies mid-job the row stays RUNNING forever. Redis `acknowledge` is a no-op and `lpop` is destructive (`jobs.py:119-133`), so a crash after pop loses the id. If `enqueue` fails after the row commit (`jobs.py:222-226`) the row stays QUEUED; the comment promises "a republisher" but none exists | Analysis, duplicate detection and risk scoring silently never happen; incidents sit in `pending_analysis` | 8 | 6 | 8 | **384** | `/jobs` list + manual retry (`routes_ops.py:549`) for FAILED/DEAD_LETTER only | Reaper + startup re-enqueue (Fix 2) |
| F-03 | `db.py:14-17` | `database is locked` 500s and unenforced foreign keys | SQLite connection has no `PRAGMA foreign_keys=ON`, no WAL, no `busy_timeout`; API threads and the worker thread write concurrently | Random 500s under any concurrent write; orphan rows (e.g. after city merge `routes_ops.py:427`) with no error | 8 | 7 | 6 | **336** | `check_same_thread=False` only | Pragmas on connect (Fix 5); use Postgres for anything shared |
| F-04 | `storage.py:229-233`, `jobs.py:346-349` | Total photo loss / job loss on restart | Defaults are `memory` for both storage and queue. A deployment that forgets two env vars keeps `media_assets` rows in the DB but the bytes only in RAM | All evidence photos return "Photo file is missing from storage" (`routes_ops.py` media content 404) after the first restart; queued jobs vanish | 9 | 6 | 6 | **324** | `/system/status` shows the backend names (`api.py:461-467`) | Refuse in-memory backends when `CIVICLOOP_ENV=production` (Fix 3) |
| F-05 | `api.py:180, 222-254`, `tenancy.py:52-55` | Platform-admin takeover by email squatting | Platform admin = `role == ADMIN and email in CIVICLOOP_PLATFORM_ADMINS`. Emails are never verified, and the first person to register a *new* city becomes its admin (`api.py:243-254`). If the listed email has not registered yet, anyone can register it into a new city and is instantly a platform admin | Full cross-city control: read/disable/merge/delete every city, impersonate any tenant with `X-Tenant-Id` | 10 | 4 | 8 | **320** | Env list is explicit; only matters before the real admin registers | Reserve those emails at registration (Fix 4) |
| F-06 | `db.py:33-37`, `api.py:148`, `migrations/0001` | Schema drift on existing databases | `create_all` only creates missing *tables*, never new columns. Migrations 0002-0006 are not run by the app. This already happened in this project: the test DB lacked the new `route_plans.worker_id` columns until recreated | Production deploy of new code against an old DB → `no such column` 500s on first touch of the table | 8 | 8 | 5 | **320** | Guarded, idempotent migrations exist | Fail fast on revision mismatch in production (Fix 6) |
| F-07 | `jobs.py:~88` (`InMemoryJobQueue.retry`) | Whole job pipeline frozen for up to 5 minutes | `retry` does `time.sleep(delay_seconds)` inside the single worker thread; `retry_delay` goes up to 300 s (`jobs.py:155-158`) | One failing Gemini call blocks every other queued job (analysis for all cities) while the thread sleeps | 7 | 7 | 6 | **294** | Max 3 attempts (`jobs.py:186`) | Schedule the retry with a timer instead of sleeping (Fix 7) |
| F-08 | `ai.py:102`, `worker.py:46` | Worker thread hung forever | `genai.Client(api_key=...)` is built with no HTTP timeout (the open-weight adapter has 30 s, `ai.py:158`). There is one worker thread | One stalled Gemini connection stops all background work and sync `POST /incidents/{id}/analysis` calls hold a request thread (`api.py:426`) | 8 | 5 | 7 | **280** | None for Gemini | Set `HttpOptions(timeout=30_000)` (Fix 7) |
| F-09 | `tenancy.py:85-91, 131-136` | Tenant isolation fails open | The read filter only applies when `session.info["tenant_id"]` is set; `bind_tenant(session, None)` removes it. `/auth/me` does this on purpose (`routes_ops.py:351`) and the worker does for jobs with a null `tenant_id`. Any new route or job that forgets `bind_tenant` sees every city. Only SELECTs are filtered (`tenancy.py:132`), not bulk UPDATE/DELETE | One missed line = cross-city data leak | 9 | 3 | 8 | **216** | 7 cross-city tests (`tests/test_driver_routes.py`, tenancy tests) | Make "no tenant" an error for request sessions; add a test that walks every route as a Pune user |
| F-10 | `services/municipal_integration.py:66-77`, `routes_ops.py:1138` | Work-order state machine bypass | `import_status_updates` sets `order.status = WorkOrderStatus(update["status"])` for any valid status. No transition check, no incident update, no assignee check | A supervisor (or a bad import file) can mark a DRAFT order COMPLETED, or ASSIGNED with no driver; routes and dashboards then show wrong state; incident stays open | 7 | 5 | 6 | **210** | Audit event `status_imported` | Allow only real transitions (Fix 8) |
| F-11 | `api.py:356`, `routes_ops.py` media content (`Response(... media_type=asset.content_type)`) | Stored file type is whatever the client claims | Only `content_type.startswith("image/")` is checked; bytes are never inspected, and `image/svg+xml` passes. The same type is echoed back | Non-images sent to the AI model (errors, wasted quota); SVG with script served from the API origin; no `nosniff` | 6 | 5 | 7 | **210** | Auth required to fetch; 10 MB cap | Sniff magic bytes, allow-list types (Fix 9) |
| F-12 | `api.py:285-301` | Duplicate reports on retry | `POST /incidents` has no idempotency key. A phone that times out and retries creates two incidents (and two analyses, work orders, etc.) | Duplicate queue items for supervisors; reporter confusion | 5 | 7 | 6 | **210** | Duplicate-detection feature flags near matches later | `Idempotency-Key` header with unique index (Fix 10) |
| F-13 | `models.py:437-443`, `services/fleet.py` | `vehicle_pings` grows without bound | Insert-only table, one row per fix; no retention or rollup. At 1 fix/5 s, 100 vehicles × 10 h ≈ 720k rows/day | Slow trail/day-distance queries, disk growth, slow backups within weeks | 6 | 8 | 4 | **192** | Index on `recorded_at`; trail capped at 600 rows (`fleet.py:233`) | Nightly delete of pings older than N days (keep daily totals on `Vehicle`) |
| F-14 | `services/work_order.py:36-37, 54-66, 68-86`; `models.py:251` | Lost updates and duplicate orders | Check-then-write with no row lock or unique constraint. Two supervisors assigning the same order to different drivers both get 200 and the last write wins. Two `create_order` calls for one incident both pass the "no active order" check | Order silently reassigned; a driver's job vanishes; two active orders for one incident | 6 | 4 | 8 | **192** | `assign_order` requires status APPROVED (only the first flush wins on SQLite's single writer) | Partial unique index on active order per incident; `with_for_update()` on `_get` |
| F-15 | `auth.py:110-115` | Account enumeration by timing | An unknown email returns before scrypt runs; a known email costs about 50 ms more | Attacker learns which emails have accounts; feeds F-01 | 4 | 6 | 8 | **192** | Same error text for both cases | Verify against a dummy hash when the user is missing (Fix 1) |
| F-16 | `services/dashboard.py:65-66, 143-145`, `routes_ops.py:1017` | Dashboard loads whole tables into memory | `select(Incident)` for the window plus all open ones, `select(RoutePlan)`, `select(RouteStop)` without limits; evaluation `route_saving` loads all plans | Supervisor dashboard slows and balloons memory as history grows; every page load pays it | 6 | 6 | 5 | **180** | 7-60 day window clamp (`routes_ops.py:1110`) | Aggregate in SQL (`COUNT ... GROUP BY`), cache for 30-60 s |
| F-17 | `api.py:70`, `models` DateTime | Time-zone mix-ups *(unverified: not reproduced)* | `occurred_at: datetime` accepts naive or any-offset values and far-future dates; SQLite hands back naive datetimes. `jobs.py` and `fleet.py` normalise with `as_utc`, incidents do not | Wrong ordering in risk/duplicate time features, or a `can't compare offset-naive and offset-aware` 500 | 5 | 6 | 6 | **180** | `as_utc` helpers exist for jobs/fleet | Validator: assume UTC if naive, reject > now + 5 min (Fix 10) |
| F-18 | `jobs.py:135-136, 295-303` | Redis worker spins at full speed | `RedisJobQueue.retry` ignores the delay and re-pushes at once. A job whose `available_at` is in the future is popped, re-pushed, popped... | 100% CPU and a flood of Redis writes for up to 5 minutes per backed-off job | 5 | 8 | 4 | **160** | In-memory queue sleeps instead (F-07) | Delayed set (sorted set by due time) |
| F-19 | `routes_ops.py` `route_dict` (about line 856), `repositories.py:325` | N+1 queries on routes | Per stop: `session.get(WorkOrder)`, `session.get(Incident)`; per plan: stops query + driver. `GET /routes` runs it for every plan with no limit | A city with 200 plans × 10 stops ≈ 4,000 queries per page load of the planner | 5 | 8 | 4 | **160** | None | Batch-load with `IN (...)` (Fix 10 notes) and paginate `list_all` |
| F-20 | `api.py:358-366` | Upload memory and storage abuse | Whole file is held as a list then `b"".join` (2× 10 MB per request); no limit on files per incident or per user | Memory spikes with parallel uploads; a resident can fill storage | 6 | 5 | 5 | **150** | 10 MB per file, 413 | Stream to storage; cap files per incident (say 8) |
| F-21 | `api.py:425-441` | Duplicate analyses and a blocked thread | Sync analysis (`async_mode=False`, the default) has no idempotency, calls the AI inline, and commits twice | Two double-clicks → two `analysis_results` rows and double AI spend; thread held for the AI latency | 5 | 5 | 6 | **150** | `async_mode` exists and is idempotent per `updated_at` | Make `async_mode` the default; reuse an existing result for the same incident revision |
| F-22 | `auth.py`, `api.py:168-191` | No way to revoke a token | Stateless 12 h bearer token; no logout list, no password reset flow, `set_password` does not invalidate old tokens (`auth.py:118-123`). Deactivation *is* honoured on each request (`api.py:175`) | A stolen token stays valid up to 12 h | 5 | 4 | 7 | **140** | Per-request `is_active` check | Add `token_version` on `User`, put it in the token, bump on password change |
| F-23 | `services/fleet.py:153-215` | Race on vehicle position and distance | Read `last_*` and `day_distance_km`, loop, write; no lock. The phone endpoint and a tracker can both post for one vehicle | Double-counted or negative-jump distance, "teleporting" position | 4 | 5 | 7 | **140** | Plausibility checks (speed ≤ 160 km/h, ±5 min) | `with_for_update()` on the vehicle row in `record` |
| F-24 | `.env`, chat history | Exposed API key | The Gemini key lives in plaintext `.env` and was pasted into the chat | Quota theft or billing abuse | 9 | 5 | 3 | **135** | `.env` is git-ignored and excluded from the zip | **Rotate the key now**; use a secret manager in production |
| F-25 | `frontend/src/lib/api.ts:375-403` | Token readable by any XSS | The bearer token is kept in `localStorage` | Any injected script can exfiltrate a 12 h session | 6 | 3 | 7 | **126** | No known XSS sink (React escapes by default); mobile uses SecureStore | httpOnly cookie via a Next route handler, or shorter TTL + refresh |
| F-26 | `api.py:51-57, 67`, `routes_ops.py:235, 292, 302`, `schemas` | Unbounded input | `description` has no max length; `RegisterRequest.password` none; `ClusterRequest.candidate_ids`, `MunicipalExport.work_order_ids`, `MunicipalImport.updates` have no `max_length`; sensor `reading` dict has no key limit (`routes_ops.py:283`) | Multi-MB text into DB, embeddings and AI prompts; million-item loops | 5 | 5 | 5 | **125** | Pydantic type checks; some list/limit clamps | Add `max_length` everywhere (Fix 10) |
| F-27 | `routes_fleet.py` `POST /telemetry/gps` | Unauthenticated flood path | Only a header key; no per-device rate limit; each call can carry 200 points | Insert flood into `vehicle_pings` from a leaked or guessed key; unknown-key requests still cost a DB lookup | 5 | 4 | 6 | **120** | SHA-256 key hash, plausibility drop, 200-point cap | Per-device rate limit; reject batches older than 24 h |
| F-28 | `api.py:137-140`, `auth.py:126-132` | Secret and TTL misconfiguration | Without `CIVICLOOP_AUTH_SECRET` (dev) each process makes a random secret: with 2 workers, half the requests 401 after login. Two different TTL env names: `CIVICLOOP_AUTH_TTL_SECONDS` (3600) in `auth.py:131` vs `CIVICLOOP_TOKEN_TTL_SECONDS` (12 h) in `api.py:140` | Intermittent 401s; surprise session length | 5 | 6 | 4 | **120** | Production refuses to start without a secret (`api.py:135`) | One TTL variable; delete the unused `authenticator_from_env` |
| F-29 | `risk_model.py:316-342`, `embeddings.py:97` | Silent fallbacks and unsafe deserialisation | `joblib.load` (pickle) of files in `CIVICLOOP_MODEL_DIR`; `except Exception: return None` hides corrupt models; embeddings fall back to word overlap silently (flagged per result as `text_method`). Pointer file and model file are written non-atomically (`risk_model.py:322-323`) | A writable model dir means code execution; a bad model quietly gives heuristic risk scores | 5 | 3 | 8 | **120** | Model dir is local, not user-supplied; `text_method` reported | Log + metric on fallback; write to temp then `os.replace`; keep the dir root-owned |
| F-30 | `routes_ops.py:239`, `engines/routing.py:29, 207` | Large route request | `work_order_ids` has no upper bound; the distance matrix is built before OR-Tools' 2 s limit applies | One supervisor request with thousands of ids burns CPU/RAM | 6 | 3 | 6 | **108** | 2 s solver limit | `max_length=60` (Fix 10) |
| F-31 | `api.py:212` | `/tenants?q=` wildcard leak | `Tenant.name.ilike(f"{needle}%")` leaves `%` and `_` unescaped: `q=__` lists the first 8 verified cities. The docstring says the list "cannot be dumped" | Cities can still be enumerated by walking prefixes, but at most 8 per request | 3 | 5 | 7 | **105** | 2-character minimum, limit 8 | Escape wildcards; per-IP rate limit |
| F-32 | `routes_ops.py:427-446` | City merge races | Moves rows table by table then deletes the source; concurrent writes into the source city during the merge are orphaned (no FK enforcement on SQLite, F-03) | Lost rows in a rare admin action | 7 | 2 | 7 | **98** | Single transaction; audit event | Disable the city first, then merge |
| F-33 | `routes_ops.py:483-508` | Admin lock-out | Only "change yourself" is blocked; two admins can demote or deactivate each other, or the last other admin | City left with no administrator | 6 | 3 | 5 | **90** | Self-change blocked | Refuse if it would leave zero active admins |
| F-34 | `api.py:222-266`, `tenancy.py:64-70`, `models.py:113` | Registration race returns 500 | Check-then-insert on email (unique) and on city slug (unique); concurrent duplicates raise `IntegrityError` | Rare 500 instead of 409 | 4 | 5 | 4 | **80** | Unique constraints keep the data correct | Catch `IntegrityError` → 409 / re-select the tenant |
| F-35 | `api.py:499` | App built at import time | `app = create_app()` runs for any `import civicloop.api` (tests, tools): creates `civicloop.db` in the CWD and storage/queue objects | Stray DB files; surprising side effects | 3 | 6 | 4 | **72** | Tests pass their own app | Use an app factory (`uvicorn --factory`) |
| F-36 | `api.py:452` | Job status readable by anyone in the city | Jobs with `created_by` null pass the check for any role, including residents | Low-value metadata leak | 3 | 3 | 6 | **54** | City filter applies | Require staff role |
| F-37 | `auth.py:43-46` | Malformed hash → 400 with internals | `encoded.split("$", 3)` unpacking raises `ValueError` on a corrupted hash; the global `ValueError` handler returns its message (`api.py:492-494`) | Rare; leaks an internal error string | 3 | 2 | 5 | **30** | Hashes are only written by `hash_password` | Wrap in try/except → `False` |

---

## 3. Edge cases by endpoint

"Expected" is what the code should do; "Finding" is what reading it shows. Examples were traced through the code, not executed unless marked *(tested)*.

| Endpoint / function | Input | Finding |
|---|---|---|
| `POST /auth/register` | `email: "A@B.com"` then `"a@b.com"` | Lower-cased at `api.py:221` → 409 on the second. OK. |
| | `email: "a@b.c"`; `"a@b.c "` (trailing space) | Regex `^[^@\s]+@[^@\s]+\.[^@\s]+$` rejects the space with 422; one-letter TLD passes. |
| | `password` of 10 MB | No `max_length` (`api.py:53`); read into memory and scrypt'd. See F-01. |
| | `city: "Chandigarh"` vs `"chandigarh "` vs `"Chandīgarh"` | `slugify` merges case/space; the accented spelling becomes a separate unverified city (platform merge exists for this). |
| | `role: "admin"` with no token, for an existing city | 403 "Cannot register with elevated role…" (`api.py:249-253`) *(tested)*. For a **new** city: allowed, becomes its admin. |
| | `pincode: "16001"` / `"１６００１７"` (full-width digits) | `normalise_pincode` handles format; unicode digits: unverified. |
| `POST /auth/login` | `email: null` | 422 (type check). `email: ""` → 401. |
| | wrong password 1,000× | No lockout (F-01). |
| `POST /incidents` | `description: ""` | 422. `description: "   "` passes `min_length=1`. |
| | `latitude: 91`, `longitude: NaN` | 91 → 422; `NaN` fails `ge/le` comparisons → 422. |
| | `occurred_at: "2099-01-01T00:00:00Z"` / `"0001-01-01"` / `"2026-10-24T10:00:00"` (no zone) | All accepted (F-17). |
| | same body twice | Two incidents (F-12). |
| | `description` with emoji/RTL/NUL byte `\u0000` | Emoji and RTL are stored fine; NUL breaks Postgres text columns → 500 *(unverified)*. |
| `GET /incidents` | `limit=-5` / `limit=1000000` / `limit=abc` | Clamped to 1..200 (`api.py:315`); `abc` → 422. |
| | `pincode="  "` | `normalise_pincode` returns None → no filter. |
| `PATCH /incidents/{id}/status` | any status not in `MANUAL_TRANSITIONS` | 409 with a readable reason (`api.py:337`). |
| `POST /incidents/{id}/media` | 0-byte file | 400 "cannot be empty". |
| | exactly 10 MB + 1 byte | 413. |
| | `Content-Type: image/svg+xml`, body is `<svg onload=...>` | Accepted (F-11). |
| | same photo uploaded twice | Depends on how `storage_key` is derived (`models.py:170` is unique). *Unverified*; if it is content-derived this is a 500. |
| `POST /incidents/{id}/analysis` | called twice quickly, sync mode | Two result rows (F-21). |
| | Gemini returns invalid JSON / 429 | `AIAdapterError` → 502 with its message (`api.py:480-482`); in a job it retries then dead-letters. |
| `POST /work-orders/{id}/assign` | worker deactivated after approval | `require_user` is checked at assign time only; a later deactivation leaves the order with an inactive driver. Supervisor must notice. |
| | two supervisors, different drivers, same instant | Last write wins (F-14). |
| `POST /routes`, `/routes/preview` | `work_order_ids: []` | 422 (`min_length=1`) *(tested)*. |
| | same id twice in the list | Not de-duplicated before OR-Tools: stop appears twice or the plan fails *(unverified)*. |
| | ids from two drivers / not assigned | 400 with names *(tested)*. |
| | `vehicle_capacity: 1e308` | Passes `gt=0`. |
| `POST /routes/{id}/approve` | called twice | 400 "already approved" *(tested)*. |
| | job completed between plan and approve | 400 "Plan the route again" *(tested)*. |
| `GET /routes/mine` | worker with zero routes | `[]` *(tested)*. |
| `POST /vehicles/{id}/position` | `speed_kmh: 400` / `500` | 400 allowed by schema (`le=400`) but the service drops > 160 as implausible; 500 → 422. |
| | `recorded_at` 2 h in the future / 3 days old | Dropped by plausibility rules; response says `dropped` count. |
| | two phones, same vehicle | Race (F-23). |
| `POST /telemetry/gps` | `points` 201 entries | 422 (`max_length=200`). |
| | wrong key / disabled vehicle / disabled city | 401 / 401 / 403 (`routes_fleet.py` device_vehicle). |
| | batch with out-of-order `recorded_at` | Sorted by time before use (`fleet.py:157`). |
| `POST /municipal/import` | `status: "completed"` for a DRAFT order | Applied (F-10). |
| | unknown `work_order_id` | Skipped silently (`municipal_integration.py:68`); response shows `imported` vs `received`. |
| `POST /sensors/readings` | `reading: {"a": "x" * 10_000_000}` | No size limit (F-26). |
| `GET /evaluations`, `/dashboard/*` | city with 1M incidents | Loads all rows (F-16). |
| `GET /api/v1/tenants?q=` | `q=%`, `q=__` | Wildcards honoured (F-31). |
| Job `analyze_incident` | incident deleted before the job runs | Handler raises → retry ×3 → dead-letter, 3 pointless Gemini-free retries with growing sleeps (F-07). |
| Job worker | two API processes share one SQLite file with in-memory queues | Each process runs its own worker; jobs created in A are only in A's queue. |

---

## 4. Single points of failure and what breaks first

**Single points of failure**

1. **The one API process hosts everything**: HTTP, the only worker thread, and the in-memory queue (`api.py:142-144`). Restart = lost queue (F-02, F-04).
2. **One worker thread** (`worker.py:46`), and it sleeps in `InMemoryJobQueue.retry` (F-07) and waits on Gemini with no timeout (F-08).
3. **The SQLite file** (dev/demo) with a single writer and no WAL (F-03). On Postgres the pool is 20+10 (`db.py:19-20`), which is fine for one process.
4. **Local/in-memory object storage** (F-04): photos are the legal evidence of a cleanup.
5. **Gemini** is the only analysis provider configured; failure queues work but does not degrade to anything.
6. **The platform admin email list and the first-registrant rule** (F-05).
7. **The signing secret**: one value signs every token; rotating it logs everyone out (no key id in the token).

**First thing to break under load (10× traffic)**

In this order:

1. **Login CPU** (F-01): scrypt on the request thread pool; a login burst starves unrelated requests.
2. **SQLite write lock** (F-03): "database is locked" 500s as soon as the worker thread, GPS pings (one write every few seconds per vehicle) and request writes overlap.
3. **Job backlog**: one worker thread plus a sleeping retry (F-07) means analysis latency grows without bound while the queue shows "queued".
4. **Per-request overhead**: every request runs `current_principal` (user query + tenant query, `api.py:174-179`) and then the route; route lists then add N+1 queries (F-19) and the dashboard reads whole tables (F-16).
5. **`vehicle_pings` size** (F-13) after a few weeks.

---

## 5. Top 10 fixes

None of these have been applied. Each shows the change I would make.

### 1. [Critical] Throttle and harden login and registration (F-01, F-15)

Files: `civicloop/api.py:50-62, 277-283`, `civicloop/auth.py:108-116`.

Problem: unlimited password guesses and unbounded CPU use; unknown emails answer faster than known ones.

```python
# api.py: new, above create_app()
import time
from collections import defaultdict, deque

class AttemptLimiter:
    """Allow `limit` failures per key in `window` seconds (per process; use Redis if you run several)."""
    def __init__(self, limit: int = 8, window: int = 300) -> None:
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def check(self, key: str) -> None:
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.", headers={"Retry-After": str(self.window)})

    def fail(self, key: str) -> None:
        self.hits[key].append(time.monotonic())

login_limiter = AttemptLimiter()

class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
# RegisterRequest.password: Field(min_length=12, max_length=256)

# in login(payload, request: Request, ...):
key = f"{request.client.host if request.client else '-'}:{payload.email.strip().lower()}"
login_limiter.check(key)
try:
    token = AuthenticationService(...).login(payload.email, payload.password)
except AuthenticationError as error:
    login_limiter.fail(key)
    raise HTTPException(status_code=401, detail="Invalid credentials") from error
```

```python
# auth.py: module level, and in AuthenticationService.login (line 110)
_DUMMY_HASH = hash_password("not-a-real-password")

user = self.users.get_by_email(email.strip().lower())
ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
if user is None or not user.is_active or not ok:
    raise AuthenticationError("Invalid credentials")
```

### 2. [Critical] Make jobs recoverable (F-02)

Files: `civicloop/repositories.py` (near line 411), `civicloop/worker.py:55-63`, `civicloop/jobs.py:222-226`.

Problem: a crash leaves jobs RUNNING forever or loses them from the queue.

```python
# repositories.py, JobRepository
def reclaim_stale(self, older_than) -> list[str]:
    """Put jobs whose worker died back in the queue; give up after max_attempts."""
    ids = []
    for job in self.session.scalars(select(Job).where(Job.status == JobStatus.RUNNING, Job.started_at < older_than)):
        if job.attempt_count >= job.max_attempts:
            job.status, job.last_error_code = JobStatus.DEAD_LETTER, "worker_lost"
        else:
            job.status = JobStatus.QUEUED
            ids.append(job.id)
    self.session.flush()
    return ids

def queued_ids(self) -> list[str]:
    return list(self.session.scalars(select(Job.id).where(Job.status == JobStatus.QUEUED)))
```

```python
# worker.py, WorkerThread._run: before the loop, and then once a minute
def _recover(self) -> None:
    with self.worker.session_factory() as session:
        repo = JobRepository(session)
        ids = repo.reclaim_stale(utc_now() - timedelta(minutes=10)) + repo.queued_ids()
        session.commit()
    for job_id in dict.fromkeys(ids):
        self.worker.queue.enqueue(job_id)
```

Also make `JobWorker.run_once` skip a delivery whose job is already RUNNING, so a duplicate id is harmless.

### 3. [Critical] Refuse volatile storage and queue in production (F-04)

File: `civicloop/api.py` after line 130.

Problem: two forgotten environment variables silently lose every photo and queued job on restart.

```python
if os.getenv("CIVICLOOP_ENV", "development").lower() == "production":
    if isinstance(storage, InMemoryObjectStorage):
        raise ValueError("Set CIVICLOOP_STORAGE_BACKEND=local or s3 in production; in-memory storage loses every photo on restart")
    if isinstance(queue, InMemoryJobQueue):
        raise ValueError("Set CIVICLOOP_QUEUE_BACKEND=redis in production and run `python -m civicloop.worker`")
```
(import `InMemoryObjectStorage` from `civicloop.storage`.)

### 4. [Critical] Reserve platform-admin emails (F-05)

File: `civicloop/api.py` after line 235 (once `caller_admin` is known).

Problem: an unverified registration can claim a listed platform-admin address.

```python
if email in platform_admin_emails() and caller_admin is None:
    raise HTTPException(status_code=403, detail="This address is reserved. Ask an existing administrator to create the account.")
```
Bootstrap the first platform admin with a one-off CLI (`python -m civicloop.make_admin --email ... --city ...`) that writes the user directly. Longer term: email verification before any admin power.

### 5. [High] SQLite pragmas (F-03)

File: `civicloop/db.py:14-23`.

Problem: no foreign keys, no write-ahead log, no wait on locks.

```python
from sqlalchemy import event

def create_engine(database_url: str = "sqlite:///civicloop.db", **kwargs: Any) -> Engine:
    if database_url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False, "timeout": 10})
        engine = sqlalchemy_create_engine(database_url, **kwargs)

        @event.listens_for(engine, "connect")
        def _pragmas(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine
    kwargs.setdefault("pool_size", 20)
    ...
```
Run the full suite after enabling foreign keys; it may expose tests that rely on orphan rows.

### 6. [High] Fail fast on schema mismatch (F-06)

Files: `civicloop/db.py` (new function), `civicloop/api.py:148`.

Problem: new code on an old database fails at the first query that touches a new column.

```python
def assert_schema_current(engine: Engine) -> None:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise RuntimeError(f"Database is at revision {current}, this code needs {head}. Run: alembic upgrade head")
```
In `lifespan`: `if production: assert_schema_current(engine) else: init_db(engine)`.

### 7. [High] Stop the worker from stalling (F-07, F-08, F-18)

Files: `civicloop/jobs.py:~88`, `civicloop/jobs.py:135-136`, `civicloop/ai.py:102`.

Problem: retries sleep inside the only worker thread; Gemini has no timeout; Redis retries spin.

```python
# jobs.py, InMemoryJobQueue.retry: schedule instead of sleeping
def retry(self, delivery: JobDelivery, delay_seconds: int) -> None:
    timer = threading.Timer(max(0, delay_seconds), self.enqueue, args=(delivery.job_id, delivery.priority))
    timer.daemon = True
    timer.start()
```
```python
# jobs.py, RedisJobQueue: delayed set so the worker never sees a job early
def retry(self, delivery, delay_seconds):
    self.client.zadd(f"{self.prefix}:delayed", {delivery.job_id: time.time() + delay_seconds})

def dequeue(self):
    for job_id in self.client.zrangebyscore(f"{self.prefix}:delayed", 0, time.time()):
        if self.client.zrem(f"{self.prefix}:delayed", job_id):
            self.enqueue(job_id)
    ...  # then the existing priority pops
```
```python
# ai.py:102
from google.genai import types as genai_types
client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"), http_options=genai_types.HttpOptions(timeout=30_000))
```

### 8. [High] Validate municipal status imports (F-10)

File: `civicloop/services/municipal_integration.py:66-77`.

Problem: imported statuses overwrite the work-order state machine.

```python
ALLOWED = {
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.APPROVED: {WorkOrderStatus.CANCELLED},
}
...
try:
    new = WorkOrderStatus(update["status"])
except ValueError:
    continue
if new not in ALLOWED.get(order.status, set()):
    skipped += 1
    continue
order.status = new
```
Return `skipped` too, and have `routes_ops.py:1138` include it in the response so the supervisor sees what was refused.

### 9. [High] Check what is actually uploaded (F-11)

Files: `civicloop/api.py:356` and the verification upload (`routes_ops.py:945-955`), media content response in `routes_ops.py`.

Problem: any `image/*` label is trusted, including SVG.

```python
def sniff_image(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[4:8] == b"ftyp" and content[8:12] in (b"heic", b"heix", b"mif1"):
        return "image/heic"  # iPhone photos
    return None

detected = sniff_image(content)
if detected is None:
    raise HTTPException(status_code=400, detail="Upload a JPEG, PNG, WebP or HEIC photo")
asset = ...store_for_incident(incident_id, content, detected)
```
And add `"X-Content-Type-Options": "nosniff"` to the headers in `media_content`.

### 10. [Medium] Bound inputs and make creating a report safe to retry (F-12, F-17, F-19, F-26, F-30)

Files: `civicloop/api.py:50-72`, `civicloop/routes_ops.py:235, 239, 292, 302`, `civicloop/models.py` (Incident), a new migration `0007`.

```python
# api.py
class IncidentCreateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _utc_and_not_future(cls, value: datetime) -> datetime:
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("occurred_at cannot be in the future")
        return value
```
```python
# routes_ops.py
work_order_ids: list[str] = Field(min_length=1, max_length=60)     # RouteCreate, MunicipalExport
candidate_ids: list[str] = Field(min_length=1, max_length=50)      # ClusterRequest
updates: list[StatusUpdate] = Field(min_length=1, max_length=500)  # MunicipalImport
```
```python
# models.py: Incident
client_key: Mapped[str | None] = mapped_column(String(64))
__table_args__ = (UniqueConstraint("reporter_id", "client_key", name="uq_incident_client_key"),)
```
`create_incident` reads an `Idempotency-Key` header, looks up `(reporter_id, client_key)` first, and returns the existing incident with 200; both mobile apps' report form sends one UUID per draft.
For F-19, load route stops with one query each for work orders and incidents (`where(WorkOrder.id.in_(ids))`) instead of `session.get` per stop, and put a `limit` on `RoutePlanRepository.list_all` (`repositories.py:325`).

---

## 6. What I did not cover

- No load test, fuzzing or dependency vulnerability scan was run; ratings for likelihood are judgement from the code.
- The mobile background-location queue (`mobile/apps/crew/src/location/sharing.ts`) and the Next.js pages were only checked for token handling.
- `services/` modules I did not read line by line: `risk`, `duplicates`, `priority`, `evaluation`, `pilot`, `iot`, `ml`.
- Items marked *unverified* above need a quick reproduction before you spend time on them.
