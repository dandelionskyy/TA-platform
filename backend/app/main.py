import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.routers import auth, chat, teacher, ta, robot, courses, ws, academic, messaging, bridge_content, bridge_tutor, bridge_staff

settings = get_settings()
logger = logging.getLogger(__name__)


async def _bridge_retention_loop():
    """Expire anonymous state even during periods with no tutor traffic."""
    from app.core.database import AsyncSessionFactory
    from app.services.bridge_sessions import purge_expired_sessions

    while True:
        try:
            async with AsyncSessionFactory() as db:
                while await purge_expired_sessions(db):
                    await db.commit()
                await db.commit()
        except Exception:
            logger.exception("BRIDGE session expiry failed; will retry")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — auto-create tables in SQLite
    await init_db()
    # Create uploads dir if needed
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    if settings.SEED_DEMO_DATA:
        from app.core.database import AsyncSessionFactory
        from app.seed_demo import seed_demo_accounts
        async with AsyncSessionFactory() as db:
            await seed_demo_accounts(db)
            await db.commit()
    from app.services.bridge_ingest import start_ingestion_recovery, stop_ingestion_recovery
    await start_ingestion_recovery()
    retention_task = asyncio.create_task(_bridge_retention_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        try:
            await retention_task
        except asyncio.CancelledError:
            pass
        await stop_ingestion_recovery()
    # Shutdown
    from app.ai.conversation_memory import conversation_memory
    await conversation_memory.close()
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(teacher.router)
app.include_router(ta.router)
app.include_router(robot.router)
app.include_router(courses.router)
app.include_router(courses.teacher_router)
app.include_router(ws.router)
app.include_router(academic.router)
app.include_router(messaging.router)
app.include_router(bridge_content.router)
app.include_router(bridge_tutor.router)
app.include_router(bridge_staff.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}


# Serve frontend static files (built React app)
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
static_dir = os.path.join(frontend_dist, "assets") if os.path.exists(os.path.join(frontend_dist, "assets")) else None

if os.path.exists(frontend_dist):
    # Mount static assets
    if static_dir and os.path.exists(static_dir):
        app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    # Also mount old-style static files (images, ppt, etc.)
    public_static = os.path.join(os.path.dirname(frontend_dist), "public", "static")
    if os.path.exists(public_static):
        app.mount("/static", StaticFiles(directory=public_static), name="static")

    # Serve index.html for all non-API routes (SPA fallback)
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str = ""):
        file_path = os.path.join(frontend_dist, full_path) if full_path else os.path.join(frontend_dist, "index.html")
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
