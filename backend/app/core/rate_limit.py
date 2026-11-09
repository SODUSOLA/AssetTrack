from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.errors import error_body

# In-memory storage: correct for a single API process. Behind a proxy the client address must be
# configured at deploy time (Milestone 9) or every request appears to come from the proxy.
limiter = Limiter(key_func=get_remote_address)

LOGIN_LIMIT = "5/minute"


async def _rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=error_body("RATE_LIMITED", f"Too many requests ({exc.detail}). Try again later."),
        headers={"Retry-After": "60"},
    )


def register_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
