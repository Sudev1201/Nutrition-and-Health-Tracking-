import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.config import settings
from app.cycle.router import router as cycle_router
from app.diary.router import router as diary_router
from app.foods.router import router as foods_router
from app.households.router import router as households_router
from app.llm import crypto
from app.llm.router import NO_STORE, NOT_UNDERSTOOD
from app.llm.router import router as llm_router
from app.planner.router import DESCRIBED_HEADER
from app.planner.router import router as planner_router
from app.profiles.router import router as profile_router
from app.reminders.router import push_router, settings_router
from app.reminders.runner import run_forever
from app.reports.router import router as reports_router
from app.targets.router import router as targets_router
from app.weight.router import router as weight_router

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the reminder loop beside the API, on the instance configured to send them.

    Off unless SCHEDULER_ENABLED is set. Every TestClient runs this lifespan, and
    the loop opens its own sessions on the development database's engine, not the
    test's. The loop signs pushes with the VAPID private key, so without one it
    would only record every reminder as failed.
    """
    # Parse the LLM keyring now, so a malformed LLM_KEY_ENCRYPTION_KEYS stops the app at
    # boot instead of failing the first user who saves a key. An empty one only turns AI
    # descriptions off.
    crypto.keyring()

    task = None
    if settings.scheduler_enabled and settings.vapid_private_key:
        task = asyncio.create_task(run_forever())
    elif settings.scheduler_enabled:
        logger.warning("SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="healthMonitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # A cross-origin fetch shows a script only the response headers listed here.
    expose_headers=[DESCRIBED_HEADER],
)

app.include_router(auth_router)
app.include_router(households_router)
app.include_router(foods_router)
app.include_router(profile_router)
app.include_router(targets_router)
app.include_router(diary_router)
app.include_router(planner_router)
app.include_router(weight_router)
app.include_router(cycle_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(push_router)
app.include_router(llm_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's own 422, except on /settings/llm, where it would quote the key.

    A body that fails validation before the route runs -- `api_key` misspelt, missing or
    not a string, or a body that is not JSON -- comes back in FastAPI's 422 with the input
    that failed, and on /settings/llm that input is the key. There the answer is one fixed
    sentence instead, uncached like the answers of the handlers there.
    """
    if request.url.path.startswith("/settings/llm"):
        return JSONResponse(
            {"detail": NOT_UNDERSTOOD},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            headers={"Cache-Control": NO_STORE},
        )
    return await request_validation_exception_handler(request, exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
