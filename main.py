import os
from dotenv import load_dotenv
from fastapi import FastAPI

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)

# Require API_KEY to be set for the server to run
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    import sys
    print("ERROR: API_KEY is not set in environment or .env", file=sys.stderr)
    raise SystemExit(1)

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )
