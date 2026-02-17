import logging
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app.audit.writer import AuditValidationError, AuditWriter
from app.config.settings import Settings
from app.core.errors import AppError
from app.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Citation,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.policy.client import OPAClient, PolicyTimeoutError, PolicyValidationError
from app.policy.models import PolicyDecision
from app.policy.transforms import apply_transforms
from app.providers.base import ChatProvider, ProviderError
from app.rag.retrieval import (
    ConnectorNotFoundError,
    RetrievalDeniedError,
    RetrievalOrchestrator,
    RetrievalRequest,
)
from app.rag.types import DocumentChunk
from app.redaction.engine import RedactionEngine

logger = logging.getLogger("srg.chat")


class ChatService:
    def __init__(
        self,
        settings: Settings,
        policy_client: OPAClient,
        provider: ChatProvider,
        redaction_engine: RedactionEngine,
        audit_writer: AuditWriter,
        retrieval_orchestrator: RetrievalOrchestrator | None = None,
    ):
        self._settings = settings
        self._policy_client = policy_client
        self._provider = provider
        self._redaction_engine = redaction_engine
        self._audit_writer = audit_writer
        self._retrieval_orchestrator = retrieval_orchestrator

    async def handle_chat(
        self, request: Request, payload: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification

        rag_requested = bool(self._settings.rag_enabled and payload.rag and payload.rag.enabled)
        requested_connector = payload.rag.connector if rag_requested and payload.rag else ""

        policy_input = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "requested_model": payload.model,
            "classification": classification,
            "estimated_tokens": sum(len(msg.content.split()) for msg in payload.messages),
            "connector_targets": [requested_connector] if rag_requested else [],
            "request_metadata": {
                "request_id": request_id,
            },
        }

        decision = self._resolve_policy_decision(policy_input, request_id=request_id)

        if not decision.allow and self._settings.opa_mode == "enforce":
            reason = decision.deny_reason or "policy_denied"
            raise AppError(403, "policy_denied", "policy", reason)

        transformed_request = apply_transforms(payload.model_dump(), decision.transforms)
        messages: list[dict[str, str]] = transformed_request["messages"]

        citations: list[Citation] | None = None
        if rag_requested and payload.rag:
            retrieval_request = RetrievalRequest(
                query=self._last_user_message(payload),
                connector=payload.rag.connector,
                k=payload.rag.top_k,
                filters=payload.rag.filters or {},
            )
            chunks = self._retrieve_chunks(retrieval_request, decision)
            if chunks:
                messages.append(
                    {
                        "role": "system",
                        "content": self._build_retrieval_context(chunks),
                    }
                )
                citations = self._citations_from_chunks(chunks)

        redaction_count = 0
        if self._settings.redaction_enabled and classification in {"phi", "pii"}:
            redaction_result = self._redaction_engine.redact_messages(messages)
            messages = redaction_result.messages
            redaction_count = redaction_result.redaction_count

        selected_model = str(transformed_request.get("model", payload.model))
        max_tokens = transformed_request.get("max_tokens")

        try:
            provider_result = await self._provider.chat(selected_model, messages, max_tokens)
        except ProviderError as exc:
            raise self._app_error_from_provider_error(exc) from exc
        response = ChatCompletionResponse.model_validate(provider_result)

        if citations and response.choices:
            response.choices[0].message.citations = citations

        policy_decision_label = self._policy_decision_label(decision)
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost_usd = round((tokens_in + tokens_out) * 0.000001, 8)

        audit_event = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "requested_model": payload.model,
            "selected_model": selected_model,
            "provider": self._settings.provider_name,
            "policy_decision": policy_decision_label,
            "transforms_applied": [action.type for action in decision.transforms],
            "redaction_count": redaction_count,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "policy_hash": decision.policy_hash,
        }
        if decision.deny_reason is not None:
            audit_event["deny_reason"] = decision.deny_reason

        try:
            self._audit_writer.write_event(audit_event)
        except AuditValidationError as exc:
            raise AppError(
                502, "audit_write_failed", "provider", "Failed to persist audit event"
            ) from exc

        latency_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "chat_completed",
            extra={
                "request_id": request_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "model": selected_model,
                "policy_decision": policy_decision_label,
                "redaction_count": redaction_count,
                "provider": self._settings.provider_name,
                "latency_ms": latency_ms,
                "token_in": tokens_in,
                "token_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )
        return response

    async def handle_embeddings(
        self, request: Request, payload: EmbeddingsRequest
    ) -> EmbeddingsResponse:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification

        raw_inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        if not raw_inputs:
            raise AppError(422, "request_validation_failed", "validation", "Input cannot be empty")

        policy_input = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "requested_model": payload.model,
            "classification": classification,
            "estimated_tokens": sum(len(item.split()) for item in raw_inputs),
            "connector_targets": [],
            "request_metadata": {"request_id": request_id},
        }

        decision = self._resolve_policy_decision(policy_input, request_id=request_id)

        if not decision.allow and self._settings.opa_mode == "enforce":
            reason = decision.deny_reason or "policy_denied"
            raise AppError(403, "policy_denied", "policy", reason)

        selected_model = payload.model
        for transform in decision.transforms:
            if transform.type == "override_model":
                selected_model = str(transform.args.get("model", selected_model))

        inputs = list(raw_inputs)
        redaction_count = 0
        if self._settings.redaction_enabled and classification in {"phi", "pii"}:
            redaction_result = self._redaction_engine.redact_messages(
                [{"role": "user", "content": text} for text in inputs]
            )
            inputs = [item["content"] for item in redaction_result.messages]
            redaction_count = redaction_result.redaction_count

        try:
            provider_result = await self._provider.embeddings(selected_model, inputs)
        except ProviderError as exc:
            raise self._app_error_from_provider_error(exc) from exc
        response = EmbeddingsResponse.model_validate(provider_result)

        tokens_in = response.usage.prompt_tokens
        tokens_out = 0
        cost_usd = round(tokens_in * 0.0000002, 8)
        policy_decision_label = self._policy_decision_label(decision)

        audit_event = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "requested_model": payload.model,
            "selected_model": selected_model,
            "provider": self._settings.provider_name,
            "policy_decision": policy_decision_label,
            "transforms_applied": [action.type for action in decision.transforms],
            "redaction_count": redaction_count,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "policy_hash": decision.policy_hash,
        }
        if decision.deny_reason is not None:
            audit_event["deny_reason"] = decision.deny_reason

        try:
            self._audit_writer.write_event(audit_event)
        except AuditValidationError as exc:
            raise AppError(
                502, "audit_write_failed", "provider", "Failed to persist audit event"
            ) from exc

        latency_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "embeddings_completed",
            extra={
                "request_id": request_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "model": selected_model,
                "policy_decision": policy_decision_label,
                "redaction_count": redaction_count,
                "provider": self._settings.provider_name,
                "latency_ms": latency_ms,
                "token_in": tokens_in,
                "token_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )
        return response

    def readiness(self) -> dict[str, str]:
        policy_schema = self._settings.contracts_dir / "policy-decision.schema.json"
        audit_schema = self._settings.contracts_dir / "audit-event.schema.json"
        return {
            "policy_schema": "ok" if policy_schema.exists() else "missing",
            "audit_schema": "ok" if audit_schema.exists() else "missing",
            "provider": "ok",
        }

    def list_models(self) -> dict[str, object]:
        data = [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "srg",
            }
            for model in self._settings.configured_models
        ]
        return {"object": "list", "data": data}

    @staticmethod
    def request_fingerprint(messages: list[dict[str, str]]) -> str:
        serialized = "|".join(f"{m['role']}:{m['content']}" for m in messages)
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _app_error_from_provider_error(exc: ProviderError) -> AppError:
        if exc.status_code in {429, 502, 503}:
            return AppError(exc.status_code, exc.code, exc.error_type, exc.message)
        return AppError(502, "provider_upstream_error", "provider", exc.message)

    def _resolve_policy_decision(
        self, policy_input: dict[str, object], request_id: str
    ) -> PolicyDecision:
        try:
            return self._policy_client.evaluate(policy_input)
        except PolicyTimeoutError as exc:
            if self._settings.opa_mode == "observe":
                return self._observe_mode_decision(request_id, f"policy_timeout:{exc}")
            raise AppError(
                503, "policy_unavailable", "policy", "Policy service unavailable"
            ) from exc
        except PolicyValidationError as exc:
            if self._settings.opa_mode == "observe":
                return self._observe_mode_decision(
                    request_id, f"policy_contract_invalid:{exc}"
                )
            raise AppError(
                503, "policy_contract_invalid", "policy", "Policy decision contract invalid"
            ) from exc

    def _observe_mode_decision(self, request_id: str, reason: str) -> PolicyDecision:
        logger.warning(
            "policy_observe_bypass",
            extra={"request_id": request_id, "policy_decision": "observe"},
        )
        return PolicyDecision(
            decision_id=f"observe-{uuid4()}",
            allow=True,
            deny_reason=reason,
            policy_hash="observe-mode",
            evaluated_at=datetime.now(UTC).isoformat(),
            transforms=[],
        )

    def _policy_decision_label(self, decision: PolicyDecision) -> str:
        if self._settings.opa_mode == "observe" and decision.deny_reason:
            return "observe"
        if decision.transforms:
            return "transform"
        return "allow"

    def _allowed_connectors(self, decision: PolicyDecision) -> set[str] | None:
        if (
            decision.connector_constraints is not None
            and decision.connector_constraints.allowed_connectors is not None
        ):
            return set(decision.connector_constraints.allowed_connectors)
        if self._settings.rag_allowed_connector_set:
            return set(self._settings.rag_allowed_connector_set)
        return None

    def _retrieve_chunks(
        self,
        retrieval_request: RetrievalRequest,
        decision: PolicyDecision,
    ) -> list[DocumentChunk]:
        if self._retrieval_orchestrator is None:
            raise AppError(
                503,
                "retrieval_unavailable",
                "provider",
                "Retrieval orchestrator is not configured",
            )

        try:
            return self._retrieval_orchestrator.retrieve(
                request=retrieval_request,
                allowed_connectors=self._allowed_connectors(decision),
            )
        except RetrievalDeniedError as exc:
            raise AppError(
                403,
                "retrieval_forbidden",
                "policy",
                str(exc),
            ) from exc
        except ConnectorNotFoundError as exc:
            raise AppError(
                422,
                "connector_not_found",
                "validation",
                f"Connector not configured: {exc}",
            ) from exc

    @staticmethod
    def _last_user_message(payload: ChatCompletionRequest) -> str:
        for message in reversed(payload.messages):
            if message.role == "user":
                return message.content
        return payload.messages[-1].content

    @staticmethod
    def _build_retrieval_context(chunks: list[DocumentChunk]) -> str:
        lines = [f"[{chunk.chunk_id}] {chunk.text}" for chunk in chunks]
        return "Retrieved context chunks:\n" + "\n".join(lines)

    @staticmethod
    def _citations_from_chunks(chunks: list[DocumentChunk]) -> list[Citation]:
        return [
            Citation(
                source_id=chunk.source_id,
                connector=chunk.connector,
                uri=chunk.uri,
                chunk_id=chunk.chunk_id,
                score=chunk.score,
            )
            for chunk in chunks
        ]
