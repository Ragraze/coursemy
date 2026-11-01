# Coursemy

A server-rendered catalog for free Udemy coupon courses. Coursemy mirrors an upstream course feed into a local database, then serves fast search, filtering, sorting, pagination, course details, and per-visitor bookmarks without any frontend framework.

Built with FastAPI, Jinja2, HTMX, Alpine.js, Tailwind CSS, SQLAlchemy 2, and Alembic. SQLite is used for local development, PostgreSQL for production.

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Requirements](#requirements)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Catalog synchronization](#catalog-synchronization)
- [HTTP API](#http-api)
- [Bookmarks](#bookmarks)
- [Testing](#testing)
- [Docker](#docker)
- [Production deployment](#production-deployment)
- [Storage and backups](#storage-and-backups)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Local catalog cache** — search, filter, sort, and pagination run against the local database, so the UI stays responsive even when the upstream is slow or unavailable.
- **Full and incremental sync** — startup and the scheduler crawl the entire upstream catalog; the manual refresh endpoint can fetch only the first page or the full catalog.
- **Course details on demand** — enrollment URLs, coupon codes, learning outcomes, target audience, and requirements are fetched lazily and cached for six hours.
- **Coupon handling** — coupon codes are extracted only from valid `https://*.udemy.com` enrollment URLs, so no code is invented or guessed.
- **Cover images** — covers are downloaded from allowed Udemy CDN hosts, resized to 640×360 JPEG with Pillow, and stored locally. Failed downloads fall back to a local placeholder.
- **Per-visitor bookmarks** — bookmarks are scoped to an anonymous `HttpOnly` cookie; no account is required.
- **HTMX partial rendering** — search, filters, and pagination update only the results block. Every interaction still works without JavaScript thanks to plain GET forms and pagination links.
- **Progressive enhancement** — Alpine.js handles small disclosures; Lucide SVG icons are inlined.
- **Embedded scheduler** — APScheduler refreshes the catalog twice per hour (`Asia/Jakarta`).
- **Database-level sync lock** — concurrent syncs are prevented by a lease with heartbeat, so a crashed process cannot deadlock the catalog forever.
- **Automatic SQLite/PostgreSQL support** — the same schema and migration path work for both engines.

## How it works

```
                 ┌──────────────────────────────┐
                 │  Upstream course API         │
                 │  (courses, categories,       │
                 │   details, practice tests)   │
                 └───────────────┬──────────────┘
                                 │ httpx (async, retries)
                                 ▼
  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
  │  APScheduler │────▶│  Sync service    │────▶│  SQLite /       │
  │  manual API  │     │  catalog.py      │     │  PostgreSQL     │
  └──────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
  ┌──────────────┐     ┌──────────────────┐               │
  │  Browser     │◀───▶│  FastAPI + Jinja │◀──────────────┘
  │  HTMX/Alpine │     │  HTML + JSON API │
  └──────────────┘     └──────────────────┘
```

1. On startup, Alembic migrations must already be applied. The app then mounts static files and, if `INITIAL_SYNC_ENABLED` is set, starts a background full sync when no prior full sync exists.
2. Pages are fetched in batches and upserted inside short transactions. The catalog is readable during a sync, so the first start can serve partial data.
3. Covers are downloaded concurrently (with a small semaphore) and resized before being written to `BLOB_DIR`.
4. Course details are refreshed lazily per course and cached for six hours. Category caches last one day.
5. Every visitor receives an anonymous cookie; bookmarks are stored against that identifier.

## Project structure

```
.
├── app/
│   ├── main.py              # App factory, lifespan, middleware, exception handlers
│   ├── config.py            # Pydantic settings loaded from environment / .env
│   ├── database.py          # Engine, session factory, SQLite PRAGMAs
│   ├── models.py            # Course, SavedCourse, CatalogMeta
│   ├── schemas.py           # Pydantic response models (camelCase aliases)
│   ├── routers/
│   │   ├── courses.py       # JSON catalog API
│   │   ├── admin.py         # Catalog refresh endpoint
│   │   ├── pages.py         # HTML pages and HTMX partials
│   │   └── dependencies.py  # DB, upstream, and query-filter dependencies
│   ├── services/
│   │   ├── catalog.py       # Sync, upsert, query, stats, locks, normalization
│   │   ├── upstream.py      # httpx client with retries and payload validation
│   │   ├── images.py        # Cover download and resize
│   │   └── coupon.py        # Enrollment URL and coupon code validation
│   ├── templates/           # Jinja2 templates and HTMX partials
│   └── static/              # CSS, JS, placeholder, downloaded covers
├── alembic/                 # Migration environment and versions
├── scripts/build_css.py     # Tailwind standalone CLI builder (no Node)
├── tests/                   # pytest suite with mocked upstream
├── docs/                    # Tech stack review and verification notes
├── Dockerfile               # Multi-stage image (CSS build + runtime)
├── docker-compose.yml       # App + PostgreSQL 17
└── requirements.txt
```

## Tech stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12+ |
| Web framework | FastAPI |
| ASGI server | Uvicorn (Gunicorn + `uvicorn-worker` in production) |
| Templating | Jinja2, server-side rendering |
| Interactivity | HTMX and Alpine.js via CDN |
| Styling | Tailwind CSS standalone CLI (v4.1.17), no Node project |
| Icons | Inline Lucide SVG |
| Database | SQLite (development), PostgreSQL 17 (production) |
| ORM / migrations | SQLAlchemy 2.0, Alembic |
| Validation | Pydantic v2 and pydantic-settings |
| HTTP client | httpx `AsyncClient` with retries |
| Images | Pillow |
| Scheduling | APScheduler `BackgroundScheduler` |
| Testing | pytest, `httpx.MockTransport` |

## Requirements

- Python **3.12 or newer**, including the `venv` module (`python3-venv` on Debian/Ubuntu).
- Network access for the upstream catalog, the Tailwind CLI download, and cover images.
- Docker and Docker Compose only if you deploy with containers.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp -n .env.example .env            # adjust values if needed
alembic upgrade head               # create the schema
python scripts/build_css.py        # build app/static/css/style.css
uvicorn app.main:app --reload
```

Open:

- Catalog: <http://127.0.0.1:8000/courses>
- Landing page: <http://127.0.0.1:8000/>
- Swagger UI: <http://127.0.0.1:8000/api/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

### Tailwind CSS

`scripts/build_css.py` downloads the official standalone Tailwind CLI (`v4.1.17`) from GitHub releases on first use, then compiles `app/static/css/input.css` into `app/static/css/style.css`. No Node.js project is required.

- Use an existing binary: `TAILWIND_BIN=/path/to/tailwindcss python scripts/build_css.py`
- Watch mode: `python scripts/build_css.py --watch`
- A bootstrap `style.css` is committed so the UI stays usable before the first build; run the builder for the complete utility CSS.

### Using the Make-free workflow

All commands are plain shell commands; there is no `Makefile` dependency. Run the app from the repository root so SQLite paths and templates resolve correctly.

## Configuration

Settings are read from environment variables or a local `.env` file (see `.env.example`).

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Coursemy` | Application name shown in templates and the API info endpoint. |
| `UPSTREAM_API_BASE` | `https://courspora.my.id/api` | Base URL of the upstream catalog API. |
| `DATABASE_URL` | `sqlite:///./courspora.db` | SQLAlchemy URL. Use `postgresql+psycopg://...` for PostgreSQL. |
| `BLOB_DIR` | `app/static/blobs` | Directory for downloaded course covers. Must be writable and persistent. |
| `SCHEDULER_ENABLED` | `true` | Enables the embedded APScheduler job. Keep it enabled on **one** process only. |
| `INITIAL_SYNC_ENABLED` | `true` | Runs a full catalog sync on first startup when none has completed before. |
| `COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS. |
| `REFRESH_COOLDOWN_SECONDS` | `60` | Global cooldown between catalog refreshes (`0`–`3600`). Too-frequent requests return `429` with `Retry-After`. |

The fixed list of 13 Udemy categories lives in `app/services/catalog.py`. Category order from the upstream `listCategories` endpoint has not been verified against a live source; treat it as a documented assumption.

## Catalog synchronization

- **Startup** — a full sync runs in the background the first time the catalog is empty. The server responds immediately and may serve partial results while the sync completes.
- **Scheduler** — with `SCHEDULER_ENABLED=true`, a full sync runs at minute `00` and `30` of every hour (`Asia/Jakarta`). A running sync is never stacked with the next scheduled run (`max_instances=1`, coalescing enabled).
- **Manual, first page** — `POST /api/catalog/refresh` fetches the first page of courses and practice tests (up to 15 items per kind). No admin token is required.
- **Manual, full catalog** — `POST /api/catalog/refresh?full=true` crawls every page and waits for completion. Increase your reverse-proxy timeout for large catalogs.
- **Legacy alias** — `POST /api/catalog/refreshCourses` is deprecated but still works.
- **Locking** — a database lease (`sync_lock`, 10 minutes) with a per-batch heartbeat prevents overlapping syncs. If a process dies, the lease expires and the next sync proceeds.
- **Pagination safety** — a full sync aborts with an upstream error if the source repeats a page or stops before the reported total is reached.
- **Failure behavior** — upstream failures are retried twice with exponential backoff. A failed refresh leaves the previously cached catalog intact and records the error in `catalog_meta`.
- **Expiration** — `isExpired` follows the upstream flag. A course is never removed because it is missing from a later upstream page, and a coupon is never marked valid just because the course still exists.

Example requests:

```bash
curl -X POST http://127.0.0.1:8000/api/catalog/refresh
curl -X POST 'http://127.0.0.1:8000/api/catalog/refresh?full=true'
curl 'http://127.0.0.1:8000/api/courses/search?q=python'
curl 'http://127.0.0.1:8000/api/courses?category=Development&sort=rating&page=2'
```

## HTTP API

Interactive documentation is available at `/api/docs` (Swagger UI) and `/redoc`.

### Catalog

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/courses` | Paginated catalog. Accepts all filter parameters below. |
| `GET` | `/api/courses/search` | Same as `/api/courses`; kept as an explicit search route. |
| `GET` | `/api/courses/{slug_part}` | Course detail; refreshes from upstream when the cache is older than six hours. |
| `GET` | `/api/courses/{slug_part}/related` | Up to three related courses from the same category. |
| `GET` | `/api/categories` | The 13 supported categories. |
| `GET` | `/api/info` | Application name, upstream base URL, and documentation links. |
| `GET` | `/api/stats` | Catalog, sync, and bookmark statistics for the current visitor. |

Filter parameters:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | integer | `1` | `1`–`100000`; clamped to the last page when out of range. |
| `q` | string | empty | Up to 300 characters, control characters rejected. Searches title, instructor, description, and category. |
| `category` | string | none | Must be one of the 13 categories, otherwise `422`. |
| `sort` | enum | `latest` | `latest`, `rating`, or `title`. |
| `hide_expired` | boolean | `false` | Excludes courses flagged as expired. |
| `kind` | enum | none | `courses`, `practice`, or `saved`. |

The API uses camelCase field aliases (for example `totalHour`, `isExpired`, `imageUrl`) while the database uses snake_case.

### Bookmarks

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/saved` | Courses bookmarked by the current visitor. |
| `POST` | `/api/saved/{course_id}/toggle` | Adds or removes a bookmark; returns `{ "saved": bool, "course_id": int }`. |

### Administration

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/catalog/refresh` | Refresh the first page, or the full catalog with `?full=true`. |
| `POST` | `/api/catalog/refreshCourses` | Deprecated alias of the refresh endpoint. |

Status codes: `409` when a sync is already running, `429` when the refresh cooldown is active, `502` when the upstream is unreachable or returns an unexpected payload.

## Bookmarks

Bookmarks require no account. Each visitor gets an anonymous, signed-format `course_visitor` cookie (`HttpOnly`, `SameSite=Lax`, one-year lifetime). The bookmark table enforces a unique `(visitor_id, course_id)` pair, and cross-site `POST` requests are rejected.

Clearing cookies removes access to that bookmark list. There is no cross-device sync yet.

To exercise bookmarks with curl, persist the cookie jar:

```bash
curl -c cookies.txt -b cookies.txt -X POST http://127.0.0.1:8000/api/saved/123/toggle
curl -c cookies.txt -b cookies.txt http://127.0.0.1:8000/api/saved
```

## Testing

```bash
pytest -q
```

The suite uses a temporary SQLite database and `httpx.MockTransport`, so it never contacts the live upstream. It covers:

- refresh without a token, repeated refresh, cooldown, and full-catalog paging
- sync locking and interrupted pagination
- local filtering, sorting, pagination, and category validation
- coupon extraction and enrollment URL validation
- detail flattening and HTML sanitization
- cover resize and placeholder fallback
- bookmark isolation between visitors and duplicate-toggle behavior
- HTMX partial responses and API documentation availability

Tests validate the application's own contracts, not the live upstream format. Run a real sync against the configured upstream before relying on a new deployment.

## Docker

The repository ships a multi-stage `Dockerfile`:

1. **CSS stage** — installs nothing; downloads the standalone Tailwind CLI and builds `style.css`.
2. **Runtime stage** — installs `requirements.txt`, copies the project, creates an unprivileged `course` user, runs `alembic upgrade head`, and starts Gunicorn with a Uvicorn worker on `${PORT:-8000}`.

Build and run the image directly (SQLite inside the container):

```bash
docker build -t coursemy .
docker run --rm -p 8000:8000 \
  -e SCHEDULER_ENABLED=true \
  -v "$PWD/app/static/blobs:/app/app/static/blobs" \
  coursemy
```

With PostgreSQL, use Compose. Add a strong `POSTGRES_PASSWORD` to `.env` first:

```bash
docker compose up --build -d
docker compose logs -f app
```

Compose starts PostgreSQL 17 plus a single Gunicorn worker, persists the database and covers in named volumes, waits for a healthy database, and exposes a health check against `/api/info`.

> Do not run `docker compose down -v` unless you intend to delete the database and cover volumes.

## Production deployment

Without Docker, on a VPS:

```bash
alembic upgrade head
gunicorn app.main:app \
  -k uvicorn_worker.UvicornWorker \
  --workers 1 --bind 127.0.0.1:8000 --timeout 180
```

Behind a reverse proxy, forward `X-Forwarded-*` headers and set `COOKIE_SECURE=true` when HTTPS is terminated upstream.

Guidance for scaled deployments:

- **Multiple workers or instances** — use PostgreSQL, set `SCHEDULER_ENABLED=false` everywhere, and trigger `POST /api/catalog/refresh?full=true` from one external cron job.
- **Shared storage** — all instances must share `BLOB_DIR` (network volume or object storage integration) or horizontal scaling will produce broken covers.
- **Migrations** — run `alembic upgrade head` once before new workers start.
- **Timeouts** — a full sync can exceed default proxy timeouts; either raise them or rely on the scheduler.
- **Platforms** — on Railway or Render, bind to `0.0.0.0:$PORT` and attach a persistent volume for `BLOB_DIR`.

## Storage and backups

| Data | Where | Persist? |
| --- | --- | --- |
| Courses, bookmarks, sync metadata | `DATABASE_URL` (SQLite file or PostgreSQL) | Yes |
| Course covers | `BLOB_DIR` (`app/static/blobs`) | Yes |
| Built CSS | `app/static/css/style.css` | Rebuilt from source |
| `.env` | Repository root | Secret, never commit |

A complete backup needs both the database and the cover directory. Without the covers, the app still works and serves placeholders, but each cover must be re-downloaded after the next sync.

## Security notes

- `.env` is ignored by Git. Never commit real credentials.
- The refresh endpoint is intentionally unauthenticated, as specified by the project brief. Protect it at the proxy layer if your deployment requires it.
- State-changing requests are rejected when `Sec-Fetch-Site: cross-site` or the `Origin` header does not match the host.
- Security headers are applied to every response: `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options`.
- Cover downloads are restricted to known Udemy CDN hosts over HTTPS, with size and pixel limits to guard against decompression bombs.
- Enrollment URLs are validated before a coupon code is extracted; non-Udemy or malformed URLs are discarded.
- Bookmark and stats responses are marked `Cache-Control: private, no-store` with `Vary: Cookie`.

This project does not claim that a coupon is still valid at checkout. Coupon availability is controlled by the upstream feed and Udemy.

## Troubleshooting

**`RuntimeError: Database migrations have not been applied`**
Run `alembic upgrade head` before starting the app.

**The page has no Tailwind styling**
Run `python scripts/build_css.py` (or provide `TAILWIND_BIN`). The committed `style.css` is only a bootstrap fallback.

**`The course source is unavailable`**
The upstream request failed after retries. The cached catalog remains available; retry `POST /api/catalog/refresh`.

**`409 A catalog sync is already running`**
Another sync holds the database lease. Wait for it, or wait up to 10 minutes for an abandoned lease to expire.

**`429 Please wait N seconds ...`**
`REFRESH_COOLDOWN_SECONDS` is active. Wait for `Retry-After`, or set the value to `0` while developing.

**Bookmarks disappear**
The `course_visitor` cookie was cleared or `COOKIE_SECURE=true` is set while serving over plain HTTP.

**Covers are missing after a deploy**
`BLOB_DIR` was not persisted or not shared between instances.

## Documentation

- [`docs/TECH_STACK_REVIEW.md`](docs/TECH_STACK_REVIEW.md) — stack decisions and trade-offs.
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — verification log and known gaps.
- [`DESIGN.md`](DESIGN.md) — visual direction and design rationale.

## License

Released under the [MIT License](LICENSE).

Copyright © 2026 Ragraze.
