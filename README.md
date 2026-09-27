# notes-service

A Python based microservice to perform CRUD operations for notes data.

Built with **FastAPI**, **Uvicorn**, **Motor** (async MongoDB), and **Pydantic v2**.

## Features

- REST CRUD for notes (`userId`, `title`, `body`, `tags`, timestamps)
- Required `userId` ownership on every note; all reads/writes are scoped to that user
- Optional tag filter on list endpoint (`?userId=&tag=`)
- Health checks: `GET /health` and `GET /health/live` (liveness), `GET /health/ready` (Mongo readiness)
- Starts serving HTTP even if MongoDB is down; background reconnect with exponential backoff
- `/notes*` returns `503` with `reason: database` while Mongo is unavailable
- Env-based MongoDB configuration (`MONGODB_URI`, optional `DB_NAME`)
- CORS enabled for local development
- Heroku-ready `Procfile`

Ownership is enforced via a required `userId` field (create body) and query param (list/get/update/delete). JWT/auth middleware is not included yet — the caller (future notes app / gateway) passes the authenticated user's id.

## Prerequisites

- Python 3.12+
- A MongoDB Atlas (or local) connection string

## Setup

```bash
cd notes-service

# Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -r requirements.txt

# Configure environment (do not commit .env)
cp .env.example .env
# Edit .env and set MONGODB_URI / DB_NAME
```

### Environment variables

| Variable       | Required | Default         | Description                          |
|----------------|----------|-----------------|--------------------------------------|
| `MONGODB_URI`  | yes      | —               | MongoDB connection URI              |
| `DB_NAME`      | no       | `notes-service` | Database name                        |
| `PORT`         | no       | `8000`          | HTTP port (Heroku sets this)         |

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open API docs at http://localhost:8000/docs

## API

| Method | Path            | Description                                              |
|--------|-----------------|----------------------------------------------------------|
| GET    | `/health`       | Liveness check (always 200 if process is up)             |
| GET    | `/health/live`  | Same as `/health`                                        |
| GET    | `/health/ready` | Readiness: 200 when Mongo connected, else 503            |
| GET    | `/notes`        | List notes (`?userId=` required, `?tag=` optional)       |
| GET    | `/notes/{id}`   | Get one note (`?userId=` required)                       |
| POST   | `/notes`        | Create a note (`userId` in JSON body)                    |
| PUT    | `/notes/{id}`   | Replace a note (`?userId=` required; ownership immutable)|
| PATCH  | `/notes/{id}`   | Partially update a note (`?userId=` required)            |
| DELETE | `/notes/{id}`   | Delete a note (`?userId=` required)                      |

Liveness does not depend on MongoDB. Readiness and all `/notes*` routes require a live connection; when the DB is down they return `503` with `reason: database` (and a `database` state string on readiness). The process keeps running and retries Mongo in the background.

### Example create body

```json
{
  "userId": "user-123",
  "title": "Shopping list",
  "body": "milk, eggs",
  "tags": ["errands"]
}
```

Responses include `userId` and string `id` (MongoDB ObjectId). Notes that are missing or belong to another user return `404` with `"Note not found"` (no cross-user existence leak). Invalid ids / payloads return `422`.

## Heroku

```bash
# Ensure MONGODB_URI and DB_NAME are set as config vars
git push heroku master
```

The `Procfile` starts:

```
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Project layout

```
app/
  main.py           # FastAPI app + lifespan
  config.py         # Settings from env
  db.py             # Motor client, reconnect, readiness helpers
  models/note.py    # NoteCreate, NoteUpdate, NoteOut
  routers/
    health.py
    notes.py
requirements.txt
.env.example
Procfile
```
