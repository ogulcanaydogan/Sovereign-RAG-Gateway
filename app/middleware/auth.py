from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config.settings import get_settings
from app.core.errors import app_error_response, request_id_from_request

REQUIRED_HEADERS = ("x-srg-tenant-id", "x-srg-user-id", "x-srg-classification")
BYPASS_PATHS = {"/healthz", "/readyz", "/openapi.json", "/docs", "/docs/oauth2-redirect"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in BYPASS_PATHS:
            return await call_next(request)

        request_id = request_id_from_request(request)
        settings = get_settings()

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return app_error_response(
                401, "auth_missing", "auth", "Missing bearer token", request_id
            )

        token = auth_header.removeprefix("Bearer ").strip()
        if token not in settings.api_key_set:
            return app_error_response(401, "auth_invalid", "auth", "Invalid API key", request_id)

        missing_headers = [header for header in REQUIRED_HEADERS if not request.headers.get(header)]
        if missing_headers:
            return app_error_response(
                422,
                "missing_required_headers",
                "validation",
                f"Missing required headers: {', '.join(missing_headers)}",
                request_id,
            )

        request.state.tenant_id = request.headers["x-srg-tenant-id"]
        request.state.user_id = request.headers["x-srg-user-id"]
        request.state.classification = request.headers["x-srg-classification"]
        return await call_next(request)
