# gpt-db

Experimental API to enhance ChatGPT's logging abilities. Built with FastAPI and designed for Vercel.

## Endpoints

- `/`: Health check (no auth). Returns `{ "status": "ok" }` when the API is up.
- `/list`: Lists MongoDB collections across accessible databases. Requires `x-api-key` header.

## Setup & Local Run

1) Install dependencies and configure env:

```bash
pip install -r requirements.txt
cp .env.example .env
```

2) Set required variables in `.env`:

- `API_KEY`: any string you choose; used for `/list` auth.
- `MONGO_URI`: Atlas connection string (recommended). Example:
  `mongodb+srv://<user>:<pass>@<cluster>/?retryWrites=true&w=majority`

3) Start the server (defaults to port `8000`):

```bash
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
# or
python main.py
```

## Usage Examples (curl)

- API health:

```bash
curl -sS http://localhost:${PORT:-8000}/
# -> {"status":"ok"}
```

- List MongoDB collections (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/list
# -> {"databases":[{"name":"mydb","collections":["logs","events", ...]}, ...]}
```

If MongoDB is unreachable or misconfigured, `/list` responds with `503` and a JSON error:

```json
{
  "error": true,
  "type": "DatabaseAuthenticationError",
  "message": "Unable to connect to MongoDB: authentication failed. Please check your username, password, or connection string.",
  "code": 8000,
  "service": "MongoDB Atlas"
}
```

## Troubleshooting Mongo Auth

- Wrong password/URI: Ensure `MONGO_URI` has the correct username and password. If building from separate vars, verify `MONGO_PASS` is used (not a duplicated username).
- Special characters: If your password has `@`, `:`, `/`, `#`, or spaces, it must be URL-encoded. When using `MONGO_USER/MONGO_PASS/MONGO_HOST`, the app will URL-encode the password for you.
- Prefer full Atlas URI: You can paste the Atlas-provided SRV string directly into `MONGO_URI`.
- Quick connectivity test: Use the included script to verify outside FastAPI.

```bash
python tests/ping-mongo.py
# Expected: "Pinged your deployment. You successfully connected to MongoDB!"
```

## Project Structure

- `main.py`: Thin entrypoint that imports `app.app` for Vercel/uvicorn.
- `app/`: Application package
  - `app/main.py`: Creates the FastAPI application and mounts routes
  - `app/api/routes.py`: Route definitions (`/`, `/list`)
  - `app/api/deps.py`: Shared dependencies (e.g., API key auth)
  - `app/db/mongo.py`: MongoDB client and helpers
  - `app/core/env.py`: Environment variable helpers and dotenv loading
    - Builds `MONGO_URI` from `MONGO_USER/MONGO_PASS/MONGO_HOST` if `MONGO_URI` is not set

## Deployment (Vercel)

Configured for Vercel’s Python runtime via `vercel.json`:

- Builds `main.py` with `@vercel/python` and entrypoint `main:app` (which imports `app.app`).
- Routes all paths to `main.py`.

Set environment variables in Vercel Project Settings:

- `API_KEY`
- `MONGO_URI` (Atlas connection string)

After deploy, verify:

```bash
# Health (no auth)
curl -sS https://<project>.vercel.app/
# -> {"status":"ok"}

# Collections (with auth)
curl -sS -H "x-api-key: ${API_KEY}" https://<project>.vercel.app/list
```

If you get `404: NOT_FOUND` on `/`, ensure you redeployed with the included `vercel.json` routing.
