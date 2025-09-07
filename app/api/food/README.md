# Food Endpoints

- `/food/catalog`:
  - `GET` – list products with optional filters (`q`, `upc`, `tag`).
  - `POST` – create or update a product by `upc`.
  - `GET /food/catalog/{product_id}` – retrieve a product.
  - `DELETE /food/catalog/{product_id}` – delete a product (`force=true` to bypass reference checks).
- `/food/stock`:
  - `GET` – list stock with `view=aggregate|items`.
  - `POST` – add units via `{ upc|product_id, quantity }`.
  - `POST /food/stock/consume` – atomic decrement and log.
  - `POST /food/stock/remove` – decrement with a `reason` (no nutrition log).
  - `DELETE /food/stock/{stock_id}` – delete a specific stock document.
- `/food/log`:
  - `GET` – list log entries for a day (`date=YYYY-MM-DD`) with totals and remaining targets.
  - `POST` – append a log entry manually.
  - `DELETE /food/log/{log_id}` – soft delete a log entry.
  - `POST /food/log/undo` – delete the most recent entry.
