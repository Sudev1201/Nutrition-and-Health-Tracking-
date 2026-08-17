from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    # min_length=1 admits a single space, which the service strips to "" -- a
    # "%%" LIKE pattern matching every dish in the database. A blank search is
    # a client bug, so it gets a validation error, not twenty arbitrary rows.
    try:
        return service.search_foods(db, q, limit)
    except service.EmptySearchQuery as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
