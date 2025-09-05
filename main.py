import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends, status

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)

# Require API_KEY to be set for the server to run
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    import sys
    print("ERROR: API_KEY is not set in environment or .env", file=sys.stderr)
    raise SystemExit(1)

#
# Ensure PORT is an int for uvicorn
PORT = int(os.getenv("PORT", "8000"))

# 
app = FastAPI(title="gpt-db")

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@app.get("/health")
async def health(_: None = Depends(require_api_key)):
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
