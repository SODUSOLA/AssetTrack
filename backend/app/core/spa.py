"""Serving the built web app (frontend/) from the API container, same origin as /api/v1.

Same origin matters: the refresh token is a SameSite=Strict cookie scoped to /api/v1/auth.
"""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
APP_PREFIX = "/app"

# The page index.html carries this where the nonce goes; it is replaced on every request.
NONCE_PLACEHOLDER = "__CSP_NONCE__"


def content_security_policy(nonce: str | None = None) -> str:
    """Scripts and styles only from this origin; no inline script, no framing.

    The one exception is a `<style>` element carrying this request's nonce. The dialog and menu
    library locks page scrolling by injecting a style element whose text depends on the scrollbar
    width, so it cannot be allowed by hash; the page hands the library the nonce instead. Without a
    nonce (assets, errors) no inline style is allowed at all.
    """
    style = "style-src 'self'" + (f" 'nonce-{nonce}'" if nonce else "")
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            style,
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


CSP = content_security_policy()


class SPAStaticFiles(StaticFiles):
    """Static files that answer unknown paths with the app shell, so deep links survive a reload."""

    async def get_response(self, path: str, scope: Scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        if response is None or response.status_code == 404:
            if "." in Path(path).name:  # a missing script, style or image really is missing
                raise HTTPException(status_code=404)
            response = await super().get_response("index.html", scope)
            path = "index.html"
        if isinstance(response, FileResponse) and Path(response.path).name == "index.html":
            response = self._shell_with_nonce(response)
        if path.startswith("assets/"):  # content-hashed by the build
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @staticmethod
    def _shell_with_nonce(shell: FileResponse) -> HTMLResponse:
        """The app shell with a fresh nonce in the page and in its policy header."""
        nonce = secrets.token_urlsafe(18)
        html = Path(shell.path).read_text(encoding="utf-8").replace(NONCE_PLACEHOLDER, nonce)
        return HTMLResponse(
            html, headers={"Content-Security-Policy": content_security_policy(nonce)}
        )


def install_web_app(app: FastAPI, static_dir: Path = STATIC_DIR) -> bool:
    """Mount the built app at /app and redirect / there. Returns whether a build was found."""
    built = (static_dir / "index.html").is_file()
    if built:
        app.mount(APP_PREFIX, SPAStaticFiles(directory=static_dir, html=True), name="web-app")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(f"{APP_PREFIX}/" if built else "/docs")

    return built


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path == APP_PREFIX or request.url.path.startswith(f"{APP_PREFIX}/"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        return response
