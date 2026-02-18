import json as json_mod

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.audit.writer import AuditWriter
from app.config.settings import Settings, get_settings
from app.core.errors import AppError, app_error_response, request_id_from_request
from app.core.logging import configure_logging
from app.middleware.auth import AuthMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.policy.client import OPAClient
from app.providers.anthropic import AnthropicProvider
from app.providers.azure_openai import AzureOpenAIProvider
from app.providers.base import ChatProvider, ProviderCapabilities
from app.providers.http_openai import HTTPOpenAIProvider
from app.providers.registry import ProviderCost, ProviderEntry, ProviderRegistry
from app.providers.stub import StubProvider
from app.rag.connectors.filesystem import FilesystemConnector
from app.rag.connectors.postgres import PostgresPgvectorConnector
from app.rag.connectors.s3 import S3Connector
from app.rag.embeddings import (
    EmbeddingGenerator,
    HashEmbeddingGenerator,
    HTTPOpenAIEmbeddingGenerator,
)
from app.rag.registry import ConnectorRegistry
from app.rag.retrieval import RetrievalOrchestrator
from app.redaction.engine import RedactionEngine
from app.services.chat_service import ChatService


def _build_rag_embedding_generator(settings: Settings, embedding_dim: int) -> EmbeddingGenerator:
    source = settings.rag_embedding_source.strip().lower()
    if source == "hash":
        return HashEmbeddingGenerator(embedding_dim=embedding_dim)
    if source == "http":
        endpoint = settings.rag_embedding_endpoint
        if not endpoint:
            raise RuntimeError("SRG_RAG_EMBEDDING_ENDPOINT is required when source=http")
        return HTTPOpenAIEmbeddingGenerator(
            endpoint=endpoint,
            model=settings.rag_embedding_model,
            embedding_dim=embedding_dim,
            api_key=settings.rag_embedding_api_key,
            tenant_id=settings.rag_embedding_tenant_id,
            user_id=settings.rag_embedding_user_id,
            classification=settings.rag_embedding_classification,
        )
    raise RuntimeError(f"Unsupported SRG_RAG_EMBEDDING_SOURCE value: {source}")


def _build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    stub = StubProvider(embedding_dim=settings.rag_embedding_dim)

    registry.register(
        ProviderEntry(
            name="stub",
            provider=stub,
            cost=ProviderCost(input_per_token=0.000001, output_per_token=0.000001),
            capabilities=ProviderCapabilities(
                chat=True,
                embeddings=True,
                streaming=True,
            ),
            priority=100,
        )
    )

    if settings.provider_config:
        for entry in json_mod.loads(settings.provider_config):
            provider_type = str(entry.get("type", "openai_compatible")).strip().lower()
            raw_capabilities_cfg = entry.get("capabilities", {})
            capabilities_cfg = (
                raw_capabilities_cfg if isinstance(raw_capabilities_cfg, dict) else {}
            )
            model_prefixes = tuple(str(item) for item in capabilities_cfg.get("model_prefixes", []))
            provider: ChatProvider
            capabilities = ProviderCapabilities(
                chat=bool(capabilities_cfg.get("chat", True)),
                embeddings=bool(capabilities_cfg.get("embeddings", True)),
                streaming=bool(capabilities_cfg.get("streaming", True)),
                model_prefixes=model_prefixes,
            )
            if provider_type in {"openai_compatible", "openai"}:
                provider = HTTPOpenAIProvider(
                    base_url=entry["base_url"],
                    api_key=entry["api_key"],
                    timeout_s=entry.get("timeout_s", 30.0),
                )
                if "capabilities" not in entry:
                    capabilities = ProviderCapabilities(
                        chat=True,
                        embeddings=True,
                        streaming=True,
                        model_prefixes=model_prefixes,
                    )
            elif provider_type == "azure_openai":
                provider = AzureOpenAIProvider(
                    endpoint=entry["endpoint"],
                    api_key=entry["api_key"],
                    api_version=entry.get("api_version", "2024-10-21"),
                    timeout_s=entry.get("timeout_s", 30.0),
                )
                if "capabilities" not in entry:
                    capabilities = ProviderCapabilities(
                        chat=True,
                        embeddings=True,
                        streaming=True,
                        model_prefixes=model_prefixes,
                    )
            elif provider_type == "anthropic":
                provider = AnthropicProvider(
                    api_key=entry["api_key"],
                    base_url=entry.get("base_url", "https://api.anthropic.com"),
                    anthropic_version=entry.get("anthropic_version", "2023-06-01"),
                    timeout_s=entry.get("timeout_s", 30.0),
                )
                if "capabilities" not in entry:
                    capabilities = ProviderCapabilities(
                        chat=True,
                        embeddings=False,
                        streaming=False,
                        model_prefixes=model_prefixes,
                    )
            else:
                raise RuntimeError(
                    f"Unsupported provider type in SRG_PROVIDER_CONFIG: {provider_type}"
                )
            cost_cfg = entry.get("cost", {})
            registry.register(
                ProviderEntry(
                    name=entry["name"],
                    provider=provider,
                    cost=ProviderCost(
                        input_per_token=cost_cfg.get("input_per_token", 0.0),
                        output_per_token=cost_cfg.get("output_per_token", 0.0),
                    ),
                    capabilities=capabilities,
                    priority=entry.get("priority", 50),
                    enabled=entry.get("enabled", True),
                )
            )

    return registry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Sovereign RAG Gateway", version="0.3.0-rc1")

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AuthMiddleware)

    connector_registry = ConnectorRegistry()
    connector_registry.register(
        "filesystem",
        FilesystemConnector(index_path=settings.rag_filesystem_index_path),
    )
    if settings.rag_postgres_dsn:
        embedding_generator = _build_rag_embedding_generator(
            settings=settings,
            embedding_dim=settings.rag_embedding_dim,
        )
        connector_registry.register(
            "postgres",
            PostgresPgvectorConnector(
                dsn=settings.rag_postgres_dsn,
                table=settings.rag_postgres_table,
                embedding_dim=settings.rag_embedding_dim,
                embedding_generator=embedding_generator,
            ),
        )
    if settings.rag_s3_bucket:
        connector_registry.register(
            "s3",
            S3Connector(
                bucket=settings.rag_s3_bucket,
                index_key=settings.rag_s3_index_key,
                region=settings.rag_s3_region,
                endpoint_url=settings.rag_s3_endpoint_url,
            ),
        )

    provider_registry = _build_provider_registry(settings)
    primary_entry = provider_registry.get(settings.provider_name)
    primary_provider = (
        primary_entry.provider
        if primary_entry
        else StubProvider(embedding_dim=settings.rag_embedding_dim)
    )

    chat_service = ChatService(
        settings=settings,
        policy_client=OPAClient(settings),
        provider=primary_provider,
        redaction_engine=RedactionEngine(),
        audit_writer=AuditWriter(settings),
        retrieval_orchestrator=RetrievalOrchestrator(
            registry=connector_registry,
            default_k=settings.rag_default_top_k,
        ),
        provider_registry=provider_registry,
    )
    app.state.chat_service = chat_service

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = request_id_from_request(request)
        return app_error_response(
            exc.status_code, exc.code, exc.error_type, exc.message, request_id
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = request_id_from_request(request)
        return app_error_response(
            422, "request_validation_failed", "validation", str(exc), request_id
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, _: Exception) -> JSONResponse:
        request_id = request_id_from_request(request)
        return app_error_response(
            500, "internal_error", "provider", "Internal server error", request_id
        )

    app.include_router(router)
    return app


app = create_app()
