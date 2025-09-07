# Food Endpoints

- `/food/catalog`:
  - `GET` – list products with optional filters (`q`, `upc`, `tag`).
  - `POST` – create or update a product by `upc`.
  - `GET /food/catalog/{product_id}` – retrieve a product.
  - `DELETE /food/catalog/{product_id}` – delete a product (`force=true` to bypass reference checks).
- `/food/stock`:
  - `GET` – returns all documents in the `food.stock` collection.
  - `POST` – inserts one or more JSON objects into `food.stock`.
