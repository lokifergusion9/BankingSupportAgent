def main() -> None:
    """Start the SecureBank support API on http://localhost:8000"""
    import uvicorn

    uvicorn.run("bankingsupportagent.api:app", host="127.0.0.1", port=8000)
