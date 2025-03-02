import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from src.config import get_settings
    from src.storage.database import init_db

    settings = get_settings()
    init_db(settings.database_url)
    logger.info("Database initialized")
    yield
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Finparse AI",
        description="AI-powered financial document parser",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes import batch, documents, health, parse

    app.include_router(health.router)
    app.include_router(parse.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(batch.router, prefix="/api/v1")

    return app


app = create_app()
