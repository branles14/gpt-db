# gpt-db

Experimental API to enhance ChatGPT's logging abilities. Built with FastAPI and designed for Vercel.

## OpenAPI

A unified [OpenAPI 3.1 specification](openapi.yaml) consolidates all routes under a single `paths` section. Each operation has a unique `operationId` and uses the shared server URL `https://gpt-db.vercel.app`.

## Endpoints

- `/`: Returns `{ "message": "🍌" }` when the API key is valid.
- `/health`: Reports overall service status and component checks (e.g. MongoDB). Requires `x-api-key` header.
- `/list`: Lists MongoDB collections across accessible databases. Requires `x-api-key` header.
  - Unauthorized requests receive a playful randomized error message.
- `/docs`, `/openapi.json`: Interactive API docs, no API key required.
- `/redoc`: Interactive API docs. Requires `x-api-key` header.
- `/food/catalog`:
  - `GET` – list products with optional filters (`q`, `upc`, `tag`). `q` searches
    across `name`, `upc`, `tags`, and `ingredients` (case-insensitive). `upc`
    matches exactly; `tag` matches within the `tags` array case-insensitively.
  - `POST` – create or update a product by `upc`.
    - Create: if no existing item with the provided `upc` is found, requires `name`.
    - Update: if an item with the provided `upc` exists, performs a partial merge:
      only the fields you include are modified; other fields remain unchanged.
      To clear a field, send it explicitly as `null`.
    - Accepts optional `tags`, `ingredients`, and a nested `nutrition` object with
      macros, vitamins, and minerals per unit. For backward compatibility,
      top‑level macro fields (`calories`, `protein`, `fat`, `carbs`) are accepted
      and merged into `nutrition`.
    Note: UPC must be provided as a JSON string of digits (e.g., "070662404072"); numeric values will be rejected to prevent loss of leading zeros.
  - `GET /food/catalog/{product_id}` – retrieve a product.
  - `DELETE /food/catalog/{product_id}` – delete a product (`force=true` to bypass reference checks).
- `/food/stock`:
  - `GET` – list stock with `view=aggregate|items`.
- `POST` – add units via `{ upc, quantity }`. Optional fields (`name`, `tags`, `ingredients`, `nutrition`) seed or update the catalog.
  Note: `upc` must be a JSON string of digits (e.g., `"070662404072"`). Numbers or strings containing spaces/hyphens are rejected to preserve leading zeros and ensure consistent lookups.
  - `POST /food/stock/consume` – atomic decrement with log.
  - `POST /food/stock/remove` – decrement with a `reason` (no nutrition log).
  - `DELETE /food/stock/{stock_uuid}` – remove a specific stock row.
- `/food/log`:
  - `GET` – list entries for a day (`date=YYYY-MM-DD`) with totals and remaining targets.
  - `POST` – append a log entry manually.
  - `DELETE /food/log/{log_id}` – soft delete a log entry.
  - `POST /food/log/undo` – undo the most recent entry.
- `/food/targets`:
  - `GET` – current macro targets (defaults to FDA Daily Values).
  - `PATCH` – update one or more targets.
  - `DELETE` – reset all targets to defaults.
  - `DELETE /food/targets/{macro}` – reset a single macro to its default.

Full request/response examples for `/food/catalog`, `/food/stock`, `/food/log`, and `/food/targets` are available in [gpt_db/api/food/README.md](gpt_db/api/food/README.md).

## Response Conventions

Mutating endpoints in catalog, stock, and log return a consistent envelope:

- On success: `{ "success": true, "message": string, ...data }`
- On failure: `{ "success": false, "error": string, ...details }`

Read-only endpoints may omit the `success` flag and return data directly.

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

Note: The server connects using MongoDB Stable API v1 to maximize
compatibility with Atlas clusters that enable strict API mode.

3) Start the server (defaults to port `8000`):

```bash
uvicorn gpt_db.app:app --host 0.0.0.0 --port "${PORT:-8000}"
```

## Usage Examples (curl)

- Root (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/
# -> {"message":"🍌"}
```

- Service health (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/health
# -> {"status": "ok", "components": {"mongo": "ok"}}
```

- List MongoDB collections (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/list
# -> {"databases":[{"name":"mydb","collections":["logs","events", ...]}, ...]}
```

- List food catalog (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/food/catalog
# -> {"items": [...]}  # product list
```

- Upsert a product (with nested nutrition facts):

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{
        "upc": "0001",
        "name": "Apple",
        "tags": ["fruit"],
        "ingredients": ["apple"],
        "nutrition": {
          "calories": 95,
          "protein": 0.5,
          "fat": 0.3,
          "carbs": 25,
          "fiber": 4.4,
          "vitamin_c_mg": 8.4,
          "potassium_mg": 195
        }
      }' \
  http://localhost:${PORT:-8000}/food/catalog
# -> {"success": true, "message": "Product created", "item": {"_id": "...", "upc": "0001", "name": "Apple", "tags": ["fruit"], "ingredients": ["apple"], "nutrition": {"calories":95,"protein":0.5,"fat":0.3,"carbs":25,"fiber":4.4,"vitamin_c_mg":8.4,"potassium_mg":195}}}
```

- Partially update an existing product by UPC (merge update):

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{
        "upc": "0001",
        "nutrition": { "calories": 100 }
      }' \
  http://localhost:${PORT:-8000}/food/catalog
# -> {"success": true, "message": "Product updated", "item": { ... "nutrition": { ... "calories": 100, ... } }}

# Clear a field by sending null (example: remove calories):
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{
        "upc": "0001",
        "nutrition": { "calories": null }
      }' \
  http://localhost:${PORT:-8000}/food/catalog
```

- Read food stock (requires API key):

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  "http://localhost:${PORT:-8000}/food/stock?view=aggregate"
# -> {"items": [...]}  # aggregated quantities
```

- Add to food stock (requires API key):

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"items": [{"upc": "0001", "quantity": 3}]}' \
  http://localhost:${PORT:-8000}/food/stock
# -> {"success": true, "message": "Stock updated", "upserted_uuids": ["..."], "count": 1}

- Add to stock and sync catalog details:

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"items": [{
        "upc": "0002",
        "quantity": 2,
        "name": "Banana",
        "tags": ["fruit"],
        "ingredients": ["banana"],
        "nutrition": {"calories": 105, "protein": 1.3, "carbs": 27}
      }]}' \
  http://localhost:${PORT:-8000}/food/stock
```

Rules:
- If the UPC is not in catalog, a new catalog item is created with provided details.
- If the UPC exists, new values (e.g., tags, ingredients, nutrition) are merged into the catalog item.
- Stock documents copy a snapshot of catalog fields (name, tags, ingredients, nutrition) but have their own `_id`.
```

- Consume stock (with log):

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc": "0001", "units": 1}' \
  http://localhost:${PORT:-8000}/food/stock/consume
# -> {"success": true, "message": "Stock consumed", "remaining": 2}
```

- Remove stock (no log):

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc": "0001", "units": 1, "reason": "spoilage"}' \
  http://localhost:${PORT:-8000}/food/stock/remove
# -> {"success": true, "message": "Stock removed", "remaining": 1}

Notes:
- Consuming/removing stock accepts UPC only (no product_id).
```

- View food log for today:

```bash
curl -sS \
  -H "x-api-key: ${API_KEY}" \
  "http://localhost:${PORT:-8000}/food/log"
# -> {"entries": [...], "totals": {...}, "remaining": {...}}
```

- Append to the food log manually:

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc": "0001", "units": 1}' \
  http://localhost:${PORT:-8000}/food/log
# -> {"success": true, "message": "Log entry created", "log_id": "..."}
```

- Undo the most recent log entry:

```bash
curl -sS -X POST \
  -H "x-api-key: ${API_KEY}" \
  http://localhost:${PORT:-8000}/food/log/undo
# -> {"success": true, "message": "Last log entry undone", "deleted_id": "..."}
```

## Simulate API usage (CLI)

For quick manual testing without crafting curl commands, a Click-based
helper script is provided:

```bash
python tests/simulate-use.py --help
python tests/simulate-use.py root
python tests/simulate-use.py list --api-key ${API_KEY} --api-url http://localhost:${PORT:-8000}
```

## Deployment (Vercel)

- Use `@vercel/python` with the provided `vercel.json`.
- Set environment variables in your Vercel project: `API_KEY` and `MONGO_URI`.
- This service opens a fresh connection per server instance and caches the
  client; serverless cold starts will recreate a client as needed.

## Troubleshooting

- API returns `DatabaseConnectionError`, but `tests/ping-mongo.py` works locally:
  - Ensure your Atlas Network Access allows Vercel IPs or use `0.0.0.0/0` for testing.
  - Confirm `MONGO_URI` is set in Vercel Environment Variables (Production/Preview).
  - The app uses MongoDB Stable API v1 via Motor/PyMongo, matching the sample ping script.
  - If `MONGO_URI` is missing, endpoints now return HTTP 500 with
    `Server not configured: set MONGO_URI` instead of a generic 503.

- Catalog add “doesn’t stick” or a tool claims success but the item isn’t listed:
  - Verify the request actually hit `POST /food/catalog` with a `201 Created` or `200 OK` response.
  - Ensure `x-api-key` is included; read endpoints will also require it, but double‑check the write.
  - Check that UPC is a quoted string of digits. Example valid payload snippet:
    ```json
    {"upc":"070662404072","name":"Example","nutrition":{"calories":100}}
    ```
    Invalid examples: `{ "upc": 70662404072 }`, `{ "upc": "07066-2404072" }`.
  - If you post empty arrays for `tags` or `ingredients`, validation fails. Omit the fields instead.
  - To manually verify end‑to‑end, use the CLI: `python tests/simulate-use.py food catalog upsert '@payload.json'` then `python tests/simulate-use.py food catalog list`.

Commands mirror the API structure. JSON payloads may be passed directly or
from a file by prefixing the path with `@`.

```bash
python tests/simulate-use.py food catalog upsert '{"upc": "0001", "name": "Apple"}'
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

- `gpt_db/app.py`: Creates the FastAPI application and mounts routes
- `gpt_db/`: Application package
  - `gpt_db/api/routes.py`: Root route definitions and sub-router mounting
  - `gpt_db/api/food/`: Module containing food catalog and stock endpoints
  - `gpt_db/api/deps.py`: Shared dependencies (e.g., API key auth)
  - `gpt_db/api/utils.py`: Helper utilities (e.g., Mongo error formatting)
  - `gpt_db/db/mongo.py`: MongoDB client and helpers
  - `gpt_db/core/env.py`: Environment variable helpers and dotenv loading
    - Builds `MONGO_URI` from `MONGO_USER/MONGO_PASS/MONGO_HOST` if `MONGO_URI` is not set

## Deployment (Vercel)

Configured for Vercel’s Python runtime via `vercel.json`:

- Builds `gpt_db/app.py` with `@vercel/python` and entrypoint `gpt_db.app:app`.
- Routes all paths to `gpt_db/app.py`.

Set environment variables in Vercel Project Settings:

- `API_KEY`
- `MONGO_URI` (Atlas connection string)

After deploy, verify:

```bash
# Root
curl -sS -H "x-api-key: ${API_KEY}" "${API_URL}"
# -> {"message":"🍌"}

# Service health
curl -sS -H "x-api-key: ${API_KEY}" "${API_URL}/health"
# -> {"mongo":{"status":"ok"}}

# Collections
curl -sS -H "x-api-key: ${API_KEY}" "${API_URL}/list"
```

If you get `404: NOT_FOUND` on `/`, ensure you redeployed with the included `vercel.json` routing.
