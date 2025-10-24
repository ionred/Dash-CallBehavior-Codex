"""Application entry points for ASGI and WSGI servers."""
from __future__ import annotations

from app import app, server

__all__ = ["app", "server"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", factory=False, host="0.0.0.0", port=8050, reload=True)

