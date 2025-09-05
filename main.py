import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends, status

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)

# Read API_KEY; if missing, don't crash in serverless envs.
API_KEY = os.getenv("API_KEY") or None

#
# Ensure PORT is an int for uvicorn
PORT = int(os.getenv("PORT", "8000"))

# 
app = FastAPI(title="gpt-db")

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server not configured: set API_KEY")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@app.get("/")
async def root():
    return {
        "name": "gpt-db",
        "status": "ready",
        "health": "/health",
        "docs": "/docs"
    }

@app.get("/health")
async def health(_: None = Depends(require_api_key)):
    return {"status": "ok"}

# Convenience alias in case users expect an /api path
@app.get("/api/health")
async def api_health(_: None = Depends(require_api_key)):
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
