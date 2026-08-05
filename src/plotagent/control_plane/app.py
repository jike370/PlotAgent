"""FastAPI surface for the minimal Beta cloud control plane."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from plotagent.control_plane.config import ControlPlaneSettings
from plotagent.control_plane.errors import ERRORS, ControlPlaneError
from plotagent.control_plane.logging import SafeControlPlaneLogger
from plotagent.control_plane.models import (
    CredentialRevocationResponse,
    CredentialVerificationResponse,
    ErrorBody,
    ErrorResponse,
    ModelInvokeRequest,
    ModelRunResponse,
    QuotaSnapshot,
    RedeemInviteRequest,
    RedeemInviteResponse,
)
from plotagent.control_plane.provider import ProviderAdapter, UnavailableProviderAdapter
from plotagent.control_plane.security import SecretHasher
from plotagent.control_plane.service import ControlPlaneService
from plotagent.control_plane.store import ControlPlaneStore


def create_app(
    settings: ControlPlaneSettings,
    *,
    provider: ProviderAdapter | None = None,
    store: ControlPlaneStore | None = None,
    logger: SafeControlPlaneLogger | None = None,
) -> FastAPI:
    """Create an isolated app; tests and deployments inject the upstream adapter."""

    safe_logger = logger or SafeControlPlaneLogger()
    hasher = SecretHasher.from_text(settings.secret_pepper.get_secret_value())
    control_store = store or ControlPlaneStore(
        settings.database_path,
        hasher,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    service = ControlPlaneService(
        settings=settings,
        store=control_store,
        provider=provider or UnavailableProviderAdapter(),
        hasher=hasher,
        logger=safe_logger,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        service.startup_recover()
        yield

    app = FastAPI(
        title="PlotAgent Beta Control Plane",
        version="1",
        debug=False,
        lifespan=lifespan,
    )
    app.state.control_plane = service

    @app.exception_handler(ControlPlaneError)
    async def control_plane_error_handler(_: Request, exc: ControlPlaneError) -> JSONResponse:
        safe_logger.error(exc.code)
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        error = ControlPlaneError("REQUEST_INVALID")
        safe_logger.error(error.code)
        return _error_response(error)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, __: StarletteHTTPException) -> JSONResponse:
        error = ControlPlaneError("REQUEST_INVALID")
        safe_logger.error(error.code)
        return _error_response(error)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
        # Never stringify or attach a traceback: adapter exceptions may contain provider content.
        error = ControlPlaneError("INTERNAL_ERROR")
        safe_logger.error(error.code)
        return _error_response(error)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "protocol_version": settings.protocol_version}

    @app.post("/v1/invites/redeem", response_model=RedeemInviteResponse)
    async def redeem(request: RedeemInviteRequest) -> RedeemInviteResponse:
        return service.redeem(request)

    @app.post("/v1/credentials/verify", response_model=CredentialVerificationResponse)
    async def verify(request: Request) -> CredentialVerificationResponse:
        return service.verify(_bearer_credential(request))

    @app.delete("/v1/credentials/current", response_model=CredentialRevocationResponse)
    async def revoke_current(request: Request) -> CredentialRevocationResponse:
        return service.revoke_current(_bearer_credential(request))

    @app.get("/v1/quota", response_model=QuotaSnapshot)
    async def quota(request: Request) -> QuotaSnapshot:
        return service.verify(_bearer_credential(request)).quota_snapshot

    @app.post("/v1/model-runs", response_model=ModelRunResponse)
    async def invoke(
        request: Request,
        body: ModelInvokeRequest,
        response: Response,
    ) -> ModelRunResponse:
        result, status_code = await service.invoke(
            credential=_bearer_credential(request),
            request=body,
        )
        response.status_code = status_code
        return result

    @app.get("/v1/model-runs/{client_run_id}", response_model=ModelRunResponse)
    async def get_run(
        client_run_id: str,
        request: Request,
        response: Response,
    ) -> ModelRunResponse:
        result, status_code = service.get_run(
            credential=_bearer_credential(request),
            client_run_id=client_run_id,
        )
        response.status_code = status_code
        return result

    return app


def _bearer_credential(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, credential = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential or len(credential) > 512:
        raise ControlPlaneError("DEVICE_CREDENTIAL_INVALID")
    return credential


def _error_response(error: ControlPlaneError) -> JSONResponse:
    definition = ERRORS[error.code]
    body = ErrorResponse(
        error=ErrorBody(
            code=error.code,
            message=definition.message,
            retryable=definition.retryable,
            retry_after=error.retry_after,
        )
    )
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse(
        status_code=definition.status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )
