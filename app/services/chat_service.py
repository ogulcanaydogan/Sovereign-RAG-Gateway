import logging
from hashlib import sha256
from time import perf_counter

from fastapi import Request

from app.audit.writer import AuditValidationError, AuditWriter
from app.config.settings import Settings
from app.core.errors import AppError
from app.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.policy.client import OPAClient, PolicyTimeoutError, PolicyValidationError
from app.policy.transforms import apply_transforms
from app.providers.base import ChatProvider, ProviderError
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
    ):
        self._settings = settings
        self._policy_client = policy_client
        self._provider = provider
        self._redaction_engine = redaction_engine
        self._audit_writer = audit_writer

    async def handle_chat(
        self, request: Request, payload: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification

        policy_input = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "requested_model": payload.model,
            "classification": classification,
            "estimated_tokens": sum(len(msg.content.split()) for msg in payload.messages),
            "connector_targets": [],
            "request_metadata": {
                "request_id": request_id,
            },
        }

        try:
            decision = self._policy_client.evaluate(policy_input)
        except PolicyTimeoutError as exc:
            raise AppError(
                503, "policy_unavailable", "policy", "Policy service unavailable"
            ) from exc
        except PolicyValidationError as exc:
            raise AppError(
                503, "policy_contract_invalid", "policy", "Policy decision contract invalid"
            ) from exc

        if not decision.allow:
            reason = decision.deny_reason or "policy_denied"
            raise AppError(403, "policy_denied", "policy", reason)

        transformed_request = apply_transforms(payload.model_dump(), decision.transforms)
        messages: list[dict[str, str]] = transformed_request["messages"]

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

        policy_decision_label = "transform" if decision.transforms else "allow"
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

        try:
            decision = self._policy_client.evaluate(policy_input)
        except PolicyTimeoutError as exc:
            raise AppError(
                503, "policy_unavailable", "policy", "Policy service unavailable"
            ) from exc
        except PolicyValidationError as exc:
            raise AppError(
                503, "policy_contract_invalid", "policy", "Policy decision contract invalid"
            ) from exc

        if not decision.allow:
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
        policy_decision_label = "transform" if decision.transforms else "allow"

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

    @staticmethod
    def request_fingerprint(messages: list[dict[str, str]]) -> str:
        serialized = "|".join(f"{m['role']}:{m['content']}" for m in messages)
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _app_error_from_provider_error(exc: ProviderError) -> AppError:
        if exc.status_code in {429, 502, 503}:
            return AppError(exc.status_code, exc.code, exc.error_type, exc.message)
        return AppError(502, "provider_upstream_error", "provider", exc.message)
