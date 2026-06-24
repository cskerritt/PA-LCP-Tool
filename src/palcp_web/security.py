"""Authentication: password hashing, session helpers, and the audit log.

Password hashing uses the standard library (PBKDF2-HMAC-SHA256) so there are no
native build dependencies to break on Railway or in CI.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, User

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        _ALGO, iterations,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


class AuthRequired(Exception):
    """Raised by :func:`current_user` when no valid session exists."""


def login_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_session(request: Request) -> None:
    request.session.pop("user_id", None)


def optional_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        request.session.pop("user_id", None)
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: the logged-in user, or raise :class:`AuthRequired`."""
    user = optional_user(request, db)
    if user is None:
        raise AuthRequired()
    return user


def record_audit(db: Session, *, user_id: int, entity: str, action: str,
                 summary: str, case_id: int | None = None,
                 entity_id: int | None = None) -> None:
    """Append an edit-history entry (caller commits)."""
    db.add(AuditLog(user_id=user_id, case_id=case_id, entity=entity,
                    entity_id=entity_id, action=action, summary=summary))
