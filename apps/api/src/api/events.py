"""Event bus: publishes analysis lifecycle events to RabbitMQ.

We use RabbitMQ (via aio-pika) as the inter-service event bus so consumers
— audit loggers, notification services, downstream analytics — can react to
analyses without coupling to the API's write path. The FastAPI handler
commits to Postgres first, then fires a publish. If the broker is down or
unconfigured, the publish is a best-effort no-op and the analysis still
returns 201 to the client.

Topic layout:

    exchange: drug_cell_viz (type=topic, durable)
    routing keys:
        analysis.completed      — full AnalysisResult JSON
        analysis.failed         — {drug_id, detail} when analysis errors
        # Room to grow: variant.classified, pdf.rendered, etc.

The module keeps a singleton connection + channel per process. aio-pika's
RobustConnection handles reconnects transparently.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from api.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from aio_pika.abc import AbstractExchange, AbstractRobustConnection

    from api.models import AnalysisResult

logger = logging.getLogger(__name__)

_connection: "AbstractRobustConnection | None" = None
_exchange: "AbstractExchange | None" = None
_lock = asyncio.Lock()


async def _ensure_exchange() -> "AbstractExchange | None":
    """Open a robust connection + topic exchange on first use.

    Returns None if RABBITMQ_URL is unset (dev + test mode). Callers should
    treat None as "publish is a no-op."
    """
    global _connection, _exchange

    if not settings.rabbitmq_url:
        return None

    if _exchange is not None:
        return _exchange

    async with _lock:
        if _exchange is not None:
            return _exchange

        # Deferred import so environments without the aio-pika wheel can still
        # import api.events (e.g. pipeline-only contexts).
        import aio_pika
        from aio_pika import ExchangeType

        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await _connection.channel()
        _exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange,
            ExchangeType.TOPIC,
            durable=True,
        )
        logger.info(
            "rabbitmq: connected to %s, exchange=%s",
            _mask(settings.rabbitmq_url),
            settings.rabbitmq_exchange,
        )
        return _exchange


async def publish_analysis_completed(result: "AnalysisResult") -> None:
    """Fire `analysis.completed` with the full AnalysisResult JSON.

    Downstream consumers can filter on routing key `analysis.completed` or
    subscribe to the wider pattern `analysis.*`. Safe to call from any
    request handler — never raises.
    """
    exchange = await _ensure_exchange()
    if exchange is None:
        return

    from aio_pika import DeliveryMode, Message

    payload = {
        "schema": "drug_cell_viz.analysis.completed.v1",
        "analysis_id": result.id,
        "drug_id": result.drug_id,
        "drug_name": result.drug_name,
        "target_gene": result.target_gene,
        "hrd_label": result.hrd.label if result.hrd else None,
        "hrd_score": result.hrd.score if result.hrd else None,
        "current_drug_verdict": (
            result.current_drug_assessment.verdict
            if result.current_drug_assessment
            else None
        ),
        "created_at": result.created_at.isoformat(),
        "full_result": json.loads(result.model_dump_json()),
    }
    message = Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key="analysis.completed")


async def publish_analysis_failed(drug_id: str, detail: str) -> None:
    exchange = await _ensure_exchange()
    if exchange is None:
        return

    from aio_pika import DeliveryMode, Message

    payload = {
        "schema": "drug_cell_viz.analysis.failed.v1",
        "drug_id": drug_id,
        "detail": detail,
    }
    message = Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key="analysis.failed")


async def close() -> None:
    """Clean up the connection on FastAPI shutdown."""
    global _connection, _exchange
    if _connection is not None:
        await _connection.close()
    _connection = None
    _exchange = None


def _mask(url: str) -> str:
    """Redact password in the AMQP URL for safer logging."""
    if "@" not in url:
        return url
    scheme_and_auth, host = url.rsplit("@", 1)
    if "://" not in scheme_and_auth:
        return f"***@{host}"
    scheme, auth = scheme_and_auth.split("://", 1)
    if ":" in auth:
        user = auth.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://{auth}@{host}"
