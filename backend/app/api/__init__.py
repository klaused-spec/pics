from .auth import auth_router
from .media import router as media_router
from .persons import router as persons_router
from .jobs import router as jobs_router
from .albums import router as albums_router
from .settings import router as settings_router
from .mobile import router as mobile_router
from .music import router as music_router
from .slideshow_render import router as slideshow_render_router
from .logs import router as logs_router

__all__ = ["auth_router", "media_router", "persons_router", "jobs_router", "albums_router", "settings_router", "mobile_router", "music_router", "slideshow_render_router", "logs_router"]
