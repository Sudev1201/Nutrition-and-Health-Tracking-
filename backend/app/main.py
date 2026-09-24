from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.cycle.router import router as cycle_router
from app.diary.router import router as diary_router
from app.foods.router import router as foods_router
from app.households.router import router as households_router
from app.planner.router import router as planner_router
from app.profiles.router import router as profile_router
from app.targets.router import router as targets_router
from app.weight.router import router as weight_router

app = FastAPI(title="healthMonitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
