import asyncio
import json as json_mod
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request

from app.audit.writer import AuditValidationError, AuditWriter
from app.budget.tracker import BudgetBackendError, BudgetExceededError, BudgetTracker
from app.config.settings import Settings
from app.core.errors import AppError
from app.metrics import record_request
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
from app.providers.registry import (
    ProviderRegistry,
    route_embeddings_with_fallback,
    route_stream_with_fallback,
    route_with_fallback,
)
from app.rag.retrieval import (
    ConnectorNotFoundError,
    RetrievalDeniedError,
    RetrievalOrchestrator,
    RetrievalRequest,
)
from app.rag.types import DocumentChunk
from app.redaction.engine import RedactionEngine
from app.telemetry.tracing import SpanCollector
from app.webhooks.dispatcher import WebhookDispatcher, WebhookEventType

logger = logging.getLogger("srg.chat")


class _NoopSpan:
    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        _ = exc_type, exc_val, exc_tb

    def set_attribute(self, key: str, value: Any) -> None:
        _ = key, value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        _ = name, attributes


class ChatService:
    def __init__(
        self,
        settings: Settings,
        policy_client: OPAClient,
        provider: ChatProvider,
        redaction_engine: RedactionEngine,
        audit_writer: AuditWriter,
        retrieval_orchestrator: RetrievalOrchestrator | None = None,
        provider_registry: ProviderRegistry | None = None,
        budget_tracker: BudgetTracker | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
        span_collector: SpanCollector | None = None,
    ):
        self._settings = settings
        self._policy_client = policy_client
        self._provider = provider
        self._redaction_engine = redaction_engine
        self._audit_writer = audit_writer
        self._retrieval_orchestrator = retrieval_orchestrator
        self._provider_registry = provider_registry
        self._budget_tracker = budget_tracker
        self._webhook_dispatcher = webhook_dispatcher
        self._span_collector = span_collector

    async def handle_chat(
        self, request: Request, payload: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification
        endpoint = str(request.url.path)
        webhook_events: list[dict[str, object]] = []
        budget_summary: dict[str, object] | None = None
        request_payload_hash = self._hash_value(payload.model_dump(exclude_none=True))

        with self._span(
            trace_id=request_id,
            operation="gateway.request",
            attributes={
                "endpoint": endpoint,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
            },
        ):
            rag_requested = bool(
                self._settings.rag_enabled and payload.rag and payload.rag.enabled
            )
            requested_connector = payload.rag.connector if rag_requested and payload.rag else ""

            policy_input = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "requested_model": payload.model,
                "classification": classification,
                "estimated_tokens": sum(len(msg.content.split()) for msg in payload.messages),
                "connector_targets": [requested_connector] if rag_requested else [],
                "request_metadata": {
                    "request_id": request_id,
                },
            }

            with self._span(
                trace_id=request_id,
                operation="policy.evaluate",
                attributes={
                    "endpoint": endpoint,
                    "model": payload.model,
                },
            ):
                decision = self._resolve_policy_decision(policy_input, request_id=request_id)

            if not decision.allow and self._settings.opa_mode == "enforce":
                reason = decision.deny_reason or "policy_denied"
                self._queue_webhook_event(
                    event_type=WebhookEventType.POLICY_DENIED,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "endpoint": endpoint,
                        "requested_model": payload.model,
                        "deny_reason": reason,
                    },
                    webhook_events=webhook_events,
                )
                self._write_policy_deny_audit(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    endpoint=endpoint,
                    requested_model=payload.model,
                    decision=decision,
                    reason=reason,
                    request_payload_hash=request_payload_hash,
                    streaming=False,
                    trace_id=request_id,
                    webhook_events=webhook_events,
                )
                raise AppError(403, "policy_denied", "policy", reason)

            transformed_request = apply_transforms(payload.model_dump(), decision.transforms)
            messages: list[dict[str, str]] = transformed_request["messages"]

            citations: list[Citation] | None = None
            if rag_requested and payload.rag:
                with self._span(
                    trace_id=request_id,
                    operation="rag.retrieve",
                    attributes={
                        "connector": payload.rag.connector,
                        "top_k": payload.rag.top_k,
                    },
                ):
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

            input_redaction_count = 0
            if self._settings.redaction_enabled and classification in {"phi", "pii"}:
                with self._span(
                    trace_id=request_id,
                    operation="redaction.scan",
                    attributes={"direction": "request"},
                ):
                    redaction_result = self._redaction_engine.redact_messages(messages)
                    messages = redaction_result.messages
                    input_redaction_count = redaction_result.redaction_count
            redacted_payload_hash = self._hash_value(messages)

            selected_model = str(transformed_request.get("model", payload.model))
            self._validate_model_constraints(decision, selected_model)
            max_tokens = transformed_request.get("max_tokens")
            allowed_provider_names = self._allowed_providers(decision)

            requested_budget_tokens = self._estimate_requested_tokens(messages, max_tokens)
            budget_summary = self._enforce_budget_or_deny(
                tenant_id=tenant_id,
                requested_tokens=requested_budget_tokens,
                request_id=request_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=payload.model,
                selected_model=selected_model,
                decision=decision,
                request_payload_hash=request_payload_hash,
                streaming=False,
                webhook_events=webhook_events,
            )

            provider_request_hash = self._hash_value(
                {
                    "model": selected_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
            )

            routed_provider = self._settings.provider_name
            provider_attempts = 1
            fallback_chain: list[str] = [routed_provider]

            with self._span(
                trace_id=request_id,
                operation="provider.call",
                attributes={
                    "provider": routed_provider,
                    "model": selected_model,
                    "streaming": False,
                },
            ):
                try:
                    if self._provider_registry and self._settings.provider_fallback_enabled:
                        routing_result = await route_with_fallback(
                            self._provider_registry,
                            self._settings.provider_name,
                            selected_model,
                            messages,
                            max_tokens,
                            allowed_provider_names=allowed_provider_names,
                        )
                        provider_result = routing_result.result
                        routed_provider = routing_result.provider_name
                        provider_attempts = routing_result.attempts
                        fallback_chain = routing_result.fallback_chain
                    else:
                        self._validate_direct_provider_constraints(allowed_provider_names)
                        provider_result = await self._provider.chat(
                            selected_model, messages, max_tokens
                        )
                except ProviderError as exc:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.PROVIDER_ERROR,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "provider": routed_provider,
                            "model": selected_model,
                            "status_code": exc.status_code,
                            "code": exc.code,
                        },
                        webhook_events=webhook_events,
                    )
                    raise self._app_error_from_provider_error(exc) from exc

            response = ChatCompletionResponse.model_validate(provider_result)
            provider_response_hash = self._hash_value(provider_result)

            output_redaction_count = 0
            if self._settings.redaction_enabled and classification in {"phi", "pii"}:
                with self._span(
                    trace_id=request_id,
                    operation="redaction.scan",
                    attributes={"direction": "response"},
                ):
                    for choice in response.choices:
                        result = self._redaction_engine.redact_text(choice.message.content)
                        if result.redaction_count > 0:
                            choice.message.content = result.text
                            output_redaction_count += result.redaction_count
            redaction_count = input_redaction_count + output_redaction_count

            if citations and response.choices:
                response.choices[0].message.citations = citations

            policy_decision_label = self._policy_decision_label(decision)
            tokens_in = response.usage.prompt_tokens
            tokens_out = response.usage.completion_tokens
            cost_usd = round((tokens_in + tokens_out) * 0.000001, 8)

            budget_summary = self._record_budget_usage(
                tenant_id=tenant_id,
                used_tokens=tokens_in + tokens_out,
                current_summary=budget_summary,
            )

            if provider_attempts > 1:
                self._queue_webhook_event(
                    event_type=WebhookEventType.PROVIDER_FALLBACK,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "provider_attempts": provider_attempts,
                        "fallback_chain": fallback_chain,
                    },
                    webhook_events=webhook_events,
                )
            if redaction_count > 0:
                self._queue_webhook_event(
                    event_type=WebhookEventType.REDACTION_HIT,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "input_redaction_count": input_redaction_count,
                        "output_redaction_count": output_redaction_count,
                        "redaction_count": redaction_count,
                    },
                    webhook_events=webhook_events,
                )

            audit_event = self._build_audit_event(
                request_id=request_id,
                tenant_id=tenant_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=payload.model,
                selected_model=selected_model,
                provider=routed_provider,
                decision=decision,
                policy_decision_label=policy_decision_label,
                redaction_count=redaction_count,
                request_payload_hash=request_payload_hash,
                redacted_payload_hash=redacted_payload_hash,
                provider_request_hash=provider_request_hash,
                provider_response_hash=provider_response_hash,
                retrieval_citations=citations,
                streaming=False,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                provider_attempts=provider_attempts,
                fallback_chain=fallback_chain,
                trace_id=request_id,
                budget=budget_summary,
                webhook_events=webhook_events,
                input_redaction_count=input_redaction_count,
                output_redaction_count=output_redaction_count,
            )

            with self._span(
                trace_id=request_id,
                operation="audit.persist",
                attributes={"streaming": False, "provider": routed_provider},
            ):
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
                    "input_redaction_count": input_redaction_count,
                    "output_redaction_count": output_redaction_count,
                    "provider": routed_provider,
                    "latency_ms": latency_ms,
                    "token_in": tokens_in,
                    "token_out": tokens_out,
                    "cost_usd": cost_usd,
                    "provider_attempts": provider_attempts,
                    "fallback_chain": fallback_chain,
                    "budget_used": budget_summary.get("used") if budget_summary else None,
                    "budget_remaining": budget_summary.get("remaining")
                    if budget_summary
                    else None,
                },
            )
            if self._settings.metrics_enabled:
                record_request(
                    endpoint=endpoint,
                    provider=routed_provider,
                    model=selected_model,
                    policy_decision=policy_decision_label,
                    status_code=200,
                    latency_s=latency_ms / 1000.0,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    redaction_count=redaction_count,
                    provider_attempts=provider_attempts,
                )
            return response

    async def handle_chat_stream(
        self, request: Request, payload: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification
        endpoint = str(request.url.path)
        webhook_events: list[dict[str, object]] = []
        budget_summary: dict[str, object] | None = None
        request_payload_hash = self._hash_value(payload.model_dump(exclude_none=True))

        with self._span(
            trace_id=request_id,
            operation="gateway.request",
            attributes={
                "endpoint": endpoint,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
                "streaming": True,
            },
        ):
            rag_requested = bool(
                self._settings.rag_enabled and payload.rag and payload.rag.enabled
            )
            requested_connector = payload.rag.connector if rag_requested and payload.rag else ""

            policy_input = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "requested_model": payload.model,
                "classification": classification,
                "estimated_tokens": sum(len(msg.content.split()) for msg in payload.messages),
                "connector_targets": [requested_connector] if rag_requested else [],
                "request_metadata": {
                    "request_id": request_id,
                },
            }

            with self._span(
                trace_id=request_id,
                operation="policy.evaluate",
                attributes={"endpoint": endpoint, "model": payload.model, "streaming": True},
            ):
                decision = self._resolve_policy_decision(policy_input, request_id=request_id)

            if not decision.allow and self._settings.opa_mode == "enforce":
                reason = decision.deny_reason or "policy_denied"
                self._queue_webhook_event(
                    event_type=WebhookEventType.POLICY_DENIED,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "endpoint": endpoint,
                        "requested_model": payload.model,
                        "deny_reason": reason,
                    },
                    webhook_events=webhook_events,
                )
                self._write_policy_deny_audit(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    endpoint=endpoint,
                    requested_model=payload.model,
                    decision=decision,
                    reason=reason,
                    request_payload_hash=request_payload_hash,
                    streaming=True,
                    trace_id=request_id,
                    webhook_events=webhook_events,
                )
                raise AppError(403, "policy_denied", "policy", reason)

            transformed_request = apply_transforms(payload.model_dump(), decision.transforms)
            messages: list[dict[str, str]] = transformed_request["messages"]

            citations: list[Citation] | None = None
            if rag_requested and payload.rag:
                with self._span(
                    trace_id=request_id,
                    operation="rag.retrieve",
                    attributes={
                        "connector": payload.rag.connector,
                        "top_k": payload.rag.top_k,
                    },
                ):
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

            input_redaction_count = 0
            if self._settings.redaction_enabled and classification in {"phi", "pii"}:
                with self._span(
                    trace_id=request_id,
                    operation="redaction.scan",
                    attributes={"direction": "request", "streaming": True},
                ):
                    redaction_result = self._redaction_engine.redact_messages(messages)
                    messages = redaction_result.messages
                    input_redaction_count = redaction_result.redaction_count
            redacted_payload_hash = self._hash_value(messages)

            selected_model = str(transformed_request.get("model", payload.model))
            self._validate_model_constraints(decision, selected_model)
            max_tokens = transformed_request.get("max_tokens")
            allowed_provider_names = self._allowed_providers(decision)
            requested_budget_tokens = self._estimate_requested_tokens(messages, max_tokens)
            budget_summary = self._enforce_budget_or_deny(
                tenant_id=tenant_id,
                requested_tokens=requested_budget_tokens,
                request_id=request_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=payload.model,
                selected_model=selected_model,
                decision=decision,
                request_payload_hash=request_payload_hash,
                streaming=True,
                webhook_events=webhook_events,
            )

            provider_request_hash = self._hash_value(
                {
                    "model": selected_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
            )

            routed_provider = self._settings.provider_name
            provider_attempts = 1
            fallback_chain: list[str] = [routed_provider]
            first_chunk: dict[str, object] | None = None
            with self._span(
                trace_id=request_id,
                operation="provider.call",
                attributes={
                    "provider": routed_provider,
                    "model": selected_model,
                    "streaming": True,
                },
            ):
                try:
                    if self._provider_registry and self._settings.provider_fallback_enabled:
                        routing_result = await route_stream_with_fallback(
                            self._provider_registry,
                            self._settings.provider_name,
                            selected_model,
                            messages,
                            max_tokens,
                            allowed_provider_names=allowed_provider_names,
                        )
                        provider_stream = routing_result.stream
                        first_chunk = routing_result.first_chunk
                        routed_provider = routing_result.provider_name
                        provider_attempts = routing_result.attempts
                        fallback_chain = routing_result.fallback_chain
                    else:
                        self._validate_direct_provider_constraints(allowed_provider_names)
                        provider_stream = self._provider.chat_stream(
                            selected_model, messages, max_tokens
                        )
                        try:
                            first_chunk = await anext(provider_stream)
                        except StopAsyncIteration:
                            first_chunk = None
                except ProviderError as exc:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.PROVIDER_ERROR,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "provider": routed_provider,
                            "model": selected_model,
                            "status_code": exc.status_code,
                            "code": exc.code,
                            "streaming": True,
                        },
                        webhook_events=webhook_events,
                    )
                    raise self._app_error_from_provider_error(exc) from exc

        async def event_stream() -> AsyncIterator[str]:
            nonlocal budget_summary
            completion_parts: list[str] = []
            usage_prompt_tokens = max(sum(len(item["content"].split()) for item in messages), 1)
            usage_completion_tokens = 0
            output_redaction_count = 0
            saw_finish = False
            saw_citations = False
            chunk_id = ""
            chunk_created = int(datetime.now(UTC).timestamp())
            policy_decision_label = self._policy_decision_label(decision)
            stream_error: BaseException | None = None
            stream_status_code = 200

            try:
                if first_chunk is not None:
                    chunk_id = str(first_chunk.get("id", f"chatcmpl-{uuid4().hex}"))
                    chunk_created = self._coerce_int(first_chunk.get("created"), chunk_created)
                    choices = first_chunk.get("choices")
                    if isinstance(choices, list):
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            delta = choice.get("delta", {})
                            if isinstance(delta, dict):
                                content = delta.get("content")
                                if isinstance(content, str) and content:
                                    if (
                                        self._settings.redaction_enabled
                                        and classification in {"phi", "pii"}
                                    ):
                                        redaction_result = self._redaction_engine.redact_text(
                                            content
                                        )
                                        if redaction_result.redaction_count > 0:
                                            output_redaction_count += (
                                                redaction_result.redaction_count
                                            )
                                            content = redaction_result.text
                                            delta["content"] = content
                                    completion_parts.append(content)
                                if "citations" in delta:
                                    saw_citations = True
                            finish_reason = choice.get("finish_reason")
                            if isinstance(finish_reason, str) and finish_reason:
                                saw_finish = True
                    usage = first_chunk.get("usage")
                    if isinstance(usage, dict):
                        prompt_raw = usage.get("prompt_tokens")
                        completion_raw = usage.get("completion_tokens")
                        if isinstance(prompt_raw, int):
                            usage_prompt_tokens = prompt_raw
                        if isinstance(completion_raw, int):
                            usage_completion_tokens = completion_raw
                    yield self._sse_event(first_chunk)

                async for chunk in provider_stream:
                    if chunk_id == "":
                        chunk_id = str(chunk.get("id", f"chatcmpl-{uuid4().hex}"))
                    chunk_created = self._coerce_int(chunk.get("created"), chunk_created)

                    choices = chunk.get("choices")
                    if isinstance(choices, list):
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            delta = choice.get("delta", {})
                            if isinstance(delta, dict):
                                content = delta.get("content")
                                if isinstance(content, str) and content:
                                    if (
                                        self._settings.redaction_enabled
                                        and classification in {"phi", "pii"}
                                    ):
                                        redaction_result = self._redaction_engine.redact_text(
                                            content
                                        )
                                        if redaction_result.redaction_count > 0:
                                            output_redaction_count += (
                                                redaction_result.redaction_count
                                            )
                                            content = redaction_result.text
                                            delta["content"] = content
                                    completion_parts.append(content)
                                if "citations" in delta:
                                    saw_citations = True
                            finish_reason = choice.get("finish_reason")
                            if isinstance(finish_reason, str) and finish_reason:
                                saw_finish = True

                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        prompt_raw = usage.get("prompt_tokens")
                        completion_raw = usage.get("completion_tokens")
                        if isinstance(prompt_raw, int):
                            usage_prompt_tokens = prompt_raw
                        if isinstance(completion_raw, int):
                            usage_completion_tokens = completion_raw

                    yield self._sse_event(chunk)

                if citations and not saw_citations:
                    yield self._sse_event(
                        {
                            "id": chunk_id or f"chatcmpl-{uuid4().hex}",
                            "object": "chat.completion.chunk",
                            "created": chunk_created,
                            "model": selected_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "citations": [
                                            citation.model_dump() for citation in citations
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )

                if not saw_finish:
                    yield self._sse_event(
                        {
                            "id": chunk_id or f"chatcmpl-{uuid4().hex}",
                            "object": "chat.completion.chunk",
                            "created": chunk_created,
                            "model": selected_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                    )

                yield "data: [DONE]\n\n"

            except BaseException as exc:
                stream_error = exc
                stream_status_code = 499
                raise
            finally:
                if usage_completion_tokens == 0:
                    usage_completion_tokens = len("".join(completion_parts).split())
                redaction_count = input_redaction_count + output_redaction_count
                provider_response_hash = self._hash_value(
                    {
                        "completion_text": "".join(completion_parts),
                        "prompt_tokens": usage_prompt_tokens,
                        "completion_tokens": usage_completion_tokens,
                        "chunk_id": chunk_id,
                        "model": selected_model,
                    }
                )

                cost_usd = round(
                    (usage_prompt_tokens + usage_completion_tokens) * 0.000001, 8
                )
                budget_summary = self._record_budget_usage(
                    tenant_id=tenant_id,
                    used_tokens=usage_prompt_tokens + usage_completion_tokens,
                    current_summary=budget_summary,
                )
                if provider_attempts > 1:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.PROVIDER_FALLBACK,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "provider_attempts": provider_attempts,
                            "fallback_chain": fallback_chain,
                            "streaming": True,
                        },
                        webhook_events=webhook_events,
                    )
                if redaction_count > 0:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.REDACTION_HIT,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "input_redaction_count": input_redaction_count,
                            "output_redaction_count": output_redaction_count,
                            "redaction_count": redaction_count,
                            "streaming": True,
                        },
                        webhook_events=webhook_events,
                    )
                if stream_error is not None:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.PROVIDER_ERROR,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "provider": routed_provider,
                            "model": selected_model,
                            "streaming": True,
                            "error": type(stream_error).__name__,
                        },
                        webhook_events=webhook_events,
                    )
                audit_event = self._build_audit_event(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    endpoint=endpoint,
                    requested_model=payload.model,
                    selected_model=selected_model,
                    provider=routed_provider,
                    decision=decision,
                    policy_decision_label=policy_decision_label,
                    redaction_count=redaction_count,
                    request_payload_hash=request_payload_hash,
                    redacted_payload_hash=redacted_payload_hash,
                    provider_request_hash=provider_request_hash,
                    provider_response_hash=provider_response_hash,
                    retrieval_citations=citations,
                    streaming=True,
                    tokens_in=usage_prompt_tokens,
                    tokens_out=usage_completion_tokens,
                    cost_usd=cost_usd,
                    provider_attempts=provider_attempts,
                    fallback_chain=fallback_chain,
                    trace_id=request_id,
                    budget=budget_summary,
                    webhook_events=webhook_events,
                    input_redaction_count=input_redaction_count,
                    output_redaction_count=output_redaction_count,
                )
                if stream_error is not None:
                    audit_event["stream_error"] = type(stream_error).__name__
                with self._span(
                    trace_id=request_id,
                    operation="audit.persist",
                    attributes={"streaming": True, "provider": routed_provider},
                ):
                    try:
                        self._audit_writer.write_event(audit_event)
                    except AuditValidationError as exc:
                        logger.warning(
                            "audit_write_failed_stream",
                            extra={
                                "request_id": request_id,
                                "provider": routed_provider,
                                "error": str(exc),
                            },
                        )

                latency_ms = int((perf_counter() - started) * 1000)
                logger.info(
                    "chat_stream_completed",
                    extra={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "model": selected_model,
                        "policy_decision": policy_decision_label,
                        "redaction_count": redaction_count,
                        "input_redaction_count": input_redaction_count,
                        "output_redaction_count": output_redaction_count,
                        "provider": routed_provider,
                        "latency_ms": latency_ms,
                        "token_in": usage_prompt_tokens,
                        "token_out": usage_completion_tokens,
                        "cost_usd": cost_usd,
                        "provider_attempts": provider_attempts,
                        "fallback_chain": fallback_chain,
                        "budget_used": budget_summary.get("used") if budget_summary else None,
                        "budget_remaining": budget_summary.get("remaining")
                        if budget_summary
                        else None,
                        "stream_error": type(stream_error).__name__
                        if stream_error
                        else None,
                    },
                )
                if self._settings.metrics_enabled:
                    record_request(
                        endpoint=endpoint,
                        provider=routed_provider,
                        model=selected_model,
                        policy_decision=policy_decision_label,
                        status_code=stream_status_code,
                        latency_s=latency_ms / 1000.0,
                        tokens_in=usage_prompt_tokens,
                        tokens_out=usage_completion_tokens,
                        cost_usd=cost_usd,
                        redaction_count=redaction_count,
                        provider_attempts=provider_attempts,
                    )

        return event_stream()

    async def handle_embeddings(
        self, request: Request, payload: EmbeddingsRequest
    ) -> EmbeddingsResponse:
        started = perf_counter()
        request_id = request.state.request_id
        tenant_id = request.state.tenant_id
        user_id = request.state.user_id
        classification = request.state.classification
        endpoint = str(request.url.path)
        webhook_events: list[dict[str, object]] = []
        budget_summary: dict[str, object] | None = None
        request_payload_hash = self._hash_value(payload.model_dump(exclude_none=True))

        raw_inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        if not raw_inputs:
            raise AppError(422, "request_validation_failed", "validation", "Input cannot be empty")

        with self._span(
            trace_id=request_id,
            operation="gateway.request",
            attributes={
                "endpoint": endpoint,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
            },
        ):
            policy_input = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "requested_model": payload.model,
                "classification": classification,
                "estimated_tokens": sum(len(item.split()) for item in raw_inputs),
                "connector_targets": [],
                "request_metadata": {"request_id": request_id},
            }

            with self._span(
                trace_id=request_id,
                operation="policy.evaluate",
                attributes={"endpoint": endpoint, "model": payload.model},
            ):
                decision = self._resolve_policy_decision(policy_input, request_id=request_id)

            if not decision.allow and self._settings.opa_mode == "enforce":
                reason = decision.deny_reason or "policy_denied"
                self._queue_webhook_event(
                    event_type=WebhookEventType.POLICY_DENIED,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "endpoint": endpoint,
                        "requested_model": payload.model,
                        "deny_reason": reason,
                    },
                    webhook_events=webhook_events,
                )
                self._write_policy_deny_audit(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    endpoint=endpoint,
                    requested_model=payload.model,
                    decision=decision,
                    reason=reason,
                    request_payload_hash=request_payload_hash,
                    streaming=False,
                    trace_id=request_id,
                    webhook_events=webhook_events,
                )
                raise AppError(403, "policy_denied", "policy", reason)

            selected_model = payload.model
            for transform in decision.transforms:
                if transform.type == "override_model":
                    selected_model = str(transform.args.get("model", selected_model))
            self._validate_model_constraints(decision, selected_model)
            allowed_provider_names = self._allowed_providers(decision)

            inputs = list(raw_inputs)
            input_redaction_count = 0
            if self._settings.redaction_enabled and classification in {"phi", "pii"}:
                with self._span(
                    trace_id=request_id,
                    operation="redaction.scan",
                    attributes={"direction": "request", "operation_type": "embeddings"},
                ):
                    redaction_result = self._redaction_engine.redact_messages(
                        [{"role": "user", "content": text} for text in inputs]
                    )
                    inputs = [item["content"] for item in redaction_result.messages]
                    input_redaction_count = redaction_result.redaction_count
            redaction_count = input_redaction_count
            redacted_payload_hash = self._hash_value(inputs)

            requested_budget_tokens = max(sum(len(item.split()) for item in inputs), 1)
            budget_summary = self._enforce_budget_or_deny(
                tenant_id=tenant_id,
                requested_tokens=requested_budget_tokens,
                request_id=request_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=payload.model,
                selected_model=selected_model,
                decision=decision,
                request_payload_hash=request_payload_hash,
                streaming=False,
                webhook_events=webhook_events,
            )

            routed_provider = self._settings.provider_name
            provider_attempts = 1
            fallback_chain: list[str] = [routed_provider]
            provider_request_hash = self._hash_value(
                {
                    "model": selected_model,
                    "inputs": inputs,
                }
            )

            with self._span(
                trace_id=request_id,
                operation="provider.call",
                attributes={
                    "provider": routed_provider,
                    "model": selected_model,
                    "operation_type": "embeddings",
                },
            ):
                try:
                    if self._provider_registry and self._settings.provider_fallback_enabled:
                        routing_result = await route_embeddings_with_fallback(
                            self._provider_registry,
                            self._settings.provider_name,
                            selected_model,
                            inputs,
                            allowed_provider_names=allowed_provider_names,
                        )
                        provider_result = routing_result.result
                        routed_provider = routing_result.provider_name
                        provider_attempts = routing_result.attempts
                        fallback_chain = routing_result.fallback_chain
                    else:
                        self._validate_direct_provider_constraints(allowed_provider_names)
                        provider_result = await self._provider.embeddings(selected_model, inputs)
                except ProviderError as exc:
                    self._queue_webhook_event(
                        event_type=WebhookEventType.PROVIDER_ERROR,
                        payload={
                            "request_id": request_id,
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "provider": routed_provider,
                            "model": selected_model,
                            "status_code": exc.status_code,
                            "code": exc.code,
                            "operation_type": "embeddings",
                        },
                        webhook_events=webhook_events,
                    )
                    raise self._app_error_from_provider_error(exc) from exc

            response = EmbeddingsResponse.model_validate(provider_result)
            provider_response_hash = self._hash_value(provider_result)

            tokens_in = response.usage.prompt_tokens
            tokens_out = 0
            cost_usd = round(tokens_in * 0.0000002, 8)
            policy_decision_label = self._policy_decision_label(decision)

            budget_summary = self._record_budget_usage(
                tenant_id=tenant_id,
                used_tokens=tokens_in,
                current_summary=budget_summary,
            )

            if provider_attempts > 1:
                self._queue_webhook_event(
                    event_type=WebhookEventType.PROVIDER_FALLBACK,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "provider_attempts": provider_attempts,
                        "fallback_chain": fallback_chain,
                        "operation_type": "embeddings",
                    },
                    webhook_events=webhook_events,
                )
            if redaction_count > 0:
                self._queue_webhook_event(
                    event_type=WebhookEventType.REDACTION_HIT,
                    payload={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "input_redaction_count": input_redaction_count,
                        "output_redaction_count": 0,
                        "redaction_count": redaction_count,
                        "operation_type": "embeddings",
                    },
                    webhook_events=webhook_events,
                )

            audit_event = self._build_audit_event(
                request_id=request_id,
                tenant_id=tenant_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=payload.model,
                selected_model=selected_model,
                provider=routed_provider,
                decision=decision,
                policy_decision_label=policy_decision_label,
                redaction_count=redaction_count,
                request_payload_hash=request_payload_hash,
                redacted_payload_hash=redacted_payload_hash,
                provider_request_hash=provider_request_hash,
                provider_response_hash=provider_response_hash,
                retrieval_citations=[],
                streaming=False,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                provider_attempts=provider_attempts,
                fallback_chain=fallback_chain,
                trace_id=request_id,
                budget=budget_summary,
                webhook_events=webhook_events,
                input_redaction_count=input_redaction_count,
                output_redaction_count=0,
            )

            with self._span(
                trace_id=request_id,
                operation="audit.persist",
                attributes={"streaming": False, "provider": routed_provider},
            ):
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
                    "provider": routed_provider,
                    "latency_ms": latency_ms,
                    "token_in": tokens_in,
                    "token_out": tokens_out,
                    "cost_usd": cost_usd,
                    "budget_used": budget_summary.get("used") if budget_summary else None,
                    "budget_remaining": budget_summary.get("remaining")
                    if budget_summary
                    else None,
                },
            )
            if self._settings.metrics_enabled:
                record_request(
                    endpoint=endpoint,
                    provider=routed_provider,
                    model=selected_model,
                    policy_decision=policy_decision_label,
                    status_code=200,
                    latency_s=latency_ms / 1000.0,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    redaction_count=redaction_count,
                    provider_attempts=provider_attempts,
                )
            return response

    def readiness(self) -> dict[str, str]:
        policy_schema = self._settings.contracts_dir / "policy-decision.schema.json"
        audit_schema = self._settings.contracts_dir / "audit-event.schema.json"
        providers_status = "ok"
        if self._provider_registry:
            providers_status = (
                "ok" if self._provider_registry.list_providers() else "no_providers"
            )
        return {
            "policy_schema": "ok" if policy_schema.exists() else "missing",
            "audit_schema": "ok" if audit_schema.exists() else "missing",
            "provider": providers_status,
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

    def get_trace(self, request_id: str) -> dict[str, object]:
        if self._span_collector is None:
            raise AppError(
                503,
                "tracing_disabled",
                "provider",
                "Tracing is not enabled",
            )
        return {
            "trace_id": request_id,
            "spans": self._span_collector.get_trace(request_id),
        }

    @staticmethod
    def request_fingerprint(messages: list[dict[str, str]]) -> str:
        serialized = "|".join(f"{m['role']}:{m['content']}" for m in messages)
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _app_error_from_provider_error(exc: ProviderError) -> AppError:
        if exc.status_code in {429, 501, 502, 503}:
            return AppError(exc.status_code, exc.code, exc.error_type, exc.message)
        return AppError(502, "provider_upstream_error", "provider", exc.message)

    def _span(
        self,
        trace_id: str,
        operation: str,
        attributes: dict[str, object] | None = None,
    ) -> Any:
        if self._span_collector is None:
            return _NoopSpan()
        return self._span_collector.span(
            trace_id=trace_id,
            operation=operation,
            attributes=attributes,
        )

    @staticmethod
    def _estimate_requested_tokens(
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> int:
        prompt_estimate = max(sum(len(item["content"].split()) for item in messages), 1)
        completion_estimate = max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else 0
        return prompt_estimate + completion_estimate

    def _enforce_budget_or_deny(
        self,
        tenant_id: str,
        requested_tokens: int,
        request_id: str,
        user_id: str,
        endpoint: str,
        requested_model: str,
        selected_model: str,
        decision: PolicyDecision,
        request_payload_hash: str,
        streaming: bool,
        webhook_events: list[dict[str, object]],
    ) -> dict[str, object] | None:
        if self._budget_tracker is None:
            return None

        try:
            self._budget_tracker.check(tenant_id, requested_tokens)
        except BudgetBackendError as exc:
            raise AppError(
                503,
                "budget_backend_unavailable",
                "policy",
                "Budget backend unavailable",
            ) from exc
        except BudgetExceededError as exc:
            try:
                budget_summary = self._budget_tracker.summary(tenant_id)
            except BudgetBackendError:
                budget_summary = {
                    "tenant_id": tenant_id,
                    "window_seconds": exc.window_seconds,
                    "ceiling": exc.ceiling,
                    "used": exc.used,
                    "remaining": max(0, exc.ceiling - exc.used),
                    "utilization_pct": round(exc.used / exc.ceiling * 100, 2)
                    if exc.ceiling > 0
                    else 0.0,
                }
            self._queue_webhook_event(
                event_type=WebhookEventType.BUDGET_EXCEEDED,
                payload={
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "endpoint": endpoint,
                    "requested_model": requested_model,
                    "selected_model": selected_model,
                    "requested_tokens": requested_tokens,
                    "used": exc.used,
                    "ceiling": exc.ceiling,
                    "window_seconds": exc.window_seconds,
                },
                webhook_events=webhook_events,
            )
            self._write_budget_deny_audit(
                request_id=request_id,
                tenant_id=tenant_id,
                user_id=user_id,
                endpoint=endpoint,
                requested_model=requested_model,
                selected_model=selected_model,
                decision=decision,
                request_payload_hash=request_payload_hash,
                streaming=streaming,
                budget=budget_summary,
                trace_id=request_id,
                webhook_events=webhook_events,
            )
            raise AppError(
                429,
                "budget_exceeded",
                "policy",
                (
                    f"Token budget exceeded for tenant {tenant_id}: "
                    f"{exc.used}/{exc.ceiling} in {exc.window_seconds}s window"
                ),
            ) from exc

        try:
            return self._budget_tracker.summary(tenant_id)
        except BudgetBackendError as exc:
            raise AppError(
                503,
                "budget_backend_unavailable",
                "policy",
                "Budget backend unavailable",
            ) from exc

    def _record_budget_usage(
        self,
        tenant_id: str,
        used_tokens: int,
        current_summary: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if self._budget_tracker is None:
            return current_summary
        try:
            self._budget_tracker.record(tenant_id, used_tokens)
            return self._budget_tracker.summary(tenant_id)
        except BudgetBackendError as exc:
            logger.warning(
                "budget_usage_record_failed",
                extra={
                    "tenant_id": tenant_id,
                    "used_tokens": used_tokens,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            return current_summary

    def _queue_webhook_event(
        self,
        event_type: WebhookEventType,
        payload: dict[str, object],
        webhook_events: list[dict[str, object]] | None = None,
    ) -> None:
        if self._webhook_dispatcher is None:
            return
        dispatcher = self._webhook_dispatcher
        if not dispatcher.should_fire(event_type):
            return

        summary: dict[str, object] = {
            "event_type": event_type.value,
            "delivery_success_count": None,
        }
        if webhook_events is not None:
            webhook_events.append(summary)

        async def _dispatch() -> None:
            try:
                results = await dispatcher.dispatch(event_type, payload)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning(
                    "webhook_dispatch_failed",
                    extra={
                        "event_type": event_type.value,
                        "error": str(exc),
                    },
                )
                return
            summary["delivery_success_count"] = sum(1 for result in results if result.success)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "webhook_dispatch_skipped",
                extra={"event_type": event_type.value, "reason": "no_running_loop"},
            )
            return
        loop.create_task(_dispatch())

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
        if not decision.allow:
            return "deny"
        if self._settings.opa_mode == "observe" and decision.deny_reason:
            return "observe"
        if decision.transforms:
            return "transform"
        return "allow"

    @staticmethod
    def _allowed_providers(decision: PolicyDecision) -> set[str] | None:
        constraints = decision.provider_constraints
        if not isinstance(constraints, dict):
            return None

        raw_allowed = constraints.get("allowed_providers")
        if not isinstance(raw_allowed, list):
            return None
        return {str(item) for item in raw_allowed if str(item).strip()}

    @staticmethod
    def _allowed_models(decision: PolicyDecision) -> set[str] | None:
        constraints = decision.provider_constraints
        if not isinstance(constraints, dict):
            return None

        raw_allowed = constraints.get("allowed_models")
        if not isinstance(raw_allowed, list):
            return None
        return {str(item) for item in raw_allowed if str(item).strip()}

    def _validate_direct_provider_constraints(
        self, allowed_provider_names: set[str] | None
    ) -> None:
        if allowed_provider_names is None:
            return
        if self._settings.provider_name in allowed_provider_names:
            return
        raise AppError(
            403,
            "provider_forbidden",
            "policy",
            f"Provider not allowed by policy: {self._settings.provider_name}",
        )

    def _validate_model_constraints(self, decision: PolicyDecision, model: str) -> None:
        allowed_models = self._allowed_models(decision)
        if allowed_models is None:
            return
        if model in allowed_models:
            return
        raise AppError(
            403,
            "model_forbidden",
            "policy",
            f"Model not allowed by policy: {model}",
        )

    def _build_audit_event(
        self,
        request_id: str,
        tenant_id: str,
        user_id: str,
        endpoint: str,
        requested_model: str,
        selected_model: str,
        provider: str,
        decision: PolicyDecision,
        policy_decision_label: str,
        redaction_count: int,
        request_payload_hash: str,
        redacted_payload_hash: str,
        provider_request_hash: str | None,
        provider_response_hash: str | None,
        retrieval_citations: list[Citation] | None,
        streaming: bool,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        provider_attempts: int,
        fallback_chain: list[str],
        trace_id: str | None = None,
        budget: dict[str, object] | None = None,
        webhook_events: list[dict[str, object]] | None = None,
        input_redaction_count: int | None = None,
        output_redaction_count: int | None = None,
    ) -> dict[str, object]:
        event: dict[str, object] = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "endpoint": endpoint,
            "requested_model": requested_model,
            "selected_model": selected_model,
            "provider": provider,
            "policy_decision": policy_decision_label,
            "policy_decision_id": decision.decision_id,
            "policy_evaluated_at": decision.evaluated_at,
            "policy_allow": decision.allow,
            "policy_mode": self._settings.opa_mode,
            "transforms_applied": [action.type for action in decision.transforms],
            "redaction_count": redaction_count,
            "request_payload_hash": request_payload_hash,
            "redacted_payload_hash": redacted_payload_hash,
            "provider_request_hash": provider_request_hash,
            "provider_response_hash": provider_response_hash,
            "retrieval_citations": [
                citation.model_dump() if isinstance(citation, Citation) else citation
                for citation in (retrieval_citations or [])
            ],
            "streaming": streaming,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "policy_hash": decision.policy_hash,
            "provider_attempts": provider_attempts,
            "fallback_chain": fallback_chain,
        }
        if trace_id is not None:
            event["trace_id"] = trace_id
        if budget is not None:
            event["budget"] = budget
        if webhook_events:
            event["webhook_events"] = webhook_events
        if input_redaction_count is not None:
            event["input_redaction_count"] = input_redaction_count
        if output_redaction_count is not None:
            event["output_redaction_count"] = output_redaction_count
        if decision.deny_reason is not None:
            event["deny_reason"] = decision.deny_reason
        if decision.provider_constraints is not None:
            event["provider_constraints"] = decision.provider_constraints
        if decision.connector_constraints is not None:
            event["connector_constraints"] = {
                "allowed_connectors": decision.connector_constraints.allowed_connectors
            }
        return event

    def _write_policy_deny_audit(
        self,
        request_id: str,
        tenant_id: str,
        user_id: str,
        endpoint: str,
        requested_model: str,
        decision: PolicyDecision,
        reason: str,
        request_payload_hash: str,
        streaming: bool,
        trace_id: str | None = None,
        budget: dict[str, object] | None = None,
        webhook_events: list[dict[str, object]] | None = None,
    ) -> None:
        event = self._build_audit_event(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint,
            requested_model=requested_model,
            selected_model=requested_model,
            provider="policy-gate",
            decision=decision,
            policy_decision_label="deny",
            redaction_count=0,
            request_payload_hash=request_payload_hash,
            redacted_payload_hash=request_payload_hash,
            provider_request_hash=None,
            provider_response_hash=None,
            retrieval_citations=[],
            streaming=streaming,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            provider_attempts=1,
            fallback_chain=[],
            trace_id=trace_id,
            budget=budget,
            webhook_events=webhook_events,
        )
        event["deny_reason"] = reason
        try:
            self._audit_writer.write_event(event)
        except AuditValidationError as exc:
            logger.warning(
                "audit_write_failed_policy_deny",
                extra={
                    "request_id": request_id,
                    "reason": reason,
                    "error": str(exc),
                },
            )

    def _write_budget_deny_audit(
        self,
        request_id: str,
        tenant_id: str,
        user_id: str,
        endpoint: str,
        requested_model: str,
        selected_model: str,
        decision: PolicyDecision,
        request_payload_hash: str,
        streaming: bool,
        budget: dict[str, object],
        trace_id: str | None = None,
        webhook_events: list[dict[str, object]] | None = None,
    ) -> None:
        event = self._build_audit_event(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint,
            requested_model=requested_model,
            selected_model=selected_model,
            provider="budget-gate",
            decision=decision,
            policy_decision_label="deny",
            redaction_count=0,
            request_payload_hash=request_payload_hash,
            redacted_payload_hash=request_payload_hash,
            provider_request_hash=None,
            provider_response_hash=None,
            retrieval_citations=[],
            streaming=streaming,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            provider_attempts=1,
            fallback_chain=[],
            trace_id=trace_id,
            budget=budget,
            webhook_events=webhook_events,
        )
        event["deny_reason"] = "budget_exceeded"
        try:
            self._audit_writer.write_event(event)
        except AuditValidationError as exc:
            logger.warning(
                "audit_write_failed_budget_deny",
                extra={
                    "request_id": request_id,
                    "error": str(exc),
                },
            )

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

    @staticmethod
    def _coerce_int(value: object, default: int) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _hash_value(value: object) -> str:
        canonical = json_mod.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _sse_event(payload: dict[str, object]) -> str:
        return f"data: {json_mod.dumps(payload, separators=(',', ':'))}\n\n"
