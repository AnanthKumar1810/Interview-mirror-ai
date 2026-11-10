"""Optional bearer authentication. Production requires IM_AUTH_REQUIRED=true.

Argon2id for password hashes; PyJWT with fixed algorithm, issuer, audience,
short expiration, and persisted revocation on logout.
"""
from __future__ import annotations

import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException, Request

_HASH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
# Verify even unknown users to reduce username enumeration by response timing.
_DUMMY_HASH = _HASH.hash(secrets.token_urlsafe(20))
ISSUER = 'interviewmirror-ai'
AUDIENCE = 'interviewmirror-api'


def auth_required() -> bool:
    return os.getenv('IM_AUTH_REQUIRED', 'false').lower() in ('1', 'yes', 'true')


def security_key() -> str:
    key = os.getenv('IM_JWT_SECRET', '')
    if len(key) < 32:
        raise RuntimeError('IM_JWT_SECRET must be a random secret of at least 32 characters when authentication is enabled')
    return key


def validate_deployment_config():
    if os.getenv('IM_ENV', 'development').lower() == 'production':
        if not auth_required():
            raise RuntimeError('IM_AUTH_REQUIRED=true is mandatory in production')
        security_key()


def hash_password(password: str) -> str:
    return _HASH.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    try:
        return _HASH.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError):
        return False


def issue_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {'sub': user_id, 'iat': now, 'nbf': now,
               'exp': now + timedelta(minutes=60), 'iss': ISSUER,
               'aud': AUDIENCE, 'jti': str(uuid.uuid4())}
    return jwt.encode(payload, security_key(), algorithm='HS256')


def parse_token(token: str, store) -> dict:
    try:
        claims = jwt.decode(token, security_key(), algorithms=['HS256'],
                            issuer=ISSUER, audience=AUDIENCE,
                            options={'require': ['sub', 'exp', 'iat', 'nbf', 'iss', 'aud', 'jti']})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail='Invalid or expired session',
                            headers={'WWW-Authenticate': 'Bearer'}) from exc
    if store.token_is_revoked(claims['jti']) or store.user_by_id(claims['sub']) is None:
        raise HTTPException(401, 'Session revoked or account unavailable')
    return claims


def principal(request: Request, store) -> str | None:
    if not auth_required():
        return None
    bearer = request.headers.get('Authorization', '')
    if not bearer.startswith('Bearer ') or not bearer[7:].strip():
        raise HTTPException(status_code=401, detail='Sign in to use this endpoint',
                            headers={'WWW-Authenticate': 'Bearer'})
    claims = parse_token(bearer[7:].strip(), store)
    return claims['sub']
