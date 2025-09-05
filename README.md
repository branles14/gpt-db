# gpt-db

Minimal FastAPI app exposing a single `/health` endpoint.

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
uvicorn main:app --port "${PORT:-8000}"
# or
python main.py
```

Check the health endpoint:

```bash
curl http://localhost:${PORT:-8000}/health
```

The endpoint responds with:

```json
{"status": "ok"}
```

## Deployment

The included `vercel.json` configures Vercel to build `main.py` with `@vercel/python` and serve the FastAPI app via the `main:app` entry point.

Deploy with the [Vercel CLI](https://vercel.com/docs/cli) and then verify the health endpoint:

```bash
# after `vercel deploy`
curl https://<your-project>.vercel.app/health
```
