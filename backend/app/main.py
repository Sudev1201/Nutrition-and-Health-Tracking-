from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.foods.router import router as foods_router
from app.households.router import router as households_router

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
