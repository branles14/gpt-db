#!/usr/bin/env python3
"""CLI utilities to exercise the API endpoints.

This script replaces the previous `test-api.sh` shell script and uses
`click` for a structured command line interface. It supports the various
API endpoints exposed by the service and is primarily meant for manual
verification during development.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib import parse, request

import click


def _parse_json(_ctx: click.Context, _param: click.Parameter, value: str | None) -> Any:
    """Parse a JSON argument.

    Supports passing a raw JSON string or `@path/to/file.json`.
    """
    if value is None:
        return None
    value = value.strip()
    if value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)


class APIClient:
    """Lightweight HTTP client for the API."""

    def __init__(self, base_url: str, api_key: Optional[str]) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(self, method: str, path: str, params: Optional[dict[str, Any]] = None, json_data: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + parse.urlencode(params)
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        data: Optional[bytes] = None
        if json_data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_data).encode()
        req = request.Request(url, data=data, headers=headers, method=method)
        with request.urlopen(req) as resp:
            text = resp.read().decode()
        try:
            payload = json.loads(text)
        except ValueError:
            payload = text
        click.echo(json.dumps(payload, indent=2))
        return payload


@click.group()
@click.option(
    "--api-url",
    envvar="API_URL",
    default="http://localhost:8000",
    show_default=True,
    help="Base URL of the running API.",
)
@click.option("--api-key", envvar="API_KEY", default=None, help="API key for authenticated routes.")
@click.pass_context
def cli(ctx: click.Context, api_url: str, api_key: Optional[str]) -> None:
    """Simulate interactions with the API."""
    ctx.obj = APIClient(api_url, api_key)


@cli.command()
@click.pass_obj
def root(client: APIClient) -> None:
    """Call the root endpoint (requires API key)."""
    client.request("GET", "/")


@cli.command()
@click.pass_obj
def health(client: APIClient) -> None:
    """Check service health (requires API key)."""
    client.request("GET", "/api/health")


# --- Food -----------------------------------------------------------------
@cli.group()
def food() -> None:
    """Food-related commands."""


# Catalog commands
@food.group()
def catalog() -> None:
    """Product catalog commands."""


@catalog.command("list")
@click.option("--q", default=None, help="Name search query.")
@click.option("--upc", default=None, help="Filter by UPC.")
@click.option("--tag", default=None, help="Filter by tag.")
@click.pass_obj
def catalog_list(client: APIClient, q: Optional[str], upc: Optional[str], tag: Optional[str]) -> None:
    params = {k: v for k, v in {"q": q, "upc": upc, "tag": tag}.items() if v}
    client.request("GET", "/food/catalog", params=params)


@catalog.command("upsert")
@click.argument("payload", callback=_parse_json)
@click.pass_obj
def catalog_upsert(client: APIClient, payload: Any) -> None:
    """Create or update a product with a JSON payload."""
    client.request("POST", "/food/catalog", json_data=payload)


@catalog.command("get")
@click.argument("product_id")
@click.pass_obj
def catalog_get(client: APIClient, product_id: str) -> None:
    """Retrieve a product by its ID."""
    client.request("GET", f"/food/catalog/{product_id}")


@catalog.command("delete")
@click.argument("product_id")
@click.option("--force", is_flag=True, help="Force deletion even if referenced.")
@click.pass_obj
def catalog_delete(client: APIClient, product_id: str, force: bool) -> None:
    params = {"force": "true"} if force else None
    client.request("DELETE", f"/food/catalog/{product_id}", params=params)


# Stock commands
@food.group()
def stock() -> None:
    """Stock management commands."""


@stock.command("get")
@click.option("--view", type=click.Choice(["aggregate", "items"]), default="aggregate", show_default=True)
@click.pass_obj
def stock_get(client: APIClient, view: str) -> None:
    client.request("GET", "/food/stock", params={"view": view})


@stock.command("add")
@click.argument("payload", callback=_parse_json)
@click.pass_obj
def stock_add(client: APIClient, payload: Any) -> None:
    """Add stock units from a JSON object: {"items": [...]}"""
    client.request("POST", "/food/stock", json_data=payload)


@stock.command("consume")
@click.argument("payload", callback=_parse_json)
@click.pass_obj
def stock_consume(client: APIClient, payload: Any) -> None:
    """Consume stock and log nutrition."""
    client.request("POST", "/food/stock/consume", json_data=payload)


@stock.command("remove")
@click.argument("payload", callback=_parse_json)
@click.pass_obj
def stock_remove(client: APIClient, payload: Any) -> None:
    """Remove stock with a reason (no nutrition log)."""
    client.request("POST", "/food/stock/remove", json_data=payload)


@stock.command("delete")
@click.argument("stock_uuid")
@click.pass_obj
def stock_delete(client: APIClient, stock_uuid: str) -> None:
    """Delete a stock row by its UUID."""
    client.request("DELETE", f"/food/stock/{stock_uuid}")


# Log commands
@food.group()
def log() -> None:
    """Nutrition log commands."""


@log.command("get")
@click.option("--date", default=None, help="Date in YYYY-MM-DD format.")
@click.pass_obj
def log_get(client: APIClient, date: Optional[str]) -> None:
    params = {"date": date} if date else None
    client.request("GET", "/food/log", params=params)


@log.command("append")
@click.argument("payload", callback=_parse_json)
@click.pass_obj
def log_append(client: APIClient, payload: Any) -> None:
    """Append an entry to the food log."""
    client.request("POST", "/food/log", json_data=payload)


@log.command("delete")
@click.argument("log_id")
@click.pass_obj
def log_delete(client: APIClient, log_id: str) -> None:
    """Soft delete a log entry."""
    client.request("DELETE", f"/food/log/{log_id}")


@log.command("undo")
@click.pass_obj
def log_undo(client: APIClient) -> None:
    """Undo the most recent log entry."""
    client.request("POST", "/food/log/undo")


if __name__ == "__main__":
    cli()
