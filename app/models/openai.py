from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class RagOptions(BaseModel):
    enabled: bool = False
    connector: str = "filesystem"
    top_k: int = Field(default=3, ge=1, le=20)
    filters: dict[str, str] | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=256, ge=1, le=8192)
    rag: RagOptions | None = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Citation(BaseModel):
    source_id: str
    connector: str
    uri: str
    chunk_id: str
    score: float


class ChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    citations: list[Citation] | None = None


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: Literal["stop"] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class EmbeddingsRequest(BaseModel):
    model: str
    input: str | list[str]


class EmbeddingItem(BaseModel):
    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingsUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingItem]
    model: str
    usage: EmbeddingsUsage
