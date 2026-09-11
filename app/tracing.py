"""Optional OpenTelemetry tracing (Phase 9).

Off by default (`OTEL_ENABLED=false`) — importing this module and
calling `setup_tracing(app)` is a no-op unless explicitly enabled, so it
cannot change existing behavior or break tests that don't set the env
var (CLAUDE.md rule 8: justify added complexity, keep it opt-in).

When enabled, spans export via OTLP/gRPC to a local collector — a free,
locally-run Arize Phoenix instance works out of the box
(`docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix`), or any
other OTLP-compatible local collector. No paid observability service is
required or assumed.
"""

from fastapi import FastAPI

from app.config import get_settings


def setup_tracing(app: FastAPI) -> None:
    settings = get_settings()
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
