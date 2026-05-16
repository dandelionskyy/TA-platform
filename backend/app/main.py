from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.routers import auth, chat, teacher, ta, robot

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # await init_db()  # Uncomment when DB is available
    yield
    # Shutdown
    # await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS — allow all origins in dev; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(teacher.router)
app.include_router(ta.router)
app.include_router(robot.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
