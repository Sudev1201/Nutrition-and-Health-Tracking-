from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.foods import service
from app.models.user import User

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search")
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return service.search_foods(db, q, limit)
