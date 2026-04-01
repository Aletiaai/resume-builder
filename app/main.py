"""FastAPI app entry point.

Initializes logging, Supabase client, and mounts all routers.
"""

import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth, billing, resume
from app.services.logging_service import LoggingService
from app.services.storage_service import StorageService


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Set up rotating file logger + console handler."""
    environment = os.getenv("ENVIRONMENT", "development")
    log_level = logging.DEBUG if environment == "development" else logging.INFO

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


_configure_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    logger.info("Starting resume-builder application...")

    # Supabase client
    from supabase import create_client
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_KEY"]
    supabase = create_client(supabase_url, supabase_key)
    app.state.supabase = supabase

    # Service singletons
    app.state.storage_svc = StorageService(supabase)
    app.state.logging_svc = LoggingService(supabase)

    logger.info("Application startup complete.")
    yield

    logger.info("Application shutting down.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Resume Builder",
    description="Genera currículums adaptados a ofertas de trabajo con IA.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restrict to app domain in production
_environment = os.getenv("ENVIRONMENT", "development")
if _environment == "production":
    _origins = [os.getenv("APP_DOMAIN", "*")]
else:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(billing.router)

# Serve frontend as static files
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir / "static")), name="static")
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}
