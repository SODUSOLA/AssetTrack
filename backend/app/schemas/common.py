from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, StringConstraints

# Free-text fields: trimmed and non-empty.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _validate_email(value: str) -> str:
    # Syntax only (no DNS lookups). test_environment=True accepts the reserved ".test" TLD that
    # the test suite uses; other reserved names such as ".local" or ".invalid" are still rejected.
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


Email = Annotated[str, AfterValidator(_validate_email)]
