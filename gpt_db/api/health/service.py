from gpt_db.db.mongo import get_mongo_client


async def mongo_status() -> dict[str, str]:
    """Check MongoDB connectivity.

    Returns a dict with ``status`` set to ``"ok"`` or ``"error"``.
    On error, a ``detail`` field describes the exception.
    """
    try:
        client = get_mongo_client()
        await client.admin.command("ping")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
