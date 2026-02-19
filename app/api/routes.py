from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.metrics import metrics_router
from app.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()
router.include_router(metrics_router)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, object]:
    service: ChatService = request.app.state.chat_service
    dependencies = service.readiness()
    status = "ready" if all(value == "ok" for value in dependencies.values()) else "degraded"
    return {"status": status, "dependencies": dependencies}


@router.get("/v1/models")
def list_models(request: Request) -> dict[str, object]:
    service: ChatService = request.app.state.chat_service
    return service.list_models()


@router.get("/v1/traces/{request_id}")
def get_trace(request: Request, request_id: str) -> dict[str, object]:
    service: ChatService = request.app.state.chat_service
    return service.get_trace(request_id)


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    response_model_exclude_none=True,
)
async def chat_completions(
    request: Request, payload: ChatCompletionRequest
) -> ChatCompletionResponse | StreamingResponse:
    service: ChatService = request.app.state.chat_service
    if payload.stream:
        frames = await service.handle_chat_stream(request, payload)
        return StreamingResponse(
            frames,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return await service.handle_chat(request, payload)


@router.post("/v1/embeddings", response_model=EmbeddingsResponse)
async def embeddings(request: Request, payload: EmbeddingsRequest) -> EmbeddingsResponse:
    service: ChatService = request.app.state.chat_service
    return await service.handle_embeddings(request, payload)
