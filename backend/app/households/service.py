import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdInvite, HouseholdMember
from app.models.user import User

INVITE_TTL = timedelta(days=14)


class AlreadyInHousehold(Exception):
    """The user already belongs to a household."""


class NotInHousehold(Exception):
    """The user belongs to no household."""


class InviteNotFound(Exception):
    """No usable invite matches the token."""


class InviteExpired(Exception):
    """The invite is past its expiry."""


def get_membership(db: Session, user: User) -> HouseholdMember | None:
    return db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))


def get_household_for_user(db: Session, user: User) -> Household | None:
    membership = get_membership(db, user)
    return db.get(Household, membership.household_id) if membership else None


def create_household(db: Session, owner: User, name: str) -> Household:
    if get_membership(db, owner) is not None:
        raise AlreadyInHousehold(f"{owner.email} already belongs to a household")

    household = Household(name=name, created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))
    db.flush()
    return household


def list_members(db: Session, household_id: uuid.UUID) -> list[HouseholdMember]:
    return list(
        db.scalars(
            select(HouseholdMember)
            .where(HouseholdMember.household_id == household_id)
            .order_by(HouseholdMember.created_at)
        )
    )


def invite_member(
    db: Session, household: Household, email: str, *, now: datetime | None = None
) -> HouseholdInvite:
    issued_at = now or datetime.now(UTC)
    invite = HouseholdInvite(
        household_id=household.id,
        email=email.lower(),
        token=secrets.token_urlsafe(32),
        expires_at=issued_at + INVITE_TTL,
    )
    db.add(invite)
    db.flush()
    return invite


def accept_invite(
    db: Session, user: User, token: str, *, now: datetime | None = None
) -> HouseholdMember:
    invite = db.scalar(
        select(HouseholdInvite).where(
            HouseholdInvite.token == token, HouseholdInvite.accepted_at.is_(None)
        )
    )
    if invite is None:
        raise InviteNotFound("That invitation is not valid")

    moment = now or datetime.now(UTC)
    if invite.expires_at < moment:
        raise InviteExpired("That invitation has expired")

    if get_membership(db, user) is not None:
        raise AlreadyInHousehold(f"{user.email} already belongs to a household")

    invite.accepted_at = moment
    membership = HouseholdMember(household_id=invite.household_id, user_id=user.id)
    db.add(membership)
    db.flush()
    return membership


def leave_household(db: Session, user: User) -> None:
    """Return a member to solo tracking.

    Nothing of theirs moves: profile, targets, diary and plans were always
    per-user. When the last member leaves, the household row goes too —
    its unaccepted invites cascade away with it.
    """
    membership = get_membership(db, user)
    if membership is None:
        raise NotInHousehold(f"{user.email} belongs to no household")

    household_id = membership.household_id
    db.delete(membership)
    db.flush()

    if not list_members(db, household_id):
        db.delete(db.get(Household, household_id))
        db.flush()


def update_visibility(
    db: Session,
    user: User,
    *,
    share_progress: bool | None = None,
    share_health: bool | None = None,
) -> HouseholdMember:
    membership = get_membership(db, user)
    if membership is None:
        raise NotInHousehold(f"{user.email} belongs to no household")

    if share_progress is not None:
        membership.share_progress = share_progress
    if share_health is not None:
        membership.share_health = share_health

    db.flush()
    return membership
