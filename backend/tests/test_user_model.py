import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User


def test_user_defaults_to_india_timezone(db):
    user = User(google_sub="sub-123", email="a@example.com", name="Test Person")

    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.timezone == "Asia/Kolkata"


def test_google_sub_is_unique(db):
    db.add(User(google_sub="dup", email="one@example.com", name="One"))
    db.flush()
    db.add(User(google_sub="dup", email="two@example.com", name="Two"))

    with pytest.raises(IntegrityError):
        db.flush()
