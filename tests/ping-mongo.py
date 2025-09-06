import os
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Load environment from .env
load_dotenv()

# Require MONGO_URI to be set
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    import sys
    print("ERROR: MONGO_URI is not set in environment or .env", file=sys.stderr)
    raise SystemExit(1)

# Create a new client and connect to the server
client = MongoClient(MONGO_URI, server_api=ServerApi("1"))

try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print("MongoDB connection failed:", e)
    raise
