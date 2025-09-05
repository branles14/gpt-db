# gpt-db

Minimal FastAPI app exposing a single `/health` endpoint.

## Usage

Set `PORT` to change the listening port (defaults to `8000`), then launch the server:

```bash
# optional: export PORT=9000
uvicorn main:app --port "${PORT:-8000}"
```

Check the health endpoint:

```bash
curl http://localhost:${PORT:-8000}/health
```

The endpoint responds with:

```json
{"status": "ok"}
```
