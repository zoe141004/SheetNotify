"""JWT token tests (PyJWT-based auth)."""

import uuid

import jwt

from config import settings
from services.auth import create_access_token


def test_jwt_roundtrip():
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id)
    assert isinstance(token, str)
    assert expires_in > 0

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(user_id)
    assert "exp" in payload


def test_jwt_wrong_key_rejected():
    _, _ = create_access_token(uuid.uuid4())
    token, _ = create_access_token(uuid.uuid4())
    try:
        wrong_key = "x" * 48  # long enough to avoid PyJWT key-length warning
        jwt.decode(token, wrong_key, algorithms=[settings.JWT_ALGORITHM])
        assert False, "decode with wrong key should fail"
    except jwt.InvalidTokenError:
        pass
