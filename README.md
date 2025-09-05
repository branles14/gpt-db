# gpt-db

Minimal FastAPI app exposing a single `/health` endpoint secured by an API key.

## Usage

Install dependencies and configure the environment. Configuration is read from environment variables or an optional `.env` file. At a minimum, define an `API_KEY`:

```bash
pip install -r requirements.txt
cp .env.example .env
echo "API_KEY=your_api_key" >> .env
# optional: echo "PORT=9000" >> .env
```

Run the server (defaults to port `8000`):

```bash
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
# or
python main.py
```

Check the health endpoint (requires `x-api-key` header matching `API_KEY`):

```bash
curl -H "x-api-key: your_api_key" http://localhost:${PORT:-8000}/health
```

The endpoint responds with:

```json
{"status": "ok"}

If the header is missing or incorrect, it responds with `401`:

```json
{"detail": "Invalid API key"}
```
```

## Deployment

The included `vercel.json` configures Vercel to build `main.py` with `@vercel/python` and serve the FastAPI app via the `main:app` entry point.

Deploy with the [Vercel CLI](https://vercel.com/docs/cli) and then verify the health endpoint:

```bash
# after `vercel deploy`
curl https://<your-project>.vercel.app/health
```
