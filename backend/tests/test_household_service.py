from datetime import UTC, datetime, timedelta

import pytest

from app.households.service import (
    AlreadyInHousehold,
    InviteExpired,
    InviteNotFound,
    NotInHousehold,
    accept_invite,
    create_household,
    get_household_for_user,
    invite_member,
    list_members,
    update_visibility,
)
from app.models.user import User


def _user(db, email):
    user = User(google_sub=f"sub-{email}", email=email, name=email)
    db.add(user)
    db.flush()
    return user


def test_creating_a_household_enrols_the_owner(db):
    owner = _user(db, "owner@example.com")

    household = create_household(db, owner, "Sudev's Home")

    assert household.name == "Sudev's Home"
    assert get_household_for_user(db, owner).id == household.id
    assert [m.user_id for m in list_members(db, household.id)] == [owner.id]


def test_a_user_cannot_create_a_second_household(db):
    owner = _user(db, "owner2@example.com")
    create_household(db, owner, "First")

    with pytest.raises(AlreadyInHousehold):
        create_household(db, owner, "Second")


def test_an_invited_user_joins_the_household(db):
    owner = _user(db, "owner3@example.com")
    guest = _user(db, "guest@example.com")
    household = create_household(db, owner, "Home")
    invite = invite_member(db, household, "guest@example.com")

    membership = accept_invite(db, guest, invite.token)

    assert membership.household_id == household.id
    assert get_household_for_user(db, guest).id == household.id
    assert len(list_members(db, household.id)) == 2


def test_an_invite_cannot_be_used_twice(db):
    owner = _user(db, "owner4@example.com")
    guest = _user(db, "guest4@example.com")
    household = create_household(db, owner, "Home")
    invite = invite_member(db, household, "guest4@example.com")
    accept_invite(db, guest, invite.token)

    other = _user(db, "other4@example.com")
    with pytest.raises(InviteNotFound):
        accept_invite(db, other, invite.token)


def test_an_expired_invite_is_refused(db):
    owner = _user(db, "owner5@example.com")
    guest = _user(db, "guest5@example.com")
    household = create_household(db, owner, "Home")
    long_ago = datetime.now(UTC) - timedelta(days=30)
    invite = invite_member(db, household, "guest5@example.com", now=long_ago)

    with pytest.raises(InviteExpired):
        accept_invite(db, guest, invite.token)


def test_an_unknown_token_is_refused(db):
    guest = _user(db, "guest6@example.com")

    with pytest.raises(InviteNotFound):
        accept_invite(db, guest, "no-such-token")


def test_health_sharing_can_be_switched_on(db):
    owner = _user(db, "owner7@example.com")
    create_household(db, owner, "Home")

    membership = update_visibility(db, owner, share_health=True)

    assert membership.share_health is True
    assert membership.share_progress is True


def test_visibility_requires_a_household(db):
    loner = _user(db, "loner@example.com")

    with pytest.raises(NotInHousehold):
        update_visibility(db, loner, share_progress=False)
