import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.routers import auth, chat, teacher, ta, robot

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — auto-create tables in SQLite
    await init_db()
    # Create uploads dir if needed
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Seed demo accounts (teacher + TA + student) if not exist
    from app.core.database import AsyncSessionFactory
    from app.seed_demo import seed_demo_accounts
    async with AsyncSessionFactory() as db:
        await seed_demo_accounts(db)
        await db.commit()
    yield
    # Shutdown
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
    allow_origins=["*"],
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
