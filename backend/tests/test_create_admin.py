from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import User
from app.models.enums import UserRole
from scripts import create_admin

PASSWORD = "bootstrap-password-1"


@pytest.fixture
def run_script(monkeypatch: pytest.MonkeyPatch, db: Session):
    """Run the script's main() against the per-test transaction."""

    @contextmanager
    def _session():
        yield db

    monkeypatch.setattr(create_admin, "SessionLocal", _session)

    def run(email: str, name: str = "Head", password: str | None = PASSWORD) -> None:
        monkeypatch.setattr("sys.argv", ["create_admin", "--email", email, "--name", name])
        if password is None:
            monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        else:
            monkeypatch.setenv("ADMIN_PASSWORD", password)
        create_admin.main()

    return run


def test_creates_a_working_admin(run_script, api: TestClient, db: Session, capsys) -> None:
    run_script("head@lasrra.test")
    user = db.scalar(select(User).where(User.email == "head@lasrra.test"))
    assert user is not None and user.role is UserRole.admin and user.unit_id is None
    out = capsys.readouterr().out
    assert "Created admin head@lasrra.test" in out
    assert PASSWORD not in out

    login = api.post("/api/v1/auth/login", json={"email": "head@lasrra.test", "password": PASSWORD})
    assert login.status_code == 200


def test_duplicate_email_exits_with_message(run_script) -> None:
    run_script("head@lasrra.test")
    with pytest.raises(SystemExit) as exc:
        run_script("HEAD@lasrra.test")
    assert "EMAIL_TAKEN" in str(exc.value)


@pytest.mark.parametrize(
    ("email", "password", "field"),
    [
        ("head@lasrra.test", "short", "password"),
        ("not-an-email", PASSWORD, "email"),
        ("head@lasrra.local", PASSWORD, "email"),
    ],
)
def test_invalid_input_exits_with_the_field_name(run_script, email, password, field) -> None:
    with pytest.raises(SystemExit) as exc:
        run_script(email, password=password)
    assert f"{field}:" in str(exc.value)


def test_prompts_for_password_when_env_is_unset(run_script, monkeypatch, db: Session) -> None:
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    run_script("prompted@lasrra.test", password=None)
    assert db.scalar(select(User).where(User.email == "prompted@lasrra.test")) is not None


def test_mismatched_prompts_abort(run_script, monkeypatch) -> None:
    answers = iter([PASSWORD, "something-different-1"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    with pytest.raises(SystemExit) as exc:
        run_script("prompted@lasrra.test", password=None)
    assert "do not match" in str(exc.value)
