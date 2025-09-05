# gpt-db

Minimal FastAPI app with a `/health` endpoint secured by an API key. Designed to deploy on Vercel.

## Usage

Install dependencies and configure the environment. Configuration is read from environment variables or an optional `.env` file. At a minimum, define an `API_KEY`:

```bash
pip install -r requirements.txt
cp .env.example .env
echo "API_KEY=your_api_key" >> .env
# optional: echo "PORT=9000" >> .env
```

Run the server locally (defaults to port `8000`):

```bash
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
# or
python main.py
```

Check the health endpoint (requires `x-api-key` header matching `API_KEY`):

```bash
curl -sS -H "x-api-key: your_api_key" http://localhost:${PORT:-8000}/health
# -> {"status":"ok"}
```

If the header is missing or incorrect, it responds with `401`:

```bash
curl -sS http://localhost:${PORT:-8000}/health
# -> {"detail":"Invalid API key"}
```

There is also a simple root endpoint to confirm the app is reachable:

```bash
curl -sS http://localhost:${PORT:-8000}/
# -> {"name":"gpt-db","status":"ready",...}
```

## Deployment (Vercel)

This repo is configured for Vercel’s Python runtime.

- `vercel.json` builds `main.py` with `@vercel/python` and routes all paths to it, using the ASGI entrypoint `main:app`.
- Set `API_KEY` in your Vercel Project Settings → Environment Variables.

Deploy with the [Vercel CLI](https://vercel.com/docs/cli) or Git integration. After deploy, verify:

```bash
# Health check (replace <project> with your domain)
curl -sS -H "x-api-key: your_api_key" https://<project>.vercel.app/health
# -> {"status":"ok"}

# Root endpoint (no auth)
curl -sS https://<project>.vercel.app/
# -> {"name":"gpt-db","status":"ready",...}
```

### Common 404 on root

If you previously saw `404: NOT_FOUND` at `/`, it usually means the root path wasn’t routed to your app. This repo’s `vercel.json` includes a route to send all paths to `main.py`:

```json
{
  "builds": [
    { "src": "main.py", "use": "@vercel/python", "config": { "entrypoint": "main:app" } }
  ],
  "routes": [
    { "src": "/(.*)", "dest": "main.py" }
  ]
}
```

Make sure you’ve redeployed after adding routes and that `API_KEY` is set in Vercel.
