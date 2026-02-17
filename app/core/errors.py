from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class ErrorEnvelope:
    code: str
    message: str
    type: str
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "type": self.type,
                "request_id": self.request_id,
            }
        }


class AppError(Exception):
    def __init__(self, status_code: int, code: str, error_type: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.error_type = error_type
        self.message = message


def request_id_from_request(request: Request) -> str:
    state_id = getattr(request.state, "request_id", None)
    header_id = request.headers.get("x-request-id")
    return state_id or header_id or str(uuid4())


def app_error_response(
    status_code: int, code: str, error_type: str, message: str, request_id: str
) -> JSONResponse:
    envelope = ErrorEnvelope(code=code, message=message, type=error_type, request_id=request_id)
    response = JSONResponse(status_code=status_code, content=envelope.as_dict())
    response.headers["x-request-id"] = request_id
    return response
