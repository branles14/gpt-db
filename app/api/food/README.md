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
