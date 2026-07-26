"""FastAPI application factory.

Wires config, structured logging, request-id middleware, CORS, the lifespan
singletons, and the v1 routers. `app = create_app()` is the ASGI entrypoint
(uvicorn anime_api.main:app).
"""

from __future__ import annotations

from anime_core.observability import setup_otel
from anime_core.observability.otel import instrument_fastapi
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from anime_api.config import get_settings
from anime_api.lifespan import lifespan
from anime_api.logging import configure_logging
from anime_api.middleware import MetricsMiddleware, RequestIDMiddleware, ServerTimingMiddleware
from anime_api.routes import account, feedback, health, history, recommend


def create_app() -> FastAPI:
    # Load .env into os.environ BEFORE the lifespan builds singletons that read
    # raw env (OpenAIEmbedder/Groq/DB). uvicorn doesn't load .env on its own, so
    # without this the app boots with an empty environment and fails on startup.
    load_dotenv()

    settings = get_settings()
    configure_logging(settings.log_level)
    # OTel SDK + auto-instrumentations (SQLAlchemy/Redis/httpx)
    # registered BEFORE FastAPI() so the global TracerProvider is in place when
    # the FastAPI instrumentation attaches below.
    setup_otel()

    app = FastAPI(
        title="Anime Recommender API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # FastAPI auto-instrumentation — needs the app instance, so it lives here.
    # Idempotent at the instrumentation layer.
    instrument_fastapi(app)

    # CORS added first so RequestIDMiddleware (added last) is the OUTERMOST layer —
    # the request id is bound before anything else runs. ServerTimingMiddleware sits
    # between them: it doesn't depend on request_id, but it does emit response
    # headers that must be set before the response-start message (so it must run
    # OUTSIDE the route handler but INSIDE RequestIDMiddleware).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ServerTimingMiddleware)
    # Inside RequestIDMiddleware so a metric is only recorded for a request that
    # also produced a correlated log line — a count you can't trace back to a log
    # is a count you can't investigate.
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health.router)
    app.include_router(recommend.router, prefix="/v1")
    app.include_router(feedback.router, prefix="/v1")
    app.include_router(history.router, prefix="/v1")
    app.include_router(account.router, prefix="/v1")

    return app


app = create_app()
