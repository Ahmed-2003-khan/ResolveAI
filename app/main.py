from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from admin_ui.router import router as admin_router
from app.api.v1.router import api_router
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ResolveAI",
        description="Multi-channel AI customer-operations platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(admin_router)

    # Top-level WebSocket path used by widget.js: /ws/chat/{session_id}
    @app.websocket("/ws/chat/{session_id}")
    async def ws_chat(websocket: WebSocket, session_id: str) -> None:
        from app.api.v1.inbound import websocket_chat

        await websocket_chat(websocket, session_id)

    # Serve static assets (widget.js, etc.)
    try:
        from fastapi.staticfiles import StaticFiles

        app.mount("/static", StaticFiles(directory="admin_ui/static"), name="static")
    except RuntimeError:
        pass  # directory missing in test environments

    return app


app = create_app()
