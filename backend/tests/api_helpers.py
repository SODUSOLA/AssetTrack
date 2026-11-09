"""Fixtures-as-functions for API tests: real users, real tokens, no login round trip."""

from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.core import Unit, User
from app.models.enums import UserRole
from tests.factories import make_unit, make_user

PASSWORD = "correct-horse-battery"
_PASSWORD_HASH = hash_password(PASSWORD)  # hashed once; argon2 is deliberately slow


def bearer(user: User) -> dict[str, str]:
    token, _ = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@dataclass
class People:
    unit_a: Unit
    unit_b: Unit
    admin: User
    engineer: User
    auditor: User
    rep_a: User
    rep_b: User

    def by_role(self) -> dict[str, User]:
        return {
            "admin": self.admin,
            "engineer": self.engineer,
            "auditor": self.auditor,
            "unit_rep": self.rep_a,
        }


def build_people(db: Session) -> People:
    unit_a, unit_b = make_unit(db, name="Unit A", code="A"), make_unit(db, name="Unit B", code="B")
    people = People(
        unit_a=unit_a,
        unit_b=unit_b,
        admin=make_user(db, UserRole.admin, password_hash=_PASSWORD_HASH, email="admin@t.test"),
        engineer=make_user(db, UserRole.engineer, password_hash=_PASSWORD_HASH, email="eng@t.test"),
        auditor=make_user(db, UserRole.auditor, password_hash=_PASSWORD_HASH, email="aud@t.test"),
        rep_a=make_user(
            db, UserRole.unit_rep, unit_a, password_hash=_PASSWORD_HASH, email="a@t.test"
        ),
        rep_b=make_user(
            db, UserRole.unit_rep, unit_b, password_hash=_PASSWORD_HASH, email="b@t.test"
        ),
    )
    db.commit()  # release the savepoint so later service rollbacks cannot discard this data
    return people


@pytest.fixture
def people(db: Session) -> People:
    return build_people(db)
