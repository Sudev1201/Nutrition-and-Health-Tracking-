import pytest
from sqlalchemy.exc import IntegrityError

from app.models.household import Household, HouseholdMember
from app.models.user import User


def _user(db, email):
    user = User(google_sub=f"sub-{email}", email=email, name=email)
    db.add(user)
    db.flush()
    return user


def test_membership_defaults_share_progress_but_not_health(db):
    owner = _user(db, "owner@example.com")
    household = Household(name="Home", created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    membership = HouseholdMember(household_id=household.id, user_id=owner.id)
    db.add(membership)
    db.flush()

    assert membership.share_progress is True
    assert membership.share_health is False


def test_a_user_cannot_join_the_same_household_twice(db):
    owner = _user(db, "twice@example.com")
    household = Household(name="Home", created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))
    db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))

    with pytest.raises(IntegrityError):
        db.flush()
