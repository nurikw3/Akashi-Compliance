from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audits, cases, health, providers
from app.core.auth import require_auth
from app.core.config import settings
from app.models import db
from app.services.enrichment.providers.adata import AdataProvider
from app.services.enrichment.providers.kompra import KompraProvider
from app.services.enrichment.registry import registry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    registry.register(AdataProvider())
    registry.register(KompraProvider())
    yield


app = FastAPI(
    title="Akashi Compliance",
    lifespan=lifespan,
    dependencies=[Depends(require_auth)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(cases.router)
app.include_router(providers.router)
app.include_router(audits.router)
