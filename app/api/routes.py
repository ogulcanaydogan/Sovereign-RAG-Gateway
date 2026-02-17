from fastapi import APIRouter, Request

from app.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()


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


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: Request, payload: ChatCompletionRequest
) -> ChatCompletionResponse:
    service: ChatService = request.app.state.chat_service
    return await service.handle_chat(request, payload)


@router.post("/v1/embeddings", response_model=EmbeddingsResponse)
async def embeddings(request: Request, payload: EmbeddingsRequest) -> EmbeddingsResponse:
    service: ChatService = request.app.state.chat_service
    return await service.handle_embeddings(request, payload)
