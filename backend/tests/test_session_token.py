from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.session import InvalidSession, create_session_token, read_session_token


def test_round_trips_the_user_id():
    token = create_session_token("11111111-1111-1111-1111-111111111111")

    assert read_session_token(token) == "11111111-1111-1111-1111-111111111111"


def test_rejects_an_expired_token():
    long_ago = datetime.now(UTC) - timedelta(days=400)
    token = create_session_token("some-user", now=long_ago)

    with pytest.raises(InvalidSession):
        read_session_token(token)


def test_rejects_a_tampered_token():
    token = create_session_token("some-user")
    tampered = token[:-4] + "abcd"

    with pytest.raises(InvalidSession):
        read_session_token(tampered)


def test_rejects_a_token_signed_with_another_secret():
    forged = jwt.encode(
        {
            "sub": "intruder",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        "not-our-secret",
        algorithm="HS256",
    )

    with pytest.raises(InvalidSession):
        read_session_token(forged)
