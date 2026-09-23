from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.security import require_api_key
from .db.database import init_db
from .api import routes_sessions, routes_users, routes_hardware, routes_analytics, routes_settings, routes_contrib, ws_live

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every REST router requires the API key when LIFTGUARD_API_KEY is set
# (no-op in open development mode). The WebSocket router checks the same
# key itself via ?token=, since browsers cannot set headers on WS
# handshakes.
_auth = [Depends(require_api_key)]

app.include_router(routes_sessions.router, dependencies=_auth)
app.include_router(routes_users.router, dependencies=_auth)
app.include_router(routes_hardware.router, dependencies=_auth)
app.include_router(routes_analytics.router, dependencies=_auth)
app.include_router(routes_settings.router, dependencies=_auth)
app.include_router(routes_contrib.router, dependencies=_auth)
app.include_router(ws_live.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}
