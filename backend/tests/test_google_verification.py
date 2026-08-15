import pytest

from app.auth import google as google_auth
from app.auth.google import InvalidGoogleToken, verify_google_id_token


def _patch_claims(monkeypatch, claims):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: claims,
    )


def test_returns_identity_for_a_valid_token(monkeypatch):
    _patch_claims(
        monkeypatch,
        {
            "sub": "google-sub-1",
            "email": "person@example.com",
            "email_verified": True,
            "name": "A Person",
        },
    )

    identity = verify_google_id_token("any-token")

    assert identity.google_sub == "google-sub-1"
    assert identity.email == "person@example.com"
    assert identity.name == "A Person"


def test_falls_back_to_email_when_google_sends_no_name(monkeypatch):
    _patch_claims(
        monkeypatch,
        {"sub": "google-sub-2", "email": "noname@example.com", "email_verified": True},
    )

    identity = verify_google_id_token("any-token")

    assert identity.name == "noname@example.com"


def test_rejects_an_unverified_email(monkeypatch):
    _patch_claims(
        monkeypatch,
        {
            "sub": "google-sub-3",
            "email": "unverified@example.com",
            "email_verified": False,
            "name": "Unverified",
        },
    )

    with pytest.raises(InvalidGoogleToken):
        verify_google_id_token("any-token")


def test_rejects_a_token_google_will_not_validate(monkeypatch):
    def explode(token, request, audience):
        raise ValueError("Token has wrong audience")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", explode)

    with pytest.raises(InvalidGoogleToken):
        verify_google_id_token("tampered-token")
