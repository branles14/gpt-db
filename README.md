# gpt-db
Simple FastAPI app backed by MongoDB.

## Configuration

Environment variables are loaded from a `.env` file. Start by copying the
example configuration and editing the values as needed:

```bash
cp .env.example .env
```

The application expects an `API_KEY` for authentication and optional MongoDB
connection details (`MONGO_USER`, `MONGO_PASS`, `MONGO_HOST`).

