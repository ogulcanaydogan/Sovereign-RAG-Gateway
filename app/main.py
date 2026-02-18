from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.audit.writer import AuditWriter
from app.config.settings import get_settings
from app.core.errors import AppError, app_error_response, request_id_from_request
from app.core.logging import configure_logging
from app.middleware.auth import AuthMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.policy.client import OPAClient
from app.providers.stub import StubProvider
from app.rag.connectors.filesystem import FilesystemConnector
from app.rag.connectors.postgres import PostgresPgvectorConnector
from app.rag.registry import ConnectorRegistry
from app.rag.retrieval import RetrievalOrchestrator
from app.redaction.engine import RedactionEngine
from app.services.chat_service import ChatService


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Sovereign RAG Gateway", version="0.2.0-rc1")

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AuthMiddleware)

    connector_registry = ConnectorRegistry()
    connector_registry.register(
        "filesystem",
        FilesystemConnector(index_path=settings.rag_filesystem_index_path),
    )
    if settings.rag_postgres_dsn:
        connector_registry.register(
            "postgres",
            PostgresPgvectorConnector(
                dsn=settings.rag_postgres_dsn,
                table=settings.rag_postgres_table,
                embedding_dim=settings.rag_embedding_dim,
            ),
        )

    chat_service = ChatService(
        settings=settings,
        policy_client=OPAClient(settings),
        provider=StubProvider(),
        redaction_engine=RedactionEngine(),
        audit_writer=AuditWriter(settings),
        retrieval_orchestrator=RetrievalOrchestrator(
            registry=connector_registry,
            default_k=settings.rag_default_top_k,
        ),
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
