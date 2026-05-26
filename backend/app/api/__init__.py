from .media import router as media_router
from .persons import router as persons_router
from .jobs import router as jobs_router
from .albums import router as albums_router
from .settings import router as settings_router

__all__ = ["media_router", "persons_router", "jobs_router", "albums_router", "settings_router"]
