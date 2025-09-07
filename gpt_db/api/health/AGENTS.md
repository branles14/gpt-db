# Health endpoint

An endpoint for programmatically checking the health of the API and its components.

## Notes

### Healthy response

```JSON
{
    "status": "ok",
    "components": {
        "mongo": "ok",
        "futureComponent": "ok"
    }
}
```

### Unhealthy response

```JSON
{
    "status": "error",
    "components": {
        "mongo": {
            "status": "error",
            "detail": "Event loop is closed"
        },
        "futureComponent": "ok"
    }
}
```
