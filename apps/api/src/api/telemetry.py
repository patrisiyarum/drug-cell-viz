"""OpenTelemetry wiring for the FastAPI app.

Auto-instruments FastAPI request handling and SQLAlchemy query execution,
exporting spans via OTLP HTTP to whatever endpoint `OTEL_EXPORTER_OTLP_ENDPOINT`
points at (Logfire, Grafana Tempo, Honeycomb, Jaeger's OTLP ingest, etc).

Falls back to a no-op tracer provider when no exporter endpoint is configured,
so running tests or booting the API locally doesn't spew trace noise.

To use Logfire specifically, set LOGFIRE_TOKEN in the environment and this
module will use Logfire's OTLP ingest URL with the token as a bearer header.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from api.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

LOGFIRE_ENDPOINT = "https://logfire-api.pydantic.dev/v1/traces"


def configure_telemetry(app: "FastAPI") -> None:
    """Attach OpenTelemetry instrumentation to the FastAPI app.

    No-op when no exporter is configured. Called from the FastAPI lifespan
    handler on startup; safe to call repeatedly.
    """
    endpoint, headers = _resolve_exporter()
    if endpoint is None:
        logger.debug("telemetry: no OTLP endpoint configured; skipping instrumentation")
        return

    # Deferred imports — the OTel wheels are heavy, and tests that don't care
    # about tracing don't pay the import cost.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()

    logger.info("telemetry: OTLP exporter configured (endpoint=%s)", endpoint)


def _resolve_exporter() -> tuple[str | None, dict[str, str]]:
    """Decide where to send spans.

    Priority:
      1. LOGFIRE_TOKEN → Logfire's OTLP ingest with bearer auth.
      2. OTEL_EXPORTER_OTLP_ENDPOINT → generic OTLP HTTP endpoint.
      3. Neither → no-op.
    """
    if settings.logfire_token:
        return LOGFIRE_ENDPOINT, {"Authorization": f"Bearer {settings.logfire_token}"}
    if settings.otel_exporter_otlp_endpoint:
        return settings.otel_exporter_otlp_endpoint, {}
    return None, {}
