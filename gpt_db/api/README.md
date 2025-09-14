# Food Endpoints

All routes require the `x-api-key` header.

## Catalog

### `GET /catalog`
List products with optional filters (`q`, `upc`, `tag`). The `q` parameter performs a
case-insensitive search across `name`, `upc`, `tags`, and `ingredients`. `tag`
matches against the `tags` array case-insensitively, and `upc` matches exactly.

```bash
curl -sS -H "x-api-key: ${API_KEY}" \
  "https://<host>/catalog?q=apple"
```

```json
{
  "items": [
    { "_id": "64abc...", "name": "Apple", "upc": "0001", "tags": ["fruit"] }
  ]
}
```

### `POST /catalog`
Create or update a product by `upc`.

Provide per-unit nutrition facts in a nested `nutrition` object. Supported fields include macros (e.g., `calories`, `protein`, `fat`, `carbs`, `fiber`, `sugars`), vitamins (e.g., `vitamin_c_mg`, `vitamin_d_mcg`), and minerals (e.g., `sodium_mg`, `potassium_mg`, `calcium_mg`). Optionally include `tags: string[]` and `ingredients: string[]`. For backward compatibility, top-level macro fields may be provided and will be merged into `nutrition`.

Important: UPC must be a JSON string of digits. Leading zeros are significant and must be preserved. Example: `"070662404072"` (not an unquoted number).

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc":"0001","name":"Apple","tags":["fruit"],"ingredients":["apple"],"nutrition":{"calories":95,"protein":0.5,"fat":0.3,"carbs":25,"fiber":4.4}}' \
  https://<host>/catalog
```

```json
{
  "success": true,
  "message": "Product created",
  "item": {
    "_id": "64abc...",
    "upc": "0001",
    "name": "Apple",
    "tags": ["fruit"],
    "ingredients": ["apple"],
    "nutrition": { "calories": 95, "protein": 0.5, "fat": 0.3, "carbs": 25, "fiber": 4.4 }
  }
}
```

Semantics and workflow:
- Upsert by `upc` uses `$set`, so subsequent calls with the same `upc` enrich the same document (e.g., first `upc+name`, later `upc+nutrition` → the product has both name and nutrition).
- When `nutrition` is sent via this endpoint it replaces the entire nutrition object; use `POST /stock` to merge individual nutrition keys and union `tags`/`ingredients`.
- Duplicate UPCs: the database enforces a unique sparse index on `upc`. A true duplicate insert (or a rare race) can return `409 Conflict`. Normal upsert-by-UPC updates return `200 OK`.

### `GET /catalog/{product_id}`
Retrieve a product.

```bash
curl -sS -H "x-api-key: ${API_KEY}" \
  https://<host>/catalog/64abcdeffedcba0123456789
```

```json
{ "_id": "64abcdeffedcba0123456789", "upc": "0001", "name": "Apple" }
```

### `DELETE /catalog/{product_id}`
Delete a product. Use `?force=true` to bypass reference checks.

```bash
curl -sS -X DELETE -H "x-api-key: ${API_KEY}" \
  "https://<host>/catalog/64abcdeffedcba0123456789?force=true"
```

```json
{ "deleted": true }
```

## Stock

### `GET /stock`
List stock items. Use `view=aggregate` (default) or `view=items` for raw rows.

```bash
curl -sS -H "x-api-key: ${API_KEY}" \
  "https://<host>/stock?view=aggregate"
```

```json
{
  "items": [ { "product_id": "64abc...", "quantity": 5 } ]
}
```

### `POST /stock`
Add units for one or more products. When adding by `upc`, you can include
optional fields to seed or update the catalog entry: `name`, `tags`,
`ingredients`, and `nutrition` (or top-level macros like `calories`,
`protein`, `fat`, `carbs`).

UPC requirements: the `upc` field must be a quoted string containing digits only
to avoid losing leading zeros and to keep catalog and stock in sync.

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"items":[{"upc":"0001","quantity":3}]}' \
  https://<host>/stock
```

```json
{ "success": true, "message": "Stock updated", "upserted_uuids": ["550e8400-e29b-41d4-a716-446655440000"], "count": 1 }
```

### `POST /stock/consume`
Atomically decrement stock and log nutrition (UPC-only).

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc":"0001","units":1}' \
  https://<host>/stock/consume
```

```json
{ "success": true, "message": "Stock consumed", "remaining": 2 }
```

### `POST /stock/remove`
Decrement without logging (UPC-only; requires `reason`).

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc":"0001","units":1,"reason":"spoilage"}' \
  https://<host>/stock/remove
```

```json
{ "success": true, "message": "Stock removed", "remaining": 1 }
```

### `DELETE /stock/{stock_uuid}`
Remove a specific stock document.

```bash
curl -sS -X DELETE -H "x-api-key: ${API_KEY}" \
  https://<host>/stock/550e8400-e29b-41d4-a716-446655440000
```

```json
{ "success": true, "message": "Product deleted", "deleted": true }
```

## Log

### `GET /log`
List log entries for a day (`date=YYYY-MM-DD`) with totals and remaining targets.

```bash
curl -sS -H "x-api-key: ${API_KEY}" \
  "https://<host>/log?date=2024-01-01"
```

```json
{
  "entries": [
    { "_id": "64log...", "upc": "0001", "units": 1, "timestamp": "2024-01-01T12:00:00" }
  ],
  "totals": { "calories": 95, "protein": 0, "fat": 0, "carbs": 25 },
  "remaining": { "calories": 1905, "protein": 150, "fat": 70, "carbs": 225 }
}
```

### `POST /log`
Append a log entry manually.

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"upc":"0001","units":1}' \
  https://<host>/log
```

```json
{ "success": true, "message": "Log entry created", "log_id": "64log..." }
```

### `DELETE /log/{log_id}`
Soft delete a log entry.

```bash
curl -sS -X DELETE -H "x-api-key: ${API_KEY}" \
  https://<host>/log/64abcdeffedcba0123456789
```

```json
{ "success": true, "message": "Log entry deleted", "deleted": true }
```

### `POST /log/undo`
Delete the most recent entry.

```bash
curl -sS -X POST -H "x-api-key: ${API_KEY}" \
  https://<host>/log/undo
```

```json
{ "success": true, "message": "Last log entry undone", "deleted_id": "64abc..." }
```
## Targets

### `GET /targets`
Retrieve current macro targets, falling back to standard Daily Values.

```bash
curl -sS -H "x-api-key: ${API_KEY}" \
  https://<host>/targets
```

```json
{ "targets": { "calories": 2000, "protein": 50, "fat": 78, "carbs": 275 } }
```

### `PATCH /targets`
Update one or more targets.

```bash
curl -sS -X PATCH \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"protein":60}' \
  https://<host>/targets
```

```json
{ "targets": { "calories": 2000, "protein": 60, "fat": 78, "carbs": 275 } }
```

### `DELETE /targets`
Reset all targets to defaults.

```bash
curl -sS -X DELETE -H "x-api-key: ${API_KEY}" \
  https://<host>/targets
```

### `DELETE /targets/{macro}`
Reset a specific macro to its default.

```bash
curl -sS -X DELETE -H "x-api-key: ${API_KEY}" \
  https://<host>/targets/protein
```

Add and sync details into catalog:

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{"items":[{"upc":"0002","quantity":2,"name":"Banana","tags":["fruit"],"ingredients":["banana"],"nutrition":{"calories":105,"protein":1.3}}]}' \
  https://<host>/stock
```

Behavior:
- If UPC not found in catalog, a new catalog item is created with provided details.
- If UPC exists, new values are merged (lists are unioned; nutrition fields are merged).
- Stock documents store a snapshot of catalog fields but have their own `_id`.
- When UPC is unknown, the service attempts to fetch product details from OpenFoodFacts.org.
